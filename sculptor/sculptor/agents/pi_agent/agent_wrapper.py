"""PiAgent — `DefaultAgentWrapper` subclass wrapping `pi --mode rpc`.

The agent spawns a long-lived `pi --mode rpc --session-dir <dir> --session-id
<id> --no-extensions -e <pinned extension> --append-system-prompt <prompt>
[--skill <dir> ...]` subprocess and pumps user turns over JSONL stdin/stdout.
The session flags persist the conversation as a JSONL file under a per-task dir
and pin its id Sculptor-side, so relaunching after an agent-process restart
resumes the full conversation (`supports_session_resume`). The `--skill` flags
point pi at the workspace's Claude-visible skill sources so its skill set
matches the slash picker's (`supports_skills`). The pinned `sculptor_backchannel`
extension (`extensions/`, `backchannel.py`), loaded with `--no-extensions -e`,
provides ask-user-question + plan mode: its blocking dialogs arrive as
`extension_ui_request` and are mapped onto `AskUserQuestionAgentMessage`, with
the user's `UserQuestionAnswerMessage` routed back as the matching
`extension_ui_response`. Pi's stdout multiplexes three channels (`response`,
`extension_ui_request`, and the `AgentSessionEvent` union); the dispatcher
distinguishes them by top-level `type`. Pi's tool calls render as rich tool
blocks (`supports_tool_use_rendering=True`): the issuing assistant message's
`toolCall` content blocks become `ToolUseBlock`s (name + input, shown while
running) and the tool-execution lane's `tool_execution_end` becomes the
`ToolResultBlock` (the result, shown when done), correlated by the shared
tool-call id (see `tool_rendering.py` for the pi→Claude name/arg adaptation). A
finished file-mutating tool (`edit`/`write`/`bash`) additionally triggers
`on_diff_needed` so the workspace diff is regenerated — pi runs the tools
against the workspace itself and emits no other signal that files changed.

Sub-agents (`supports_sub_agents=True`) yield immediately: the pinned
`sculptor_subagent` extension's `subagent` tool (mapped to Claude's `Agent`)
returns a launch snapshot and reports a structured per-child payload out-of-band
on completion. The adapter (`_emit_subagent_started` +
`_handle_subagent_completion` + `subagent.py`) records the task, then surfaces the
children as nested `ResponseBlockAgentMessage`s carrying `parent_tool_use_id` plus
a completion notification, so children group under the parent.

Wire-protocol reference: the pi RPC protocol notes (pi 0.78.0).
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Event
from threading import Lock
from typing import Any
from typing import Mapping
from typing import assert_never

from loguru import logger
from packaging.version import InvalidVersion
from packaging.version import Version
from pydantic import PrivateAttr
from pydantic import ValidationError

from sculptor.agents.attachments import save_attachments_to_environment
from sculptor.agents.default.agent_wrapper import DefaultAgentWrapper
from sculptor.agents.default.utils import get_state_file_contents
from sculptor.agents.default.utils import get_turn_request_id
from sculptor.agents.pi_agent.authenticated_providers import compute_authenticated_provider_ids
from sculptor.agents.pi_agent.backchannel import PLAN_APPROVAL_DIALOG_TITLE
from sculptor.agents.pi_agent.backchannel import build_ask_user_question_data
from sculptor.agents.pi_agent.backchannel import extension_ui_response_body
from sculptor.agents.pi_agent.backchannel import is_plan_approval
from sculptor.agents.pi_agent.background import BackgroundTaskCompletion
from sculptor.agents.pi_agent.background import parse_background_completion
from sculptor.agents.pi_agent.background import parse_background_start
from sculptor.agents.pi_agent.harness import PiHarness
from sculptor.agents.pi_agent.output_processor import AgentMessage
from sculptor.agents.pi_agent.output_processor import ExtensionUiRequest
from sculptor.agents.pi_agent.output_processor import ParsedAgentEnd
from sculptor.agents.pi_agent.output_processor import ParsedAgentStart
from sculptor.agents.pi_agent.output_processor import ParsedAssistantMessageError
from sculptor.agents.pi_agent.output_processor import ParsedAutoRetryEnd
from sculptor.agents.pi_agent.output_processor import ParsedAutoRetryStart
from sculptor.agents.pi_agent.output_processor import ParsedCompactionEnd
from sculptor.agents.pi_agent.output_processor import ParsedCompactionStart
from sculptor.agents.pi_agent.output_processor import ParsedExtensionError
from sculptor.agents.pi_agent.output_processor import ParsedMessageEnd
from sculptor.agents.pi_agent.output_processor import ParsedMessageStart
from sculptor.agents.pi_agent.output_processor import ParsedMessageUpdate
from sculptor.agents.pi_agent.output_processor import ParsedQueueUpdate
from sculptor.agents.pi_agent.output_processor import ParsedRpcMessage
from sculptor.agents.pi_agent.output_processor import ParsedSessionInfoChanged
from sculptor.agents.pi_agent.output_processor import ParsedTextDelta
from sculptor.agents.pi_agent.output_processor import ParsedThinkingLevelChanged
from sculptor.agents.pi_agent.output_processor import ParsedToolExecutionEnd
from sculptor.agents.pi_agent.output_processor import ParsedToolExecutionStart
from sculptor.agents.pi_agent.output_processor import ParsedToolExecutionUpdate
from sculptor.agents.pi_agent.output_processor import ParsedTurnEnd
from sculptor.agents.pi_agent.output_processor import ParsedTurnStart
from sculptor.agents.pi_agent.output_processor import ParsedUnknownEvent
from sculptor.agents.pi_agent.output_processor import RpcResponse
from sculptor.agents.pi_agent.output_processor import extract_assistant_text
from sculptor.agents.pi_agent.output_processor import humanize_pi_failure_reason
from sculptor.agents.pi_agent.output_processor import humanize_transient_failure_reason
from sculptor.agents.pi_agent.output_processor import is_transient_provider_error
from sculptor.agents.pi_agent.output_processor import parse_rpc_message
from sculptor.agents.pi_agent.output_processor import sum_message_usage
from sculptor.agents.pi_agent.prompt_assembly import build_attachment_instructions
from sculptor.agents.pi_agent.prompt_assembly import build_image_block
from sculptor.agents.pi_agent.prompt_assembly import split_image_and_path_attachments
from sculptor.agents.pi_agent.subagent import SubagentChild
from sculptor.agents.pi_agent.subagent import SubagentCompletion
from sculptor.agents.pi_agent.subagent import build_child_content_blocks
from sculptor.agents.pi_agent.subagent import parse_subagent_completion
from sculptor.agents.pi_agent.subagent import parse_subagent_start
from sculptor.agents.pi_agent.tool_rendering import BACKGROUND_TOOL_NAME
from sculptor.agents.pi_agent.tool_rendering import SUBAGENT_DISPLAY_NAME
from sculptor.agents.pi_agent.tool_rendering import build_tool_result_content
from sculptor.agents.pi_agent.tool_rendering import extract_text_from_tool_payload
from sculptor.agents.pi_agent.tool_rendering import map_pi_tool_call
from sculptor.common.plugin import get_plugin_dirs
from sculptor.foundation.common import generate_id
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingDoneAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskNotificationAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskStartedAgentMessage
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import ContextClearedMessage
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import ModelsAvailableAgentMessage
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import PlanModeAgentMessage
from sculptor.interfaces.agents.agent import RefreshModelsUserMessage
from sculptor.interfaces.agents.agent import RemoveQueuedMessageUserMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import SetModelUserMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import TurnMetricsAgentMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
from sculptor.interfaces.agents.errors import AgentCrashed
from sculptor.interfaces.agents.errors import AgentTransientError
from sculptor.interfaces.agents.errors import PiBinaryNotFoundError
from sculptor.interfaces.agents.errors import PiContextResetError
from sculptor.interfaces.agents.errors import PiCrashError
from sculptor.interfaces.agents.errors import PiSetModelError
from sculptor.interfaces.agents.errors import PiVersionMismatchError
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import ToolUseID
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.dependency_management_service import parse_pi_version
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import ContentBlockTypes
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.chat_state import TurnMetrics
from sculptor.state.chat_state import make_plan_approval_question
from sculptor.state.claude_state import get_tool_invocation_string
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message
from sculptor.state.messages import ModelOption
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.web.skills import SkillSourceKind
from sculptor.web.skills import discover_skills
from sculptor.web.skills import get_skill_source_directories
from sculptor.web.skills import parse_command_frontmatter

# Pi's file-mutating tools, keyed by their lowercase RPC `toolName`
# (pi 0.78.0 `packages/coding-agent/src/core/tools/{edit,write,bash}.ts`;
# the same literals are the `toolName` union in pi's `ToolExecutionEndEvent`).
# This is the pi analogue of Claude's PascalCase `FILE_CHANGE_TOOL_NAMES`
# (Edit/Write/MultiEdit, plus Bash) — pi has no MultiEdit, and `bash` is
# included because pi, like Claude, can mutate files via the shell. A
# completed, non-error call to one of these means the working tree may have
# changed, so Sculptor must regenerate the workspace diff artifact.
FILE_CHANGE_TOOL_NAMES: frozenset[str] = frozenset({"edit", "write", "bash"})

# Pi persists each conversation as a single auto-saved JSONL session file
# (`<timestamp>_<sessionId>.jsonl`) under `--session-dir`. Sculptor gives pi a
# per-task session dir under the environment state path (so parallel pi
# workspaces never share a session) and pins the id Sculptor-side with
# `--session-id` (pi adopts the exact id, "creating it if missing"). Relaunching
# with the same dir + id after an agent-process restart resumes the full
# conversation — the whole of `supports_session_resume`. The chosen id is
# persisted in PI_SESSION_ID_STATE_FILE so a restart reuses it.
PI_SESSION_DIR_NAME: str = "pi_session"
PI_SESSION_ID_STATE_FILE: str = "pi_session_id"

# The throwaway session dir the pre-message catalog probe launches pi against
# (see fetch_available_models_probe). Distinct from PI_SESSION_DIR_NAME so the
# probe's short-lived session never collides with the real conversation session
# the agent later resumes.
PI_PROBE_SESSION_DIR_NAME: str = "pi_probe_session"

# Control messages that legitimately reach the end of `_push_message` without pi
# handling them: the base class handles these after the False return (see
# DefaultAgentWrapper.push_message). Pi recognizes them as handled-elsewhere, so
# they are NOT dead-lettered; anything else reaching the end has no handler.
_BASE_CLASS_HANDLED_MESSAGE_TYPES: tuple[type[Message], ...] = (
    StopAgentUserMessage,
    RemoveQueuedMessageUserMessage,
)

# If pi's abort-induced `agent_end` does not arrive within this grace window
# (pi wedged or ignoring the abort), escalate to SIGTERM; the process-exit
# fallback in `_consume_until_turn_end` then resolves the turn.
_INTERRUPT_ESCALATION_GRACE_SECONDS: float = 5.0

# The backchannel extension shipped with Sculptor (package data; see
# pyproject.toml). Resolved next to this module so it works from an installed
# build as well as a repo checkout, then written into the environment at launch.
_BACKCHANNEL_EXTENSION_FILENAME: str = "sculptor_backchannel.ts"
# The sub-agent extension shipped with Sculptor (package data; see pyproject.toml).
# Registers the `subagent` tool that spawns child `pi` processes, yields
# immediately, and reports its lifecycle out-of-band, rendered nested (see
# subagent.py).
_SUBAGENT_EXTENSION_FILENAME: str = "sculptor_subagent.ts"
# The background-task extension shipped with Sculptor (package data; see
# pyproject.toml). Registers the `background` tool that starts a shell command
# in the background and reports its lifecycle out-of-band (see background.py).
_BACKGROUND_EXTENSION_FILENAME: str = "sculptor_background.ts"
_EXTENSIONS_SOURCE_DIR: Path = Path(__file__).resolve().parent / "extensions"

# Prepended to a turn's prompt while the agent is in plan mode. Drives the pi
# agent to explore read-only and present its plan via the `exit_plan_mode` tool
# for approval — the pi analogue of Claude's `is_in_plan_mode` user-instructions.
# (Divergence, REQ-CAP-ALL-3: read-only is requested in the prompt, not enforced
# by a tool allowlist.)
_PLAN_MODE_PROMPT_PREFIX: str = """[PLAN MODE]
You are in plan mode. Investigate the request using read-only tools only (read files, inspect with read-only bash, grep, find, ls) and do NOT modify any files or run state-changing commands. Produce a clear, numbered plan describing what you would do. When the plan is ready, call the `exit_plan_mode` tool to present it to the user for approval. Do not begin implementing until the user approves; if they request revisions, refine the plan and call `exit_plan_mode` again.

The user's request follows:
"""

# How long the context-reset handler waits for `new_session` to be acknowledged
# before treating the reset as failed. Under the frontend's 30s clear-call budget
# (ChatInput.tsx `wsTimeout`) so a wedged `new_session` fails rather than hanging the UI.
_CLEAR_CONTEXT_TIMEOUT_SECONDS: float = 10.0

# After a background/sub-agent completion, the extension wakes the agent with
# `sendUserMessage`; Sculptor keeps the idle-drain alive this long to consume the
# resulting reaction turn. Bounds the wait so a reaction that never arrives (the
# wake-up errored) cannot keep the drain polling forever.
_REACTION_WINDOW_SECONDS: float = 120.0

# How long each blocking read of pi's stdout queue waits before the drain loop
# re-checks shutdown / process-exit; small so an exit is noticed promptly.
_STDOUT_QUEUE_POLL_SECONDS: float = 0.1

# Input-queue wait between turns. While async tasks/reactions are pending, poll
# briefly so their out-of-band completions surface promptly; when idle, wait
# longer to avoid busy-polling (a new user message wakes the queue immediately
# either way, and the longer wait bounds shutdown latency).
_TASK_POLL_SECONDS: float = 0.1
_IDLE_WAIT_SECONDS: float = 1.0

# How long the start-time model fetch waits for pi's get_available_models /
# get_state responses before giving up (see _fetch_models_into_state).
_MODEL_FETCH_TIMEOUT_SECONDS: float = 10.0

# Transient-provider-error retry policy. A turn that ends with a known-transient
# provider failure (overloaded / rate-limit / 5xx / timeout — see
# `is_transient_provider_error`) is re-prompted up to this many times with
# exponential backoff + jitter before the turn surfaces a non-fatal, retryable
# AgentTransientError instead of crashing the agent. Backoff for retry N is
# base*2**(N-1) seconds, capped at the max, with equal jitter so concurrent
# agents that hit the same provider surge do not retry in lockstep.
_PI_TRANSIENT_MAX_RETRIES: int = 4
_PI_TRANSIENT_RETRY_BASE_DELAY_SECONDS: float = 1.0
_PI_TRANSIENT_RETRY_MAX_DELAY_SECONDS: float = 30.0

# Obsolete model ids pi's get_available_models returns that the switcher must not
# offer — the whole pre-4 `claude-3-*` family (the live Anthropic catalog still
# lists these). Curation drops any id in this set (_curate_models).
_PI_MODEL_BLACKLIST: frozenset[str] = frozenset(
    {
        "claude-3-5-haiku-20241022",
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-latest",
        "claude-3-7-sonnet-20250219",
        "claude-3-7-sonnet-latest",
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
        "claude-3-opus-latest",
        "claude-3-sonnet-20240229",
    }
)

# A "dated pin" model id ends in an 8-digit date (e.g. claude-opus-4-1-20250805).
# pi lists these alongside the friendly alias for the same model (claude-opus-4-1),
# so curation drops the dated duplicate and keeps the alias.
_DATED_PIN_SUFFIX_RE = re.compile(r"-\d{8}$")

# Captures the trailing major.minor version of a pi model id (e.g. the (4, 8) in
# claude-opus-4-8, the (4, 0) in claude-opus-4-0) for the newest-first sort.
_MODEL_VERSION_RE = re.compile(r"-(\d+)-(\d+)$")


def _model_sort_key(model: ModelOption) -> tuple[int, int, str]:
    """Newest-first sort key: descending (major, minor), then id for stability.

    Parses the trailing `-<major>-<minor>` of the model id (e.g. claude-opus-4-8
    → (4, 8)); ids without that shape sort last. The id tiebreaker keeps the order
    deterministic across same-version families.
    """
    match = _MODEL_VERSION_RE.search(model.model_id)
    if match is None:
        return (1, 0, model.model_id)
    major, minor = int(match.group(1)), int(match.group(2))
    return (-major, -minor, model.model_id)


def _curate_models(
    models: list[ModelOption],
    current_model: ModelOption | None,
    authenticated_providers: set[str] | None = None,
) -> list[ModelOption]:
    """Trim pi's raw catalog to the models the switcher should offer, newest-first.

    Drops the obsolete `_PI_MODEL_BLACKLIST` ids and dated-pin duplicates
    (`_DATED_PIN_SUFFIX_RE`), then sorts newest-first (`_model_sort_key`). The
    current model is always kept even if a rule would drop it, so the switcher
    never shows an empty selection. Duplicate ids are de-duplicated, first-wins.

    When `authenticated_providers` is provided, options whose `provider` is not in
    that set are also dropped — pi gates its catalog on credential presence, not
    validity, so a stray ambient key would otherwise leak that provider's models
    into the picker. `None` (the default) disables the filter. The current model is
    exempt from every rule, including this one.
    """
    kept: list[ModelOption] = []
    seen_ids: set[str] = set()
    current_id = current_model.model_id if current_model is not None else None
    for model in models:
        if model.model_id in seen_ids:
            continue
        is_current = model.model_id == current_id
        if not is_current and model.model_id in _PI_MODEL_BLACKLIST:
            continue
        if not is_current and _DATED_PIN_SUFFIX_RE.search(model.model_id):
            continue
        if not is_current and authenticated_providers is not None and model.provider not in authenticated_providers:
            continue
        seen_ids.add(model.model_id)
        kept.append(model)
    # The current model must be offered even if pi did not list it in the catalog.
    if current_model is not None and current_id not in seen_ids:
        kept.append(current_model)
    return sorted(kept, key=_model_sort_key)


def _model_option_from_pi(raw: Mapping[str, Any]) -> ModelOption | None:
    """Map one pi Model dict (`{id, name, provider, …}`) to a `ModelOption`.

    Returns None when the required `id` is missing/empty. `provider` defaults to
    "anthropic" (Sculptor launches pi against the Anthropic catalog) and the
    display name falls back to the id when pi omits `name`.
    """
    model_id = raw.get("id")
    if not isinstance(model_id, str) or not model_id:
        return None
    provider = raw.get("provider")
    name = raw.get("name")
    return ModelOption(
        provider=provider if isinstance(provider, str) and provider else "anthropic",
        model_id=model_id,
        display_name=name if isinstance(name, str) and name else model_id,
    )


def _pi_version_in_range(version: str) -> bool:
    try:
        v = Version(version)
    except InvalidVersion:
        return False
    return Version(PI_VERSION_RANGE.min_version) <= v <= Version(PI_VERSION_RANGE.max_version)


@dataclass
class _ToolCall:
    """A tool call's rendering state, keyed by pi's tool-call id.

    Registered when the issuing assistant message finalizes (its `toolCall`
    content block) or, as a fallback, at `tool_execution_start`. The
    tool-execution lane (`tool_execution_update`/`_end`) looks it up by id to
    attach the result to the same rendered `ToolUseBlock`. `assistant_message_id`
    is the id of the segment that issued the call, so the result block attaches
    to the right assistant message even though the lane events arrive after the
    issuing message's `message_end` reset the accumulator.

    Mutable transient state (`partial_text` accumulates across
    `tool_execution_update`s); it is never serialized, mirroring `_TurnState`.
    """

    claude_name: str
    claude_input: dict[str, Any]
    assistant_message_id: AssistantMessageID
    # Accumulated (not delta) tool output from the latest `tool_execution_update`,
    # used as the result text if `tool_execution_end` carries no result body.
    partial_text: str = ""
    # True for the sub-agent tool (mapped to Claude's `Agent`): its result carries
    # a structured launch payload (`subagent.py`); it yields immediately, and the
    # children's nested rendering + completion is surfaced out-of-band. See
    # `_emit_subagent_started`.
    is_subagent: bool = False
    # True for the background tool: its result carries a structured launch
    # payload (`background.py`) the adapter turns into a BackgroundTaskStarted
    # message + a tracked pending task, instead of a one-shot result.
    is_background: bool = False


# Matches a leading slash-command token (`/name`) and captures the remainder
# (args), DOTALL so multi-line prompts keep their tail. `\S+` lets the name
# carry a `:` so a plugin-namespaced `/sculptor-workflow:fix-bug` is captured
# whole before the namespace is stripped.
_SKILL_INVOCATION_RE = re.compile(r"^/(\S+)(.*)$", re.DOTALL)


def _rewrite_skill_invocation(text: str, discovered_skill_names: frozenset[str]) -> str:
    """Rewrite a leading Sculptor skill invocation into pi's `/skill:<name>` shape.

    The frontend stays harness-agnostic: it sends a picked skill as the same
    `/name [args]` text it sends Claude. pi instead invokes a skill as
    `/skill:<name>`. When `name` is one of the workspace's discovered skills
    (the set the slash picker offers), rewrite `/name [args]` →
    `/skill:<name> [args]`; otherwise the text is passed through untouched.

    Pseudo-skills (`/clear`, `/copy`, `/btw`) are parsed frontend-side and
    never reach here nor appear in the discovered set, so they pass through;
    ordinary text that merely starts with `/` is left alone. A plugin-namespaced
    name (`<plugin>:<skill>`) is reduced to its bare `<skill>` because pi
    registers plugin skills un-namespaced.
    """
    if not text.startswith("/"):
        return text
    match = _SKILL_INVOCATION_RE.match(text)
    if match is None:
        return text
    name, rest = match.group(1), match.group(2)
    if name not in discovered_skill_names:
        return text
    bare_name = name.rsplit(":", 1)[-1]
    return f"/skill:{bare_name}{rest}"


def _render_synthesized_skill(name: str, description: str, body: str) -> str:
    """Render a SKILL.md that wraps a loose `.claude/commands/*.md` command.

    pi only discovers skills as `SKILL.md` directories, so a loose command file
    is wrapped in one. `name`/`description` are JSON-encoded (valid YAML flow
    scalars) so colons, quotes, or stray characters in either can't break the
    frontmatter; the description is flattened to one line because pi refuses to
    load a skill whose description is missing.
    """
    flat_description = " ".join(description.split())
    return f"---\nname: {json.dumps(name)}\ndescription: {json.dumps(flat_description)}\n---\n\n{body}"


class _TurnState:
    """Per-turn streaming accumulator state.

    The text accumulator is reset between assistant messages so each
    `message_update` chain accumulates against a fresh `assistant_message_id`.
    The tool-call registry (`tool_calls`) is NOT reset per message — a tool's
    execution lane events arrive after the issuing message's `message_end`, so
    the registry persists for the whole agent run (keyed by unique tool-call id).
    """

    __slots__ = (
        "accumulated_text",
        "assistant_message_id",
        "changed_files",
        "compaction_open",
        "first_message_id",
        "prompt_id",
        "start_time",
        "tool_calls",
    )

    def __init__(self, prompt_id: str) -> None:
        self.prompt_id = prompt_id
        self.accumulated_text = ""
        self.assistant_message_id = AssistantMessageID(generate_id())
        self.first_message_id = AgentMessageID()
        self.tool_calls: dict[str, _ToolCall] = {}
        # Wall-clock start of this agent run, used for the turn footer's duration.
        # Mirrors Claude's per-turn duration (wall-clock, not the model's
        # response-only time). A transient retry rebuilds _TurnState, so this
        # measures the final (successful) attempt.
        self.start_time = time.monotonic()
        # File paths mutated by file-changing tools during this run (git-relative
        # display paths from the tool args). Feeds the turn footer's "N files
        # changed" — the authoritative, all-tools source the frontend prefers over
        # its streaming-time ToolUseBlock scan. Insertion-ordered + de-duplicated.
        self.changed_files: list[str] = []
        # True between a compaction_start and its matching compaction_end.
        # Compaction spans assistant messages, so this is NOT reset in
        # reset_accumulator. If the run exits while it is still open (process
        # death or a raised error mid-compaction), _consume_until_turn_end
        # emits the missing Done so is_auto_compacting cannot stick on True.
        self.compaction_open = False

    def note_changed_file(self, file_path: str) -> None:
        """Record a mutated file path once, preserving first-seen order."""
        if file_path and file_path not in self.changed_files:
            self.changed_files.append(file_path)

    def reset_accumulator(self) -> None:
        self.accumulated_text = ""
        self.assistant_message_id = AssistantMessageID(generate_id())
        self.first_message_id = AgentMessageID()


def _format_background_completion(completion: BackgroundTaskCompletion) -> str:
    """The assistant text surfaced when a background task finishes.

    Renders the completion in the conversation (the background tool itself is not
    a sub-agent, so message_conversion does not synthesize a child for it). The
    summary is the tail of the command's combined stdout/stderr.
    """
    verb = "completed" if completion.status == "completed" else completion.status
    exit_note = "" if completion.exit_code is None else f" (exit code {completion.exit_code})"
    header = f"Background task {verb}{exit_note}."
    summary = completion.summary.strip()
    return f"{header}\n\n{summary}" if summary else header


def _format_subagent_completion(completion: SubagentCompletion) -> str:
    """The summary surfaced when a sub-agent task finishes.

    Rides the completion `BackgroundTaskNotificationAgentMessage`; for an `Agent`
    parent, message_conversion turns it into the synthetic completion child that
    settles the sub-agent pill.
    """
    done = sum(1 for child in completion.children if child.status == "done")
    failed = sum(1 for child in completion.children if child.status == "error")
    total = len(completion.children)
    verb = "completed" if completion.status == "completed" else completion.status
    return f"Sub-agents {verb}: {done} done, {failed} failed (of {total})."


class _PiTransientTurnError(Exception):
    """Internal signal that the current turn hit a KNOWN-TRANSIENT provider error.

    Raised from the dispatcher's stopReason-"error" handling when the failure is a
    retryable provider condition (overloaded / rate-limit / 5xx / timeout), and
    caught by `_consume_turn_with_transient_retry`, which re-prompts pi with
    backoff. It never escapes the agent: a successful retry completes the turn
    normally, and an exhausted retry budget is re-surfaced as the non-fatal,
    retryable `AgentTransientError`. NOT an `AgentClientError`, so
    `_handle_user_message` does not intercept it before the retry loop runs.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PiAgent(DefaultAgentWrapper):
    # Narrows the inherited `harness: Harness` field — the registry owns
    # construction, so no agent↔harness import cycle exists.
    # pyrefly: ignore [bad-override-mutable-attribute]
    harness: PiHarness
    config: PiAgentConfig
    git_hash: str
    # Carries chat turns AND between-turns control messages (context reset,
    # model switch) through one FIFO so each runs strictly after any in-flight
    # turn — the sole-reader window where the control RPCs' responses can be
    # consumed safely (see _process_message_queue).
    _input_agent_messages: Queue[
        ChatInputUserMessage | ClearContextUserMessage | SetModelUserMessage | RefreshModelsUserMessage
    ] = PrivateAttr(default_factory=Queue)
    _shutdown_event: Event = PrivateAttr(default_factory=Event)
    _message_processing_thread: ObservableThread | None = PrivateAttr(default=None)
    # The pi session id this process resumes / creates (pinned via --session-id);
    # persisted in PI_SESSION_ID_STATE_FILE so a restart reuses it.
    _session_id: str = PrivateAttr(default="")
    # Set while a turn is actively draining pi's stdout — gates the interrupt
    # escalation so an interrupt that races in between turns never SIGTERMs an
    # idle (but healthy) pi.
    _turn_in_flight: Event = PrivateAttr(default_factory=Event)
    # The request id of the chat turn currently being processed (its
    # RequestStarted was emitted; the matching terminal RequestSuccess may not
    # have been). The interrupt path keys its reconciling RequestSuccess on this
    # when no turn is in flight, so an idle-but-RUNNING agent — a turn orphaned
    # without a terminal completion (e.g. a prior process death) — still settles
    # on Stop. Mirrors ClaudeProcessManager._in_flight_request_id.
    _in_flight_request_id: AgentMessageID | None = PrivateAttr(default=None)
    # Set when an interrupt has been requested and we are waiting for pi's
    # abort-induced boundary. The dispatcher consults it so `stopReason:"aborted"`
    # finalizes the partial response instead of raising `PiCrashError`.
    _interrupt_pending: Event = PrivateAttr(default_factory=Event)
    # The current escalation timer's cancel signal (one per interrupt). Set when
    # the turn ends so the grace-window thread stands down without SIGTERM.
    _escalation_cancel: Event | None = PrivateAttr(default=None)
    # The workspace's discovered skill names (the same set the slash picker
    # offers), captured at launch so `_run_prompt_turn` can rewrite a picked
    # `/name` into pi's `/skill:<name>` form. Empty until `start()`.
    _discovered_skill_names: frozenset[str] = PrivateAttr(default_factory=frozenset)
    # Absolute paths pi was launched with via `-e` (the pinned extension set);
    # used by the fail-loud posture to tell our extension's errors from foreign.
    _loaded_extension_paths: tuple[str, ...] = PrivateAttr(default=())
    # Interactive-backchannel state, shared between the dispatcher thread (which
    # sets `_pending_ui_request_id` when our extension opens a dialog) and the
    # request-handling thread (which clears it and writes the answer in
    # `_deliver_question_answer`). Guarded by `_backchannel_lock`.
    _backchannel_lock: Lock = PrivateAttr(default_factory=Lock)
    _pending_ui_request_id: str | None = PrivateAttr(default=None)
    # Tool-call id of the backchannel tool whose dialog is currently open. Pi
    # assigns the tool call and the extension's `ui_request` separate ids; this
    # is the tool-call id — the one carried by the rendered ToolUseBlock /
    # ToolResultBlock — used as the question's `tool_use_id` so the frontend
    # correlates the answered question with its tool block (Claude's single-id
    # model). Set and read on the dispatcher thread only. `_pending_ui_request_id`
    # keeps the separate ui_request id for the `extension_ui_response` round-trip.
    _pending_backchannel_tool_call_id: str | None = PrivateAttr(default=None)
    # Answer request ids awaiting their deferred RequestSuccess (emitted at the
    # turn boundary so the post-answer content reaches the frontend first —
    # mirrors Claude's `_pending_answer_request_ids`).
    _pending_answer_request_ids: list[AgentMessageID] = PrivateAttr(default_factory=list)
    # Tracks plan mode across turns (set from ChatInputUserMessage flags, cleared
    # on plan approval) so the prompt carries the plan-mode preamble — the pi
    # analogue of ClaudeProcessManager._is_in_plan_mode.
    _is_in_plan_mode: bool = PrivateAttr(default=False)
    # Serializes stdin writes: the prompt pump, the answer-delivery thread, and
    # `wait()`'s abort can all write to pi's stdin.
    _send_lock: Lock = PrivateAttr(default_factory=Lock)
    # In-flight background tasks (background_task_id -> the detached child's
    # process-group id), tracked at the AGENT level so they outlive the launching
    # turn: a `background` tool yields its turn immediately (the user keeps
    # chatting), and the task's completion is surfaced out-of-band later. The pgid
    # lets `wait()` SIGTERM each child's group in the environment on shutdown (the
    # child is detached, so it escapes pi's own group — `session_shutdown` in the
    # extension is the other half of the no-orphan guarantee). Mutated only on the
    # message-processing thread; the lock guards `wait()`'s cross-thread read.
    _background_tasks: dict[str, int] = PrivateAttr(default_factory=dict)
    # In-flight sub-agent tasks (task_id -> the detached children's process-group
    # ids), tracked at the AGENT level so they outlive the launching turn: the
    # `subagent` tool yields immediately and the children's nested rendering is
    # surfaced out-of-band on completion. Guarded by `_background_tasks_lock` (it
    # protects both task dicts).
    _subagent_tasks: dict[str, tuple[int, ...]] = PrivateAttr(default_factory=dict)
    _background_tasks_lock: Lock = PrivateAttr(default_factory=Lock)
    # Count of surfaced completions whose auto-resume reaction turn (the
    # extension's `sendUserMessage`) has not yet been consumed, with a deadline.
    # Keeps the idle-drain alive to catch the reaction. Mutated only on the
    # message-processing thread.
    _awaiting_reaction_count: int = PrivateAttr(default=0)
    _awaiting_reaction_deadline: float = PrivateAttr(default=0.0)
    # The curated model catalog surfaced at start (`_fetch_models_into_state`),
    # cached so a `set_model` switch can re-emit it with the new current model in
    # its `ModelsAvailableAgentMessage` carrier. Set and read on the
    # message-processing thread only.
    _available_models: tuple[ModelOption, ...] = PrivateAttr(default=())

    def start(self, secrets: Mapping[str, str | Secret]) -> None:
        # Resolve and validate the pi binary BEFORE super().start so the
        # failure surfaces (PiBinaryNotFoundError / PiVersionMismatchError)
        # short-circuit the heavier state-file + token-stream setup.
        binary = self.environment.get_tool_binary_path(Dependency.PI)
        if binary is None:
            raise PiBinaryNotFoundError()

        detected_version = self._check_pi_version(binary)
        if not _pi_version_in_range(detected_version):
            raise PiVersionMismatchError(
                detected_version=detected_version,
                pinned_version=PI_VERSION_RANGE.recommended_version,
            )

        super().start(secrets)

        # Pi reads its API key from the process environment at launch; the
        # configured env-var names are looked up in os.environ and injected
        # as Secrets. Values are never persisted to config.
        pi_secrets = self._collect_api_key_secrets()
        merged_secrets: dict[str, str | Secret] = {**self._secrets, **pi_secrets}

        # Resolve (or mint) the per-task session id. A persisted id means a prior
        # process wrote a session we should resume; its absence means this is the
        # first launch, so we mint and persist an id up front — NOT after the
        # first turn — so even a crash during the very first turn leaves a
        # resumable id behind. The session dir is per-task (the state path already
        # is) so parallel pi workspaces never share a session.
        #
        # The context-reset path (`/clear`) sends `new_session`, which starts a
        # fresh session id within this dir; `_handle_clear_context` overwrites
        # PI_SESSION_ID_STATE_FILE with that new id (read back via get_state) so a
        # later resume targets the post-clear session, not this one.
        session_dir = self.environment.get_state_path() / PI_SESSION_DIR_NAME
        persisted_session_id = get_state_file_contents(self.environment, PI_SESSION_ID_STATE_FILE)
        is_resume = persisted_session_id is not None
        self._session_id = persisted_session_id or generate_id()
        if not is_resume:
            self.environment.write_file(
                str(self.environment.get_state_path() / PI_SESSION_ID_STATE_FILE),
                self._session_id,
            )

        system_prompt = self._build_system_prompt()
        # Point pi at the workspace's Claude-visible skill sources (--skill) and
        # capture the picker's skill names so invocations can be rewritten to
        # pi's /skill: shape. Both derive from the same discover_skills roots so
        # the picker list and pi's loaded set stay in lockstep.
        skill_args = self._build_skill_launch_args()
        self._discovered_skill_names = self._discover_skill_names()
        extension_args = self._install_pinned_extensions()
        # `--session-id` (Sculptor-pinned id, "creating it if missing") is the
        # resume lever, chosen over `--session <id>`: it never errors on an
        # absent/corrupt session (real pi 0.78.0 exits non-zero for an unknown
        # `--session`), so a lost session file degrades to a loud fresh start
        # rather than a crash loop. Pi also tolerates a truncated JSONL tail,
        # resuming the valid prefix. `--no-extensions` disables pi's own
        # extension *discovery* while the explicit `-e <path>` still loads our
        # pinned set — together the immutability guarantee (REQ-EXT-3): only
        # Sculptor's curated, version-pinned extension set loads.
        command = [
            binary,
            "--mode",
            "rpc",
            "--session-dir",
            str(session_dir),
            "--session-id",
            self._session_id,
            "--no-extensions",
            *extension_args,
            "--append-system-prompt",
            system_prompt,
            *skill_args,
        ]
        self._process = self.environment.run_process_in_background(
            command,
            secrets=merged_secrets,
            open_stdin=True,
            # Make pi its own process-group leader so a Stop/shutdown signal
            # cascades to its descendants — including any `background` tool child
            # that did not opt into its own group — mirroring the Claude CLI
            # (process_manager.py). The no-orphan guarantee on shutdown; the
            # background extension's `session_shutdown` handler and Sculptor's
            # per-task in-environment kill (on interrupt) complete the picture.
            isolate_process_group=True,
        )
        if is_resume:
            # Best-effort guard against SILENT context loss: confirm pi actually
            # resumed the session we asked for. Control flow is unchanged either
            # way (`--session-id` cannot crash-loop); a mismatch / empty session
            # is logged loud. Safe to read stdout here because the message-
            # processing thread (the only other reader of the process queue) is
            # not started until after this returns.
            self._verify_resumed_session(self._session_id)
        # Fetch pi's model catalog + current model and surface them onto task
        # state for the switcher. Done here, the sole reader of the process queue
        # before the message-processing thread starts (same constraint as the
        # resume verification above).
        self._fetch_models_into_state()
        self._message_processing_thread = self.concurrency_group.start_new_thread(
            target=self._process_message_queue,
        )

    def _push_message(self, message: Message) -> bool:
        if isinstance(message, ChatInputUserMessage):
            self._input_agent_messages.put(message)
            return True
        if isinstance(message, ClearContextUserMessage):
            # Enqueued on the same FIFO as chat turns so the reset runs strictly
            # between turns (see _handle_clear_context); supports_context_reset.
            self._input_agent_messages.put(message)
            return True
        if isinstance(message, SetModelUserMessage):
            # Enqueued on the same FIFO as chat turns so the switch runs strictly
            # between turns (see _handle_set_model); supports_model_selection.
            self._input_agent_messages.put(message)
            return True
        if isinstance(message, RefreshModelsUserMessage):
            # Enqueued on the same FIFO so the credential re-read + catalog re-emit
            # runs strictly between turns (see _handle_refresh_models), where the
            # get_* RPCs are safe. Broadcast on a global credential change.
            self._input_agent_messages.put(message)
            return True
        if isinstance(message, ResumeAgentResponseRunnerMessage):
            # The previous pi process died mid-turn: the in-flight chat message
            # got a RequestStarted but never a terminal RequestSuccess, so the
            # frontend is stuck "thinking". start() has already resumed the pi
            # session (via --session-id), so the interrupted partial is back in
            # context and the next user turn picks up with full history; here we
            # only resolve the orphaned request so the UI settles on a stopped
            # turn instead of spinning. This mirrors Claude's resume contract at
            # the minimum-viable altitude — pi has no "continue this generation"
            # RPC, and re-prompting could duplicate the partial, so we do not try
            # to auto-continue the dead turn. request_id is the ORIGINAL stuck
            # message (for_user_message_id), which is what the frontend's
            # in-flight request tracks.
            self._output_messages.put(
                RequestSuccessAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=message.for_user_message_id,
                    error=None,
                    interrupted=True,
                )
            )
            return True
        if isinstance(message, InterruptProcessUserMessage):
            self._request_interrupt()
            # Resolve the interrupt request itself: the frontend's POST to
            # /interrupt blocks in `await_message_response` until a
            # RequestComplete carries this message's id, and the StatusPill
            # stays "stopping" until then. The interrupted chat turn resolves
            # separately when pi's abort-induced `agent_end` arrives; this
            # control action is itself never interrupted, hence interrupted=False.
            self._output_messages.put(
                RequestSuccessAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=message.message_id,
                    error=None,
                    interrupted=False,
                )
            )
            return True
        if isinstance(message, UserQuestionAnswerMessage):
            # Mid-turn answer to a backchannel dialog the agent is blocked on:
            # delivered here on the request-handling thread (mirrors Claude's
            # `_try_deliver_answer_to_mcp`), not queued like a new prompt.
            self._deliver_question_answer(message)
            return True
        # Dead-letter: every control message pi supports is handled above
        # (return True), and the base class handles the types in
        # _BASE_CLASS_HANDLED_MESSAGE_TYPES after this False return. Anything else
        # reaching here has no handler and would be dropped silently — likely a
        # frontend capability gate let something through pi cannot do — so log it.
        if not isinstance(message, _BASE_CLASS_HANDLED_MESSAGE_TYPES):
            logger.error(
                "PiAgent dropping unhandled control message {} for task {} — a frontend capability gate should have prevented it",
                type(message).__name__,
                self.task_id,
            )
        return False

    def poll(self) -> int | None:
        thread = self._message_processing_thread
        if thread is not None and thread.exception_raw is not None:
            self._exception = thread.exception_raw
            self._exit_code = AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
        return super().poll()

    def wait(self, timeout: float) -> int:
        if self._exception is not None:
            if self._process is not None:
                self._process.terminate()
            raise AgentCrashed("Agent crashed", exit_code=None, metadata=None) from self._exception

        self._shutdown_event.set()
        # No orphans on shutdown: kill each background child's (detached) process
        # group in the environment. The extension's `session_shutdown` handler is
        # the other half; this is the belt-and-suspenders that does not depend on pi
        # shutting down gracefully. Done before close_stdin so the kills are issued
        # while the environment is still fully up.
        self._cancel_all_background_tasks()
        process = self._process
        if process is not None:
            try:
                self._send_rpc({"type": "abort"})
                process.close_stdin()
            except Exception as e:  # noqa: BLE001
                logger.debug("PiAgent close_stdin failed: {}", e)
            try:
                self._exit_code = process.wait(timeout)
            except Exception as e:  # noqa: BLE001
                logger.debug("PiAgent process wait failed: {}", e)

        thread = self._message_processing_thread
        if thread is not None:
            thread.join(timeout)

        assert self._exit_code is not None, "PiAgent.wait must produce an exit code"
        return self._exit_code

    def _terminate(self, force_kill_seconds: float) -> None:
        self.wait(timeout=force_kill_seconds)

    def _build_system_prompt(self) -> str:
        parts: list[str] = [self.harness.hidden_system_prompt.strip()]
        env_prompt = self.environment.get_system_prompt()
        if env_prompt:
            parts.append(env_prompt.strip())
        if self.system_prompt:
            parts.append(f"<User instructions>\n{self.system_prompt.strip()}\n</User instructions>")
        return "\n\n".join(parts)

    def _discover_skill_names(self) -> frozenset[str]:
        """The workspace's discovered skill names, matching the slash picker.

        Sourced from `discover_skills` (the same authority the `/api/v1/skills`
        endpoint serves the picker), so the rewrite accepts exactly the names a
        user can pick. The names may be plugin-namespaced (`<plugin>:<skill>`);
        `_rewrite_skill_invocation` reduces those to bare names for pi.
        """
        skills = discover_skills(self.environment.get_working_directory(), get_plugin_dirs())
        return frozenset(skill.name for skill in skills)

    def _build_skill_launch_args(self) -> list[str]:
        """Build the repeatable `--skill <path>` flags pointing pi at the
        workspace's Claude-visible skill sources.

        Sources come from `get_skill_source_directories` — the same roots
        `discover_skills` (and so the picker) scans — resolved against this
        agent's environment paths. SKILL.md-directory sources (repo/home
        `.claude/skills`, plugin `skills/`) map onto pi's agentskills.io
        discovery directly. Loose `.claude/commands/*.md` files are not a shape
        pi discovers, so they are wrapped in synthesized SKILL.md dirs (see
        `_synthesize_command_skills`). Missing source dirs are skipped quietly
        (a repo without `.claude/skills` is normal); flag order follows the
        helper's discovery order.
        """
        sources = get_skill_source_directories(
            self.environment.get_working_directory(),
            plugin_dirs=get_plugin_dirs(),
            home_path=self.environment.get_user_home_directory(),
        )
        args: list[str] = []
        command_files: list[Path] = []
        for source in sources:
            if not source.path.is_dir():
                continue
            if source.kind is SkillSourceKind.SKILL_DIR:
                args += ["--skill", str(source.path)]
            else:
                command_files += sorted(source.path.glob("*.md"))
        synthesized_dir = self._synthesize_command_skills(command_files)
        if synthesized_dir is not None:
            args += ["--skill", str(synthesized_dir)]
        return args

    def _synthesize_command_skills(self, command_files: Sequence[Path]) -> Path | None:
        """Wrap loose command-style `.md` files in synthesized SKILL.md dirs pi can load.

        pi discovers skills only as `SKILL.md` directories, not the loose `.md`
        command files Claude also supports (`.claude/commands/*.md`). For each
        such file write a `<state>/pi_skills/<name>/SKILL.md` wrapper and return
        the `pi_skills` parent to hand to a single `--skill`, or None when there
        are no command files. The wrappers live under the per-task state dir —
        outside the repo and outside `~/.claude` — so neither `discover_skills`
        (the picker source) nor pi's own ancestor auto-discovery lists them a
        second time; only the explicit `--skill` loads them. The file stem is
        the skill name (matching `discover_skills`), the body is carried
        through, and a description is synthesized when the command file has none
        (pi refuses to load a skill with no description). First name wins,
        matching `discover_skills`' cross-source precedence.
        """
        if not command_files:
            return None
        skills_root = self.environment.get_state_path() / "pi_skills"
        seen_names: set[str] = set()
        for command_file in command_files:
            name = command_file.stem
            if name in seen_names:
                continue
            try:
                body = command_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.debug("PiAgent skipping unreadable command file {}: {}", command_file, e)
                continue
            seen_names.add(name)
            description = parse_command_frontmatter(body) or f"Project command '{name}' (from {command_file.name})."
            skill_md = skills_root / name / "SKILL.md"
            skill_md.parent.mkdir(parents=True, exist_ok=True)
            skill_md.write_text(_render_synthesized_skill(name, description, body), encoding="utf-8")
        return skills_root if seen_names else None

    def _install_pinned_extensions(self) -> list[str]:
        """Materialize the pinned extension set and return its `-e <path>` args.

        The extension source ships as package data next to this module
        (`extensions/`, see pyproject.toml), so it resolves in an installed
        build as well as a repo checkout. We write it into the per-task state
        dir via `environment.write_file` so the pi process can read it whatever
        the environment type (local / container / remote) — a repo-relative path
        would not survive packaging, the trap this avoids.
        """
        extension_args: list[str] = []
        loaded_paths: list[str] = []
        state_path = self.environment.get_state_path()
        for filename in (
            _BACKCHANNEL_EXTENSION_FILENAME,
            _SUBAGENT_EXTENSION_FILENAME,
            _BACKGROUND_EXTENSION_FILENAME,
        ):
            content = (_EXTENSIONS_SOURCE_DIR / filename).read_text(encoding="utf-8")
            destination = state_path / filename
            self.environment.write_file(str(destination), content)
            extension_args.extend(["-e", str(destination)])
            loaded_paths.append(str(destination))
        self._loaded_extension_paths = tuple(loaded_paths)
        return extension_args

    def _collect_api_key_secrets(self) -> dict[str, Secret]:
        config = get_user_config_instance()
        collected: dict[str, Secret] = {}
        for name in config.pi.api_key_env_var_names:
            value = os.environ.get(name)
            if value:
                collected[name] = Secret(value)
        return collected

    def _check_pi_version(self, binary: str) -> str:
        try:
            result = self.environment.run_process_to_completion(
                [binary, "--version"],
                secrets={},
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            raise PiVersionMismatchError(
                detected_version="<unknown>", pinned_version=PI_VERSION_RANGE.recommended_version
            ) from e
        # WHY: real pi emits --version to stderr, not stdout; feed both channels.
        version = parse_pi_version(f"{result.stdout}\n{result.stderr}")
        if version is None:
            raise PiVersionMismatchError(
                detected_version="<unparseable>",
                pinned_version=PI_VERSION_RANGE.recommended_version,
            )
        return version

    def _send_rpc(self, payload: Mapping[str, Any]) -> None:
        process = self._process
        if process is None:
            return
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        # The prompt pump, answer delivery, and wait()'s abort can all write
        # stdin from different threads; serialize so lines never interleave.
        with self._send_lock:
            try:
                process.write_stdin(line)
            except Exception as e:  # noqa: BLE001
                logger.debug("PiAgent write_stdin failed: {}", e)

    def _consume_until_command_response(self, command: str, command_id: str, timeout: float) -> RpcResponse | None:
        """Drain pi's stdout until the `response` for (command, command_id) arrives.

        Correlates by id (RPC §5.1), skipping any session events pi emits
        meanwhile; returns None on timeout / process exit. Used for the
        between-turns control commands this harness issues directly (`get_state`,
        `new_session`). It reads the process queue, so it is ONLY safe when it is
        the SOLE reader of that queue: before the message-processing thread starts
        (start-time resume verification), or from within that thread between turns
        (the context-reset handler). Never call it while a turn is streaming — the
        turn pump (`_consume_until_turn_end`) would race it for the same queue.
        """
        process = self._process
        if process is None:
            return None
        out_queue = process.get_queue()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.is_finished() and out_queue.empty():
                return None
            try:
                line, is_stdout = out_queue.get(timeout=_STDOUT_QUEUE_POLL_SECONDS)
            except Empty:
                continue
            if not is_stdout:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            parsed = parse_rpc_message(event)
            if isinstance(parsed, RpcResponse) and parsed.command == command and parsed.id == command_id:
                return parsed
        return None

    def _request_state_blocking(self, timeout: float = 10.0) -> dict[str, Any] | None:
        """Send `get_state` and return pi's reported `RpcSessionState` data (RPC §5.1).

        Returns None on timeout / process exit / no matching response. Shares the
        sole-reader safety constraint of `_consume_until_command_response`.
        """
        if self._process is None:
            return None
        request_id = generate_id()
        self._send_rpc({"type": "get_state", "id": request_id})
        response = self._consume_until_command_response("get_state", request_id, timeout)
        if response is None or not isinstance(response.data, dict):
            return None
        return response.data

    def _verify_resumed_session(self, expected_session_id: str) -> None:
        """Confirm pi resumed the persisted session; log loud on any anomaly.

        Pi adopts the `--session-id` we pass verbatim, so a reported id that
        differs would signal a pi-behavior change; an empty session
        (`messageCount == 0`) on a resume launch means the on-disk session was
        lost (deleted / unreadable) and prior context is gone. Neither is fatal —
        pi carries on with a fresh session of the same id — but both are logged
        at error so context loss is never silent (the failure mode to avoid).
        """
        state = self._request_state_blocking()
        if state is None:
            logger.error(
                "PiAgent could not verify resumed pi session {} (no get_state response); continuing",
                expected_session_id,
            )
            return
        reported_id = state.get("sessionId")
        message_count = state.get("messageCount")
        if reported_id != expected_session_id:
            logger.error(
                "PiAgent resume mismatch: asked pi to resume session {} but it reports {}; context may be lost",
                expected_session_id,
                reported_id,
            )
        elif message_count == 0:
            logger.error(
                "PiAgent expected to resume pi session {} but it is empty (messageCount=0) — the on-disk session was lost; continuing with a fresh session",
                expected_session_id,
            )
        else:
            logger.info("PiAgent resumed pi session {} (messageCount={})", expected_session_id, message_count)

    def _request_available_models_blocking(
        self, timeout: float = _MODEL_FETCH_TIMEOUT_SECONDS
    ) -> list[dict[str, Any]]:
        """Send `get_available_models` and return pi's raw `data.models` list.

        Returns `[]` on timeout / process exit / a malformed payload. Shares the
        sole-reader safety constraint of `_consume_until_command_response`.
        """
        if self._process is None:
            return []
        request_id = generate_id()
        self._send_rpc({"type": "get_available_models", "id": request_id})
        response = self._consume_until_command_response("get_available_models", request_id, timeout)
        if response is None or not isinstance(response.data, dict):
            return []
        models = response.data.get("models")
        if not isinstance(models, list):
            return []
        return [m for m in models if isinstance(m, dict)]

    def _request_set_model_blocking(
        self, provider: str, model_id: str, timeout: float = _MODEL_FETCH_TIMEOUT_SECONDS
    ) -> ModelOption | None:
        """Send `set_model` and return pi's new current model, or None on failure.

        The non-raising counterpart to `_handle_set_model`'s RPC core, used by the
        internal auto-reselect (`_reselect_unauthenticated_current_model`). Shares
        the sole-reader constraint of `_consume_until_command_response`, so it is
        only safe between turns.
        """
        if self._process is None:
            return None
        command_id = generate_id()
        self._send_rpc({"type": "set_model", "id": command_id, "provider": provider, "modelId": model_id})
        response = self._consume_until_command_response("set_model", command_id, timeout)
        if response is None or not response.success:
            return None
        new_model = _model_option_from_pi(response.data) if isinstance(response.data, dict) else None
        return new_model or ModelOption(provider=provider, model_id=model_id, display_name=model_id)

    def _reselect_unauthenticated_current_model(
        self, current_model: ModelOption, curated: list[ModelOption], authenticated: set[str]
    ) -> ModelOption:
        """Switch off a current model whose provider is no longer authenticated.

        pi's catalog gates on credential presence, so disconnecting a provider can
        leave the agent pointed at a model it can no longer run — and because the
        current model is retained in `curated`, the switcher otherwise stays stuck on
        it. If an authenticated model is available, switch to the first (newest-first)
        one so the user is not stranded. Best-effort: a failed switch leaves the
        current model unchanged. Only call when `current_model.provider` is already
        known to be unauthenticated, and only after a successful catalog fetch (so pi
        is proven responsive and the `set_model` write will not block).
        """
        replacement = next((option for option in curated if option.provider in authenticated), None)
        if replacement is None:
            logger.info(
                "PiAgent current model {} is no longer authenticated and no authenticated model is available to switch to",
                current_model.model_id,
            )
            return current_model
        new_model = self._request_set_model_blocking(replacement.provider, replacement.model_id)
        if new_model is None:
            logger.info(
                "PiAgent could not switch off deauthenticated model {}; leaving it selected", current_model.model_id
            )
            return current_model
        logger.info(
            "PiAgent switched off deauthenticated model {} to authenticated {}",
            current_model.model_id,
            new_model.model_id,
        )
        return new_model

    def _fetch_models_into_state(self) -> None:
        """Fetch pi's model catalog + current model and surface them onto task state.

        Issues `get_available_models` and `get_state` (sole reader of the process
        queue, before the message thread starts), maps the raw Model dicts to
        `ModelOption`s, curates them (`_curate_models`), and emits a
        `ModelsAvailableAgentMessage` the run-agent handler maps onto
        `AgentTaskStateV2.available_models` / `current_model`. Best-effort: an empty
        catalog leaves the switcher to the frontend's built-in fallback list.
        """
        raw_models = self._request_available_models_blocking()
        state = self._request_state_blocking()
        current_raw = state.get("model") if isinstance(state, dict) else None
        current_model = _model_option_from_pi(current_raw) if isinstance(current_raw, dict) else None
        options: list[ModelOption] = []
        for raw in raw_models:
            option = _model_option_from_pi(raw)
            if option is not None:
                options.append(option)
        authenticated = compute_authenticated_provider_ids()
        curated = _curate_models(options, current_model, authenticated)
        # Don't strand the agent on a model whose provider was just deauthorized
        # (e.g. the user disconnected it): switch to an authenticated model and
        # re-curate so the now-unusable model drops out of the switcher. Safe here
        # because the fetch above already proved pi responsive.
        if current_model is not None and current_model.provider not in authenticated:
            current_model = self._reselect_unauthenticated_current_model(current_model, curated, authenticated)
            curated = _curate_models(options, current_model, authenticated)
        if not curated and current_model is None:
            logger.info("PiAgent get_available_models returned no usable models; switcher will fall back to defaults")
            return
        # Cache the catalog so a later set_model can re-emit it with the new
        # current model.
        self._available_models = tuple(curated)
        self._output_messages.put(
            ModelsAvailableAgentMessage(
                message_id=AgentMessageID(),
                available_models=self._available_models,
                current_model=current_model,
            )
        )
        logger.info(
            "PiAgent fetched {} model(s) from pi at start; current model={}",
            len(self._available_models),
            current_model.model_id if current_model is not None else None,
        )

    def fetch_available_models_probe(
        self, secrets: Mapping[str, str | Secret]
    ) -> tuple[list[ModelOption], ModelOption | None]:
        """Fetch + curate pi's catalog via a short-lived probe, without starting the agent.

        Lets the run-agent handler populate the switcher for a fresh pi agent
        BEFORE the first message, when `start()` (and its
        `_fetch_models_into_state`) has not run yet. Launches a minimal `pi
        --mode rpc` process against a throwaway probe session
        (`PI_PROBE_SESSION_DIR_NAME`, a distinct `--session-id`) with no
        extensions / skills / system prompt — `get_available_models` and
        `get_state` need none — issues those two RPCs as the sole reader of the
        process queue, then shuts the probe down before returning the curated
        `list[ModelOption]` + current `ModelOption | None`.

        `secrets` are the backend-env + PATH the caller would pass `start()` (so
        the probe resolves the same `pi` and reaches the same provider); the
        probe merges its own api-key secrets on top, mirroring `start()`. The
        probe does NOT call `start()`, so `self._secrets` is not set here.

        Best-effort, like `_fetch_models_into_state`: on any failure (no binary,
        version mismatch, timeout, no response) it logs and returns
        `([], None)`, never raising — the switcher then falls back to the
        frontend's built-in list, exactly as before this probe existed. Does NOT
        touch the agent lifecycle: it neither sets `self._process` for the
        message loop nor mints/persists the real session id, so the normal
        `start()` path is unaffected.
        """
        binary = self.environment.get_tool_binary_path(Dependency.PI)
        if binary is None:
            logger.info("PiAgent model probe skipped: pi binary not found; switcher will fall back to defaults")
            return [], None
        detected_version = self._check_pi_version_for_probe(binary)
        if detected_version is None or not _pi_version_in_range(detected_version):
            logger.info(
                "PiAgent model probe skipped: pi version {} out of range; switcher will fall back to defaults",
                detected_version,
            )
            return [], None

        pi_secrets = self._collect_api_key_secrets()
        merged_secrets: dict[str, str | Secret] = {**secrets, **pi_secrets}
        probe_session_dir = self.environment.get_state_path() / PI_PROBE_SESSION_DIR_NAME
        command = [
            binary,
            "--mode",
            "rpc",
            "--session-dir",
            str(probe_session_dir),
            "--session-id",
            f"probe-{generate_id()}",
            "--no-extensions",
        ]
        probe_process = None
        try:
            probe_process = self.environment.run_process_in_background(
                command,
                secrets=merged_secrets,
                open_stdin=True,
            )
            # Point the blocking RPC helpers at the probe process for the duration
            # of the fetch only; the message loop never runs here, so there is no
            # concurrent reader of this queue.
            self._process = probe_process
            raw_models = self._request_available_models_blocking()
            state = self._request_state_blocking()
        except Exception as e:  # noqa: BLE001
            logger.info("PiAgent model probe failed ({}); switcher will fall back to defaults", e)
            self._shutdown_probe_process(probe_process)
            self._process = None
            return [], None

        self._shutdown_probe_process(probe_process)
        self._process = None

        current_raw = state.get("model") if isinstance(state, dict) else None
        current_model = _model_option_from_pi(current_raw) if isinstance(current_raw, dict) else None
        options: list[ModelOption] = []
        for raw in raw_models:
            option = _model_option_from_pi(raw)
            if option is not None:
                options.append(option)
        curated = _curate_models(options, current_model, compute_authenticated_provider_ids())
        if not curated and current_model is None:
            logger.info("PiAgent model probe found no usable models; switcher will fall back to defaults")
            return [], None
        logger.info(
            "PiAgent model probe fetched {} model(s); current model={}",
            len(curated),
            current_model.model_id if current_model is not None else None,
        )
        return curated, current_model

    def _check_pi_version_for_probe(self, binary: str) -> str | None:
        """`_check_pi_version` for the probe: return None instead of raising.

        The probe is best-effort, so a failed / unparseable version check yields
        an empty catalog (caller falls back to defaults) rather than the
        `PiVersionMismatchError` `start()` raises to fail the run loudly.
        """
        try:
            return self._check_pi_version(binary)
        except PiVersionMismatchError:
            return None

    def _shutdown_probe_process(self, process: Any) -> None:
        """Close stdin then terminate the catalog probe's pi process.

        Pi exits on stdin EOF (Sculptor closes stdin at shutdown); terminate is
        the backstop if it lingers. Best-effort — the probe is throwaway, so any
        teardown error is logged and swallowed rather than failing the fetch.
        """
        if process is None:
            return
        try:
            process.close_stdin()
        except Exception as e:  # noqa: BLE001
            logger.debug("PiAgent model probe close_stdin failed: {}", e)
        try:
            process.terminate()
        except Exception as e:  # noqa: BLE001
            logger.debug("PiAgent model probe terminate failed: {}", e)

    def _request_interrupt(self) -> None:
        """Halt the in-flight pi turn via pi's `abort` command (supports_interruption).

        Runs on the request-handling thread, concurrently with the
        message-processing thread draining the turn. Sets the base
        `_was_interrupted` event (the wrapper's success path reads-and-clears it
        to surface `RequestSuccess(interrupted=True)`) and an interrupt-pending
        flag the dispatcher consults so the abort-induced `stopReason:"aborted"`
        finalizes the partial response instead of raising `PiCrashError`. The
        turn keeps draining inside `_handle_user_message` until pi's `agent_end`;
        if that never arrives, the escalation ladder SIGTERMs pi so the
        process-exit fallback in `_consume_until_turn_end` still resolves the turn.

        When no turn is in flight the abort is a no-op (pi is idle) and no
        turn-end will arrive, so Stop instead reconciles any orphaned in-flight
        request directly — the idle-but-RUNNING escape hatch.
        """
        self._was_interrupted.set()
        self._interrupt_pending.set()
        self._send_rpc({"type": "abort", "id": generate_id()})
        # Arm escalation only when a turn is actually in flight: an interrupt
        # that raced in between turns must not force-kill a healthy idle pi.
        if self._turn_in_flight.is_set():
            cancel = Event()
            self._escalation_cancel = cancel
            self.concurrency_group.start_new_thread(
                target=self._await_interrupt_escalation,
                args=(cancel,),
            )
        else:
            # The abort above is a no-op with pi idle, and no turn-end will
            # arrive to resolve the request, so reconcile any orphaned turn here.
            self._resolve_in_flight_request_as_interrupted()
            # The reconciliation emits its own terminal RequestSuccess directly,
            # so no in-flight turn will consume these flags. A chat turn resets
            # interrupt state at its start, but the between-turns control paths
            # read it via `_handle_user_message` without resetting it — so clear
            # it here, or a lingering flag mislabels the next such request as
            # interrupted.
            self._was_interrupted.clear()
            self._interrupt_pending.clear()

    def _resolve_in_flight_request_as_interrupted(self) -> None:
        """Emit a terminal RequestSuccess(interrupted=True) for the in-flight
        request, if any, so the frontend's in-progress chat message resolves
        instead of staying stuck "thinking".

        Used by the interrupt path when no turn is draining pi's stdout: the
        turn's own terminal message can no longer be relied upon (it was never
        emitted, or its process is gone). No-ops when no request is being
        tracked (`_in_flight_request_id is None`). Mirrors
        ClaudeProcessManager._resolve_in_flight_request_as_interrupted.
        """
        in_flight_request_id = self._in_flight_request_id
        if in_flight_request_id is not None:
            self._output_messages.put(
                RequestSuccessAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=in_flight_request_id,
                    error=None,
                    interrupted=True,
                )
            )

    def _await_interrupt_escalation(self, cancel: Event) -> None:
        """Wait out the grace window, then SIGTERM pi if the turn hasn't ended."""
        if cancel.wait(timeout=_INTERRUPT_ESCALATION_GRACE_SECONDS):
            return
        self._escalate_interrupt()

    def _escalate_interrupt(self) -> None:
        """SIGTERM pi when the abort produced no `agent_end` within the grace window.

        `_consume_until_turn_end`'s `process.is_finished()` exit path then resolves
        the turn. A no-op if the turn already ended after the abort
        (`_interrupt_pending` cleared) or the process is already gone.
        """
        if not self._interrupt_pending.is_set():
            return
        process = self._process
        if process is None or process.is_finished():
            return
        logger.info(
            "PiAgent abort grace window ({}s) expired without agent_end; escalating to SIGTERM",
            _INTERRUPT_ESCALATION_GRACE_SECONDS,
        )
        process.terminate()

    def _cancel_interrupt_escalation(self) -> None:
        cancel = self._escalation_cancel
        if cancel is not None:
            cancel.set()

    def _is_abort_expected(self) -> bool:
        """Whether a `stopReason:"aborted"` message is the expected interrupted boundary.

        True when we asked pi to stop — an interrupt is pending, or we are
        shutting down (`wait()` sends `abort` then closes stdin). Otherwise an
        `aborted` message is an unexpected pi failure and must raise
        `PiCrashError` (see `_handle_message_end` / `_handle_agent_end`).
        """
        return self._interrupt_pending.is_set() or self._shutdown_event.is_set()

    def _process_message_queue(self) -> None:
        while not self._shutdown_event.is_set():
            # No task can start during an idle wait: tasks launch only from within a turn.
            has_pending_tasks = self._has_background_tasks()
            timeout = _TASK_POLL_SECONDS if has_pending_tasks else _IDLE_WAIT_SECONDS
            try:
                message = self._input_agent_messages.get(timeout=timeout)
            except Empty:
                # Sculptor only drains pi's stdout during a turn; when a background or
                # sub-agent task is running, surface its completion live while we're idle.
                if has_pending_tasks:
                    self._drain_idle_background_events()
                continue
            if isinstance(message, ClearContextUserMessage):
                # Between-turns reset: this loop processes one message at a time,
                # so reaching here means any prior turn already ended.
                self._handle_clear_context(message)
                continue
            if isinstance(message, SetModelUserMessage):
                # Between-turns model switch (see _handle_set_model).
                self._handle_set_model(message)
                continue
            if isinstance(message, RefreshModelsUserMessage):
                # Between-turns credential re-read + catalog re-emit (see
                # _handle_refresh_models).
                self._handle_refresh_models(message)
                continue
            self._run_prompt_turn(message)

    def _has_background_tasks(self) -> bool:
        with self._background_tasks_lock:
            if self._background_tasks or self._subagent_tasks:
                return True
        return self._is_awaiting_reaction()

    def _is_awaiting_reaction(self) -> bool:
        """True while a completion's auto-resume reaction turn is still expected.

        Bounded by a deadline so a reaction that never arrives (the wake-up
        errored) cannot keep the idle-drain polling forever.
        """
        if self._awaiting_reaction_count <= 0:
            return False
        if time.monotonic() >= self._awaiting_reaction_deadline:
            self._awaiting_reaction_count = 0
            return False
        return True

    def _note_awaiting_reaction(self) -> None:
        """Record a surfaced completion so the idle-drain stays alive to consume the
        reaction turn the extension triggers via `sendUserMessage`."""
        self._awaiting_reaction_count += 1
        self._awaiting_reaction_deadline = time.monotonic() + _REACTION_WINDOW_SECONDS

    def _run_prompt_turn(self, message: ChatInputUserMessage) -> None:
        # Track this turn's request id so an interrupt arriving with no turn in
        # flight can reconcile it (see _resolve_in_flight_request_as_interrupted).
        # Never cleared on turn end: a turn orphaned without a terminal completion
        # leaves this set so Stop can still settle it.
        self._in_flight_request_id = get_turn_request_id(message)
        self._update_plan_mode_from_message(message)
        with self._handle_user_message(message):
            # A fresh turn starts un-interrupted: clear interrupt state left by an
            # interrupt that raced in with no turn in flight, which would otherwise
            # mis-mark this turn as interrupted.
            self._was_interrupted.clear()
            self._interrupt_pending.clear()
            self._cancel_interrupt_escalation()
            self._turn_in_flight.set()
            turn_failed = False
            try:
                self._consume_turn_with_transient_retry(message)
            except BaseException:
                turn_failed = True
                raise
            finally:
                # Turn over: stand down escalation and drop interrupt-pending so a
                # late grace-window thread can't SIGTERM the next turn's pi.
                self._turn_in_flight.clear()
                self._interrupt_pending.clear()
                self._cancel_interrupt_escalation()
                # Finalize any backchannel answer delivered mid-turn (its
                # RequestSuccess was deferred to here so the post-answer content
                # reached the frontend first). Runs on the failure path too, so the
                # answer's request resolves instead of pinning the frontend
                # "thinking" (mirrors Claude).
                self._finalize_pending_answers(interrupted=turn_failed)

    def _consume_turn_with_transient_retry(self, message: ChatInputUserMessage) -> None:
        """Drive one user turn, retrying KNOWN-TRANSIENT provider failures with backoff.

        A turn whose assistant run ends in a transient provider error
        (`_PiTransientTurnError` — overloaded / rate-limit / 5xx / timeout) is
        re-prompted with exponential backoff + jitter rather than crashing the
        agent, up to `_PI_TRANSIENT_MAX_RETRIES` times. The re-prompt carries the
        same content under a fresh prompt id (pi correlates a `prompt` response by
        id). When the budget is exhausted — or the agent is asked to stop (shutdown
        or a user interrupt) — the turn fails with the non-fatal, retryable
        `AgentTransientError` (surfaced as a RequestFailure the user can re-run)
        instead of `PiCrashError`. A non-transient error still raises `PiCrashError`
        from the dispatcher and is not retried here.
        """
        payload = self._build_prompt_payload(generate_id(), message)
        attempt = 0
        while True:
            self._send_rpc(payload)
            try:
                self._consume_until_turn_end(payload["id"])
                return
            except _PiTransientTurnError as transient:
                attempt += 1
                should_give_up = attempt > _PI_TRANSIENT_MAX_RETRIES or self._is_abort_expected()
                if not should_give_up:
                    logger.info(
                        "PiAgent transient provider error on turn (retry {}/{}); backing off then re-prompting: {}",
                        attempt,
                        _PI_TRANSIENT_MAX_RETRIES,
                        transient.reason,
                    )
                    self._sleep_before_transient_retry(attempt)
                    # A Stop or shutdown landed during the backoff: don't re-prompt.
                    should_give_up = self._is_abort_expected()
                if should_give_up:
                    raise AgentTransientError(transient.reason, exit_code=None, metadata=None) from transient
                payload = {**payload, "id": generate_id()}

    def _transient_retry_delay_seconds(self, attempt: int) -> float:
        """Exponential-backoff-with-equal-jitter delay before transient retry `attempt`.

        Grows as base*2**(attempt-1), capped at the max; equal jitter spreads the
        delay across [half, full] of that cap so concurrent agents hitting the same
        provider surge do not retry in lockstep.
        """
        capped = min(
            _PI_TRANSIENT_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
            _PI_TRANSIENT_RETRY_MAX_DELAY_SECONDS,
        )
        return capped / 2 + random.uniform(0.0, capped / 2)

    def _sleep_before_transient_retry(self, attempt: int) -> None:
        """Block for the backoff delay, woken early by shutdown or a user interrupt.

        Polls in short slices so a Stop pressed mid-backoff (which sets
        `_interrupt_pending`, not `_shutdown_event`) is honored within a poll
        interval instead of waiting out the full delay; the retry loop then bails
        to `AgentTransientError`. Waiting on `_shutdown_event` makes a shutdown wake
        the slice immediately.
        """
        deadline = time.monotonic() + self._transient_retry_delay_seconds(attempt)
        while not self._is_abort_expected():
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return
            if self._shutdown_event.wait(timeout=min(remaining, _STDOUT_QUEUE_POLL_SECONDS)):
                return

    def _update_plan_mode_from_message(self, message: ChatInputUserMessage) -> None:
        """Track plan mode across turns from the chat input's toggle flags.

        Mirrors `ClaudeProcessManager` (`process_manager.py`): entering sets the
        flag, leaving clears it; plan approval clears it later in
        `_deliver_question_answer`.
        """
        if message.enter_plan_mode:
            self._is_in_plan_mode = True
        elif message.exit_plan_mode:
            self._is_in_plan_mode = False

    def _build_prompt_payload(self, prompt_id: str, message: ChatInputUserMessage) -> dict[str, Any]:
        """Assemble the `prompt` command for one user turn, attachments included.

        Attachments (`ChatInputUserMessage.files`) are split by type: images
        ride the `images[]` field as base64 + mimeType; everything else is
        presented as paths in the prompt text for pi to read with its own
        `read` tool. See `prompt_assembly` for the helpers.
        """
        saved_paths = save_attachments_to_environment(self.environment, message.files)
        image_paths, path_attachments = split_image_and_path_attachments(saved_paths)
        prompt_text = build_attachment_instructions(path_attachments) + self._build_prompt_text(message)
        payload: dict[str, Any] = {"type": "prompt", "id": prompt_id, "message": prompt_text}
        if image_paths:
            # No per-model image-capability gating here yet, only the
            # harness-level "pi can carry images" flag. When per-model gating is
            # added it belongs at this assembly site, mirroring the frontend's
            # `getModelCapabilities` map (`frontend/src/.../modelCapabilities.ts`).
            payload["images"] = [build_image_block(path, self._read_attachment_bytes(path)) for path in image_paths]
        return payload

    def _build_prompt_text(self, message: ChatInputUserMessage) -> str:
        """The user text with the skill-invocation rewrite, plus the plan-mode
        preamble while in plan mode."""
        text = _rewrite_skill_invocation(message.text, self._discovered_skill_names)
        if self._is_in_plan_mode:
            return f"{_PLAN_MODE_PROMPT_PREFIX}{text}"
        return text

    def _read_attachment_bytes(self, path: str) -> bytes:
        """Read a saved attachment's bytes from the environment copy."""
        content = self.environment.read_file(path, mode="rb")
        assert isinstance(content, bytes), "binary read must return bytes"
        return content

    def _finalize_pending_answers(self, interrupted: bool) -> None:
        """Emit the deferred RequestSuccess for answers delivered this turn.

        Deferred from `_deliver_question_answer` to the turn boundary so the
        post-answer content reaches the frontend's in-progress message before it
        is finalized — mirrors Claude's `_process_single_message` finally block.
        """
        with self._backchannel_lock:
            pending = self._pending_answer_request_ids
            self._pending_answer_request_ids = []
            self._pending_ui_request_id = None
        for request_id in pending:
            self._output_messages.put(
                RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=request_id, interrupted=interrupted)
            )

    def _handle_clear_context(self, message: ClearContextUserMessage) -> None:
        """Reset the conversation in-process via pi's `new_session` (`/clear`).

        Routed through the `_input_agent_messages` FIFO like chat turns, so it runs
        between turns: a `/clear` arriving mid-turn waits for the in-flight turn's
        `agent_end` before `new_session` is sent. The clear-context endpoint's
        `await_message_response` resolves on the terminal request message
        `_handle_user_message` emits — RequestSuccess on a clean reset,
        RequestFailure on the error path below.

        `new_session` clears history while preserving the model and thinking-level
        selections (no process restart). It mints a fresh session id; since Sculptor
        resumes pi by id (`supports_session_resume`), that id is read back and
        persisted (`_persist_post_clear_session_id`) so a later resume targets the
        post-clear session. A `success:false` response, a `data.cancelled:true` veto
        (an extension's `session_before_switch`), or no acknowledgement within
        `_CLEAR_CONTEXT_TIMEOUT_SECONDS` is a failed reset, raised as
        `PiContextResetError` (an `AgentClientError`, so the agent keeps running).
        """
        with self._handle_user_message(message):
            command_id = generate_id()
            self._send_rpc({"type": "new_session", "id": command_id})
            response = self._consume_until_command_response(
                "new_session", command_id, timeout=_CLEAR_CONTEXT_TIMEOUT_SECONDS
            )
            if response is None:
                raise PiContextResetError(
                    "pi did not acknowledge new_session within the timeout", exit_code=None, metadata=None
                )
            if not response.success:
                raise PiContextResetError(response.error or "pi rejected new_session", exit_code=None, metadata=None)
            if response.data is not None and response.data.get("cancelled"):
                raise PiContextResetError(
                    "pi cancelled new_session (an extension vetoed the context reset)",
                    exit_code=None,
                    metadata=None,
                )
            self._persist_post_clear_session_id()
            # Same ContextClearedMessage as Claude's clear — drives the "Context Cleared" chip.
            self._output_messages.put(ContextClearedMessage(message_id=AgentMessageID()))

    def _persist_post_clear_session_id(self) -> None:
        """After a successful `new_session`, persist pi's new session id.

        `new_session` mints a fresh session id; a later resume must target it (see
        `start`). Read it back via `get_state` and overwrite PI_SESSION_ID_STATE_FILE.
        If it cannot be read (no/empty `get_state` response), log and keep the old id
        — the reset still applied to the running process.
        """
        state = self._request_state_blocking()
        new_session_id = state.get("sessionId") if state is not None else None
        if not isinstance(new_session_id, str) or not new_session_id:
            logger.error(
                "PiAgent could not read the post-clear pi session id (no get_state response); "
                + "a later resume may regress to the pre-clear session",
            )
            return
        self._session_id = new_session_id
        self.environment.write_file(
            str(self.environment.get_state_path() / PI_SESSION_ID_STATE_FILE),
            new_session_id,
        )
        logger.info("PiAgent persisted post-clear pi session id {}", new_session_id)

    def _handle_set_model(self, message: SetModelUserMessage) -> None:
        """Switch pi's model via the `set_model` RPC (supports_model_selection).

        Routed through the `_input_agent_messages` FIFO so it runs between turns,
        where `_consume_until_command_response` is safe. `set_model` is
        session-level and persists for later turns. On success pi returns the new
        Model; we re-emit a `ModelsAvailableAgentMessage` carrier (same catalog,
        new current model) so the persisted current model and the switcher's
        selection follow. A `success:false` response (e.g. `Model not found`) or
        no acknowledgement is raised as `PiSetModelError`, leaving the current
        model unchanged.
        """
        with self._handle_user_message(message):
            command_id = generate_id()
            self._send_rpc(
                {"type": "set_model", "id": command_id, "provider": message.provider, "modelId": message.model_id}
            )
            response = self._consume_until_command_response(
                "set_model", command_id, timeout=_MODEL_FETCH_TIMEOUT_SECONDS
            )
            if response is None:
                raise PiSetModelError(
                    "pi did not acknowledge set_model within the timeout", exit_code=None, metadata=None
                )
            if not response.success:
                raise PiSetModelError(
                    response.error or f"pi rejected set_model for {message.provider}/{message.model_id}",
                    exit_code=None,
                    metadata=None,
                )
            # Prefer pi's returned Model (authoritative id/display name); fall back
            # to the requested identity if pi omits it.
            new_model = _model_option_from_pi(response.data) if isinstance(response.data, dict) else None
            if new_model is None:
                new_model = ModelOption(
                    provider=message.provider, model_id=message.model_id, display_name=message.model_id
                )
            logger.info(
                "PiAgent set_model applied: requested {}/{}, pi reports {}",
                message.provider,
                message.model_id,
                new_model.model_id,
            )
            self._output_messages.put(
                ModelsAvailableAgentMessage(
                    message_id=AgentMessageID(),
                    available_models=self._available_models,
                    current_model=new_model,
                )
            )

    def _handle_refresh_models(self, message: RefreshModelsUserMessage) -> None:
        """Re-fetch pi's catalog and re-emit it after a global credential change.

        Routed through the `_input_agent_messages` FIFO so it runs between turns,
        where `get_available_models` / `get_state` are safe. Reuses
        `_fetch_models_into_state` so the authenticated-set filter applied inside
        that shared path applies here for free. Best-effort and fire-and-forget: a
        re-fetch that finds nothing leaves the cached catalog as-is rather than
        blanking it.
        """
        del message
        self._fetch_models_into_state()

    def _consume_until_turn_end(self, prompt_id: str = "") -> None:
        """Drive pi's stdout until the current agent run terminates.

        Top-level dispatch routes on `event["type"]` into three lanes:
        `response` (command-ACK; correlate by `id`; `success: false` on
        the outstanding `prompt` raises `PiCrashError`),
        `extension_ui_request` (the backchannel extension's blocking dialogs →
        AskUserQuestion; the turn stays open until the answer is posted back),
        and everything else (the `AgentSessionEvent` union, dispatched
        per-`type`).
        """
        process = self._process
        assert process is not None
        out_queue = process.get_queue()
        state = _TurnState(prompt_id=prompt_id)

        try:
            while not self._shutdown_event.is_set():
                if process.is_finished() and out_queue.empty():
                    return
                try:
                    line, is_stdout = out_queue.get(timeout=_STDOUT_QUEUE_POLL_SECONDS)
                except Empty:
                    continue
                if not is_stdout:
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    event = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.debug("PiAgent ignoring non-JSON stdout line: {}", stripped)
                    continue
                if not isinstance(event, dict):
                    logger.debug("PiAgent ignoring non-object stdout payload: {}", event)
                    continue
                # Parse once at the boundary: the three lanes pi multiplexes
                # (`response`, `extension_ui_request`, session events) become typed
                # variants. Unrecognized / malformed payloads parse to
                # ParsedUnknownEvent and are discarded (RPC §5.3 forward-compat).
                if self._dispatch_event(parse_rpc_message(event), state):
                    return
        finally:
            # Stick-prevention: a compaction_start with no matching
            # compaction_end (process died mid-compaction, or a PiCrashError
            # raised before the end arrived) would otherwise leave
            # is_auto_compacting stuck True — derived.py scans messages in
            # reverse for the latest AutoCompacting*. Emit the Done so the
            # "Compacting" pill always clears, on every exit path (normal
            # agent_end, process exit, raised error, shutdown).
            if state.compaction_open:
                self._output_messages.put(AutoCompactingDoneAgentMessage(message_id=AgentMessageID()))

    def _handle_response_event(self, parsed: RpcResponse, state: _TurnState) -> None:
        """Process a top-level `response` envelope (correlated by `id`, RPC §5.1).

        Failure on the outstanding `prompt` ID — i.e. preflight rejection
        (missing API key, unknown model, validation error) — raises
        `PiCrashError`; pi emits no session events after a preflight
        failure so the dispatcher cannot wait for `agent_end`. Other
        responses (including the `abort` ack and uncorrelated parse-error
        responses) are logged and ignored. Responses correlate by `id`, not
        arrival order (RPC §5.1).
        """
        if parsed.command == "prompt" and parsed.id == state.prompt_id and not parsed.success:
            message = humanize_pi_failure_reason(parsed.error) if parsed.error else "pi rejected the prompt"
            raise PiCrashError(message, exit_code=None, metadata=None)
        logger.debug("PiAgent received response: command={} success={}", parsed.command, parsed.success)

    def _dispatch_event(self, parsed: ParsedRpcMessage, state: _TurnState) -> bool:
        """Dispatch one parsed RPC message. Returns True when the turn ends.

        A single `match` over the typed union makes the three lanes explicit:
        `response` (correlated by `id`), `extension_ui_request` (the backchannel
        extension's dialogs → AskUserQuestion), and the session-event union. `agent_end`
        is the only turn boundary; `message_end` fires once per assistant
        message (several times per run in tool loops) and so cannot terminate
        the turn. The `tool_execution_*` lane renders tool calls:
        `_start`/`_update` track a call's rendering state and `_end` emits its
        result block (a completed file-mutating tool also refreshes the
        workspace diff). Events this harness does not consume are enumerated in
        the discard arm; an unrecognized type arrives here as
        `ParsedUnknownEvent` (RPC §5.3).
        """
        match parsed:
            case RpcResponse():
                self._handle_response_event(parsed, state)
                return False
            case ExtensionUiRequest():
                # Backchannel dialogs and background-task completion notifies; never
                # a turn boundary (dialogs hold the turn via the answer round-trip;
                # a completion reconciles into the turn but `agent_end` ends it).
                self._handle_extension_ui_request(parsed)
                return False
            case ParsedAgentStart():
                # Streaming begins; nothing to emit until text_delta arrives.
                return False
            case ParsedMessageUpdate():
                self._handle_message_update(parsed, state)
                return False
            case ParsedMessageEnd():
                self._handle_message_end(parsed, state)
                return False
            case ParsedAgentEnd():
                return self._handle_agent_end(parsed, state)
            case ParsedAutoRetryEnd():
                self._handle_auto_retry_end(parsed, state)
                return False
            case ParsedExtensionError():
                self._handle_extension_error(parsed)
                return False
            case ParsedToolExecutionStart():
                self._handle_tool_execution_start(parsed, state)
                return False
            case ParsedToolExecutionUpdate():
                self._handle_tool_execution_update(parsed, state)
                return False
            case ParsedToolExecutionEnd():
                self._handle_tool_execution_end(parsed, state)
                return False
            case ParsedCompactionStart():
                self._handle_compaction_start(state)
                return False
            case ParsedCompactionEnd():
                self._handle_compaction_end(state)
                return False
            case (
                ParsedTurnStart()
                | ParsedTurnEnd()
                | ParsedMessageStart()
                | ParsedQueueUpdate()
                | ParsedAutoRetryStart()
                | ParsedSessionInfoChanged()
                | ParsedThinkingLevelChanged()
                | ParsedUnknownEvent()
            ):
                # Events this harness does not consume (turn/queue/retry/session
                # notices) plus any unrecognized type.
                logger.debug("PiAgent ignoring unconsumed event: {}", type(parsed).__name__)
                return False
            case _ as unreachable:
                assert_never(unreachable)

    def _refresh_diff_if_file_change(self, parsed: ParsedToolExecutionEnd, state: _TurnState) -> None:
        """Refresh the workspace diff after a successful file-mutating tool.

        Pi runs its own `edit`/`write`/`bash` loop and emits no signal that
        files changed beyond these tool-execution events, so Sculptor must
        regenerate the diff artifact itself. Mirrors Claude's `on_diff_needed`
        path (`should_send_diff_and_branch_name_artifacts`): trigger on a
        file-change tool, skip on tool errors. Also records the mutated file's
        path onto the turn state so the turn footer's "N files changed" reflects
        it (edit/write carry a `file_path`; a bash-driven change carries none, so
        it is not counted individually — matching the tools whose path we know).
        """
        if parsed.tool_name not in FILE_CHANGE_TOOL_NAMES or parsed.is_error:
            return
        info = state.tool_calls.get(parsed.tool_call_id)
        if info is not None:
            file_path = info.claude_input.get("file_path")
            if isinstance(file_path, str):
                state.note_changed_file(file_path)
        on_diff_needed = self.on_diff_needed
        if on_diff_needed is None:
            return
        logger.debug("PiAgent file-change tool finished ({}), refreshing workspace diff", parsed.tool_name)
        on_diff_needed()

    def _handle_message_update(self, parsed: ParsedMessageUpdate, state: _TurnState) -> None:
        inner = parsed.assistant_message_event
        inner_type = inner.get("type")
        if inner_type == "text_delta":
            try:
                delta = ParsedTextDelta.model_validate(inner)
            except ValidationError:
                return
            if not delta.delta:
                return
            state.accumulated_text += delta.delta
            self._output_messages.put(
                PartialResponseBlockAgentMessage(
                    assistant_message_id=state.assistant_message_id,
                    first_response_message_id=state.first_message_id,
                    content=(TextBlock(text=state.accumulated_text),),
                )
            )
            return
        if inner_type == "error":
            # WHY: streaming-time generation error — partial text up to this
            # point is preserved in the raised error.
            try:
                err = ParsedAssistantMessageError.model_validate(inner)
            except ValidationError:
                err = ParsedAssistantMessageError(type="error", reason="pi reported an in-stream error")
            reason = state.accumulated_text or err.reason
            raise PiCrashError(humanize_pi_failure_reason(reason), exit_code=None, metadata=None)
        # Other inner variants (text_start / text_end / thinking_* /
        # toolcall_* / start / done) are deliberately discarded.
        logger.debug("PiAgent ignoring assistantMessageEvent variant: {}", inner_type)

    def _raise_for_error_stop_reason(self, message: AgentMessage, state: _TurnState) -> None:
        """Raise the right failure for an assistant message that ended with stopReason "error".

        A KNOWN-TRANSIENT provider condition (`is_transient_provider_error` on
        `error_message`) raises `_PiTransientTurnError` so the turn runner retries
        it with backoff; any other error raises the terminal `PiCrashError`. A
        failed turn carries no text and no in-stream error event, so pi's real
        reason lives only on `error_message`; it is lifted (after any assistant
        text / partial) into a clean, actionable message — the transient case gets
        retry-oriented guidance so an exhausted-retry failure isn't a raw JSON blob.
        """
        if is_transient_provider_error(message.error_message):
            raise _PiTransientTurnError(humanize_transient_failure_reason(message.error_message))
        reason = extract_assistant_text(message) or message.error_message or state.accumulated_text
        raise PiCrashError(humanize_pi_failure_reason(reason), exit_code=None, metadata=None)

    def _handle_message_end(self, parsed: ParsedMessageEnd, state: _TurnState) -> None:
        """Per-message boundary — finalize this assistant message; not a turn boundary.

        Fires once per assistant message; in tool loops there may be
        several before `agent_end`. The finalized content is the assistant
        message's blocks interleaved in order — text blocks become
        `TextBlock`s and `toolCall` content blocks become `ToolUseBlock`s
        (mapped onto Claude's renderers; see `tool_rendering`). Because the
        text-only partials emitted during streaming carried no tool blocks,
        a message that issued any tool call re-advertises its full
        interleaved content as one more partial here so the `ToolUseBlock`s
        render live (name + input, in-progress) before their results arrive
        on the tool-execution lane. The `ResponseBlockAgentMessage` reuses
        the `assistant_message_id` / `first_message_id` the partials
        advertised, so the UI collapses partials into a stable final block.
        The accumulator is then reset for the next message; the tool-call
        registry persists (the lane's result events arrive after this reset).
        A `stopReason:"error"` carrying a known-transient provider failure is
        retried (see `_raise_for_error_stop_reason`); any other error raises
        `PiCrashError`, as does an unexpected `stopReason:"aborted"` UNLESS an
        abort is expected (an interrupt is pending, or shutdown) — then it is the
        interrupted boundary and the partial content is finalized normally.
        Non-assistant `message_end`s (notably the role="user" prompt echo pi emits
        at agent-run start) are dropped.
        """
        # WHY: pi records every message in the session as a message_end — the
        # user's own prompt (echoed at agent-run start), tool results, and
        # extension "custom" messages, not just the assistant's. Only assistant
        # messages carry generated content to surface; emitting any other role
        # here reflects the user's prompt back as an assistant chat bubble.
        # Guard on != "assistant" (rather than == "user") to also drop
        # toolResult/custom.
        if parsed.message.role != "assistant":
            logger.debug("PiAgent dropping non-assistant message_end (role={})", parsed.message.role)
            return
        if parsed.message.model:
            logger.info("PiAgent turn produced by model={}", parsed.message.model)
        stop_reason = parsed.message.stop_reason
        if stop_reason == "error":
            self._raise_for_error_stop_reason(parsed.message, state)
        if stop_reason == "aborted" and not self._is_abort_expected():
            # An unexpected abort (no interrupt / shutdown pending) is a pi failure.
            reason = extract_assistant_text(parsed.message) or parsed.message.error_message or state.accumulated_text
            raise PiCrashError(humanize_pi_failure_reason(reason), exit_code=None, metadata=None)
        content = self._build_interleaved_content(parsed.message, state)
        has_tool_blocks = any(isinstance(block, ToolUseBlock) for block in content)
        if has_tool_blocks:
            # Re-advertise the interleaved content as a partial so the
            # ToolUseBlocks render live (the text-only partials so far did not
            # carry them); message_conversion replaces the streamed segment with
            # this snapshot. Then register each call so the lane can attach its
            # result, and finalize the same content for persistence.
            self._output_messages.put(
                PartialResponseBlockAgentMessage(
                    assistant_message_id=state.assistant_message_id,
                    first_response_message_id=state.first_message_id,
                    content=tuple(content),
                )
            )
        for block in content:
            if isinstance(block, ToolUseBlock):
                state.tool_calls[str(block.id)] = _ToolCall(
                    claude_name=block.name,
                    claude_input=dict(block.input),
                    assistant_message_id=state.assistant_message_id,
                    is_subagent=block.name == SUBAGENT_DISPLAY_NAME,
                    is_background=block.name == BACKGROUND_TOOL_NAME,
                )
                # Remember the backchannel tool call so the dialog it opens next
                # adopts its id as the question's tool_use_id (see
                # `_build_question_data`). Dialogs are sequential, so the most
                # recent backchannel call is the one whose dialog is opening.
                if self.harness.classify_tool_ui_role(block.name) is not None:
                    self._pending_backchannel_tool_call_id = str(block.id)
        if content:
            self._output_messages.put(
                ResponseBlockAgentMessage(
                    message_id=state.first_message_id,
                    role="assistant",
                    assistant_message_id=state.assistant_message_id,
                    content=tuple(content),
                )
            )
        state.reset_accumulator()

    def _build_interleaved_content(self, message: AgentMessage, state: _TurnState) -> list[ContentBlockTypes]:
        """Build an assistant message's content as interleaved text + tool blocks.

        Iterates `message.content` in order so text and `toolCall` blocks keep
        their relative positions (the tool-execution lane is authoritative for
        the call's id/name/args, but the in-message `toolCall` block carries the
        same data and its position, so we render from it directly and reconcile
        the lane's `tool_execution_start` for the same id away — never rendering
        both). A message with no `toolCall` blocks reproduces the prior
        text-only finalization exactly: a single `TextBlock` of the
        authoritative text (the event's `message.content` text, falling back to
        the streamed accumulator), or nothing when empty.
        """
        blocks: list[ContentBlockTypes] = []
        saw_tool = False
        for raw in message.content:
            block_type = raw.get("type")
            if block_type == "text":
                text = raw.get("text", "")
                if isinstance(text, str) and text:
                    blocks.append(TextBlock(text=text))
            elif block_type == "toolCall":
                # pi's toolCall content block (docs/session-format.md): {id, name,
                # arguments}; parse permissively against the lane's
                # {toolCallId, toolName, args} naming too.
                tool_call_id = str(raw.get("id") or raw.get("toolCallId") or "")
                if not tool_call_id:
                    continue
                pi_name = str(raw.get("name") or raw.get("toolName") or "")
                pi_args = raw.get("arguments")
                if not isinstance(pi_args, dict):
                    pi_args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
                claude_name, claude_input = map_pi_tool_call(pi_name, pi_args)
                blocks.append(ToolUseBlock(id=ToolUseID(tool_call_id), name=claude_name, input=claude_input))
                saw_tool = True
        if not saw_tool:
            final_text = extract_assistant_text(message) or state.accumulated_text
            text_only: list[ContentBlockTypes] = []
            if final_text:
                text_only.append(TextBlock(text=final_text))
            return text_only
        return blocks

    def _handle_tool_execution_start(self, parsed: ParsedToolExecutionStart, state: _TurnState) -> None:
        """Render a tool call from the lane only when no `toolCall` block did.

        Normally the issuing assistant message's `toolCall` content block
        already produced the `ToolUseBlock` at `message_end` (which precedes
        this event), so a `tool_call_id` already in the registry is the SAME
        call and is skipped — the lane is authoritative but the call is rendered
        once. This fallback handles a lane event with no matching `toolCall`
        block (not expected from real pi): it registers and renders the
        `ToolUseBlock` so the call is never silently dropped.
        """
        tool_call_id = parsed.tool_call_id
        if not tool_call_id or tool_call_id in state.tool_calls:
            return
        claude_name, claude_input = map_pi_tool_call(parsed.tool_name, parsed.args)
        state.tool_calls[tool_call_id] = _ToolCall(
            claude_name=claude_name,
            claude_input=claude_input,
            assistant_message_id=state.assistant_message_id,
            is_subagent=claude_name == SUBAGENT_DISPLAY_NAME,
            is_background=claude_name == BACKGROUND_TOOL_NAME,
        )
        text_blocks: tuple[ContentBlockTypes, ...] = (
            (TextBlock(text=state.accumulated_text),) if state.accumulated_text else ()
        )
        self._output_messages.put(
            PartialResponseBlockAgentMessage(
                assistant_message_id=state.assistant_message_id,
                first_response_message_id=state.first_message_id,
                content=text_blocks
                + (ToolUseBlock(id=ToolUseID(tool_call_id), name=claude_name, input=claude_input),),
            )
        )

    def _handle_tool_execution_update(self, parsed: ParsedToolExecutionUpdate, state: _TurnState) -> None:
        """Track a tool's in-progress output (accumulated, not delta).

        pi sends the full accumulated output on each update, so we REPLACE the
        stored text rather than append. It is used as the result text only if
        `tool_execution_end` carries no result body — the rendered result block
        is emitted once, at `_end`.
        """
        info = state.tool_calls.get(parsed.tool_call_id)
        if info is None:
            return
        info.partial_text = extract_text_from_tool_payload(parsed.partial_result)

    def _handle_tool_execution_end(self, parsed: ParsedToolExecutionEnd, state: _TurnState) -> None:
        """Finish a tool call: refresh the workspace diff, then emit its result block."""
        self._refresh_diff_if_file_change(parsed, state)
        self._emit_tool_result(parsed, state)

    def _emit_tool_result(self, parsed: ParsedToolExecutionEnd, state: _TurnState) -> None:
        """Emit the `ToolResultBlock` correlated to its `ToolUseBlock` by id.

        message_conversion replaces the matching in-progress `ToolUseBlock` with
        this result (or the frontend pairs them by id), flipping the rendered
        tool from in-progress to completed/error. `is_error=True` results render
        as errors, matching Claude's error-result styling. The content type is
        chosen by `build_tool_result_content`: a diff (file chip) for
        file-mutating tools, generic text otherwise. The invocation string
        reuses Claude's per-tool formatter so the mapped tools render identically.
        """
        tool_call_id = parsed.tool_call_id
        if not tool_call_id:
            return
        info = state.tool_calls.get(tool_call_id)
        if info is not None:
            tool_name = info.claude_name
            tool_input = info.claude_input
            assistant_message_id = info.assistant_message_id
            fallback_text = info.partial_text
            if info.is_subagent:
                # The `subagent` tool returned immediately with a launch snapshot;
                # surface it as a started sub-agent task (tracked at the agent
                # level) and yield. The children's nested rendering + completion is
                # surfaced out-of-band (`_handle_subagent_completion`). The result
                # block below still renders the "Started …" launch acknowledgement.
                self._emit_subagent_started(parsed.result, tool_call_id)
            if info.is_background:
                # The `background` tool returned immediately with a launch
                # snapshot; surface it as a started background task. The turn then
                # ends normally (the user keeps chatting); the task's completion
                # is surfaced out-of-band. The normal result block below still
                # renders the "Started …" acknowledgement.
                self._emit_background_started(parsed.result, tool_call_id)
        else:
            # No registration (no toolCall block and no start seen) — map the
            # name with empty input (the end event carries no args).
            tool_name, tool_input = map_pi_tool_call(parsed.tool_name, {})
            assistant_message_id = state.assistant_message_id
            fallback_text = ""
        result_block = ToolResultBlock(
            tool_use_id=ToolUseID(tool_call_id),
            tool_name=tool_name,
            invocation_string=get_tool_invocation_string(tool_name, tool_input),
            content=build_tool_result_content(tool_name, tool_input, parsed.result, fallback_text),
            is_error=parsed.is_error,
        )
        self._output_messages.put(
            ResponseBlockAgentMessage(
                message_id=AgentMessageID(),
                role="assistant",
                assistant_message_id=assistant_message_id,
                content=(result_block,),
            )
        )

    def _emit_subagent_started(self, result_payload: Any, parent_tool_call_id: str) -> None:
        """Turn a `subagent` tool's launch result into a started sub-agent task.

        Parses the structured launch snapshot (`subagent.py`); on success records the
        task (with its children's process-group ids) at the AGENT level so it outlives
        this turn, and emits `BackgroundTaskStartedAgentMessage` against the parent
        `Agent` tool-use id (the frontend's background-sub-agent pill). The launching
        turn then ends — the user keeps chatting while the children run, and their
        nested rendering + completion is surfaced out-of-band
        (`_handle_subagent_completion`). A malformed/absent snapshot degrades to no
        sub-agent lifecycle (the call already rendered as an ordinary tool result).
        """
        started = parse_subagent_start(result_payload)
        if started is None:
            return
        with self._background_tasks_lock:
            self._subagent_tasks[started.task_id] = started.pgids
        self._output_messages.put(
            BackgroundTaskStartedAgentMessage(
                message_id=AgentMessageID(),
                background_task_id=started.task_id,
                tool_use_id=started.tool_call_id or parent_tool_call_id,
                description=f"{started.count} sub-agent(s)" if started.count else started.label,
                task_type=started.label,
            )
        )

    def _emit_child_message(self, child: SubagentChild, parent_tool_call_id: str) -> None:
        # A fresh message id and assistant_message_id per child so each renders
        # as its own attributed ChatMessage; message_conversion keys the nested
        # grouping off parent_tool_use_id, not these ids.
        self._output_messages.put(
            ResponseBlockAgentMessage(
                message_id=AgentMessageID(),
                role="assistant",
                assistant_message_id=AssistantMessageID(generate_id()),
                content=build_child_content_blocks(child, parent_tool_call_id),
                parent_tool_use_id=parent_tool_call_id,
            )
        )

    def _handle_subagent_completion(self, completion: SubagentCompletion) -> None:
        """Reconcile a sub-agent task's completion into the conversation.

        Drops the task from the agent-level set, emits each child nested under the
        parent `Agent` tool block (`parent_tool_use_id`), and emits
        `BackgroundTaskNotificationAgentMessage` to clear the started indicator — for
        an `Agent` parent, message_conversion turns that into the synthetic
        completion child that settles the sub-agent pill. Safe to call inside a
        turn's drain OR out-of-band (the caller supplies the request cycle in the
        latter case — see `_emit_subagent_completion_out_of_band`).
        """
        with self._background_tasks_lock:
            self._subagent_tasks.pop(completion.task_id, None)
        for child in completion.children:
            self._emit_child_message(child, completion.tool_call_id)
        self._output_messages.put(
            BackgroundTaskNotificationAgentMessage(
                message_id=AgentMessageID(),
                background_task_id=completion.task_id,
                tool_use_id=completion.tool_call_id,
                status=completion.status,
                summary=_format_subagent_completion(completion),
            )
        )

    def _emit_subagent_completion_out_of_band(self, completion: SubagentCompletion) -> None:
        """Surface a sub-agent completion that arrived between turns, live.

        Wraps the completion in its own minimal request cycle (RequestStarted →
        children + notification → RequestSuccess) so message_conversion renders the
        nested children as standalone assistant messages even though no user turn is
        in flight — the out-of-band analogue of the in-turn path. The request id is
        fresh (the completion is not a reply to a user message).
        """
        request_id = AgentMessageID()
        self._output_messages.put(RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id))
        try:
            self._handle_subagent_completion(completion)
        finally:
            self._output_messages.put(
                RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=request_id, interrupted=False)
            )

    def _emit_background_started(self, result_payload: Any, parent_tool_call_id: str) -> None:
        """Turn a `background` tool's launch result into a started background task.

        Parses the structured launch snapshot (`background.py`); on success records
        the task (with its child process-group id) at the AGENT level so it outlives
        this turn, and emits `BackgroundTaskStartedAgentMessage`. The launching turn
        then ends normally (`_handle_agent_end`) — the user keeps chatting while the
        task runs, and its completion is surfaced out-of-band
        (`_drain_idle_background_events`). A malformed/absent snapshot degrades to no
        background lifecycle (the call already rendered as an ordinary tool result).
        """
        started = parse_background_start(result_payload)
        if started is None:
            return
        with self._background_tasks_lock:
            self._background_tasks[started.task_id] = started.pgid
        self._output_messages.put(
            BackgroundTaskStartedAgentMessage(
                message_id=AgentMessageID(),
                background_task_id=started.task_id,
                tool_use_id=started.tool_call_id or parent_tool_call_id,
                description=started.command,
                task_type=started.label,
            )
        )

    def _handle_background_completion(self, completion: BackgroundTaskCompletion) -> None:
        """Reconcile a background task's completion into the conversation.

        Drops the task from the agent-level set and emits
        `BackgroundTaskNotificationAgentMessage` plus an assistant block carrying the
        summary, so the completion (or failure) is visible. The summary MUST be
        advertised as a partial then the final block (paired ids) so the LIVE stream
        reducer renders it: a lone final block with no preceding partial renders only
        on reload (the live/reload divergence). Safe to call inside a turn's drain OR
        out-of-band (the caller supplies the request cycle in the latter case — see
        `_emit_background_completion_out_of_band`).
        """
        with self._background_tasks_lock:
            self._background_tasks.pop(completion.task_id, None)
        self._output_messages.put(
            BackgroundTaskNotificationAgentMessage(
                message_id=AgentMessageID(),
                background_task_id=completion.task_id,
                tool_use_id=completion.tool_call_id,
                status=completion.status,
                summary=completion.summary,
                duration_seconds=(completion.duration_ms / 1000.0) if completion.duration_ms is not None else None,
            )
        )
        summary_message_id = AgentMessageID()
        summary_assistant_id = AssistantMessageID(generate_id())
        summary_blocks: tuple[ContentBlockTypes, ...] = (TextBlock(text=_format_background_completion(completion)),)
        self._output_messages.put(
            PartialResponseBlockAgentMessage(
                assistant_message_id=summary_assistant_id,
                first_response_message_id=summary_message_id,
                content=summary_blocks,
            )
        )
        self._output_messages.put(
            ResponseBlockAgentMessage(
                message_id=summary_message_id,
                role="assistant",
                assistant_message_id=summary_assistant_id,
                content=summary_blocks,
            )
        )

    def _emit_background_completion_out_of_band(self, completion: BackgroundTaskCompletion) -> None:
        """Surface a background completion that arrived between turns, live.

        Wraps the completion in its own minimal request cycle (RequestStarted →
        notification + summary → RequestSuccess) so message_conversion renders it as a
        standalone assistant message even though no user turn is in flight — the
        out-of-band analogue of the in-turn path. The request id is fresh (the
        completion is not a reply to a user message)."""
        request_id = AgentMessageID()
        self._output_messages.put(RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id))
        try:
            self._handle_background_completion(completion)
        finally:
            self._output_messages.put(
                RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=request_id, interrupted=False)
            )

    def _drain_idle_background_events(self) -> None:
        """Between turns, surface task completions and consume any auto-resume turn.

        Sculptor drains pi's stdout only during a turn, so a completion `notify`
        (and the reaction turn the extension triggers via `sendUserMessage`) firing
        while the user is idle would otherwise sit unseen. While a task is in flight
        — or a completion is awaiting its reaction turn — `_process_message_queue`
        calls this between user messages: a completion is surfaced out-of-band, and a
        pi-initiated turn (the auto-resume reaction) is consumed in its own request
        cycle. Runs on the message-processing thread (the sole stdout reader).
        """
        process = self._process
        if process is None:
            return
        out_queue = process.get_queue()
        while not self._shutdown_event.is_set():
            try:
                line, is_stdout = out_queue.get_nowait()
            except Empty:
                return
            if not is_stdout:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            parsed = parse_rpc_message(event)
            if isinstance(parsed, ParsedAgentStart):
                # The extension woke the agent (`sendUserMessage`) after a completion;
                # consume its reaction turn in its own request cycle.
                self._awaiting_reaction_count = max(0, self._awaiting_reaction_count - 1)
                self._consume_reaction_turn()
                continue
            if isinstance(parsed, ExtensionUiRequest) and parsed.method == "notify":
                completion = parse_background_completion(parsed.message)
                if completion is not None:
                    self._emit_background_completion_out_of_band(completion)
                    self._note_awaiting_reaction()
                    continue
                sub_completion = parse_subagent_completion(parsed.message)
                if sub_completion is not None:
                    self._emit_subagent_completion_out_of_band(sub_completion)
                    self._note_awaiting_reaction()

    def _consume_reaction_turn(self) -> None:
        """Consume a pi-initiated turn — the auto-resume reaction the extension
        triggered via `sendUserMessage` on completion — in its own request cycle so
        it renders as a standalone assistant turn. The triggering `agent_start` has
        already been read; `_consume_until_turn_end` consumes the rest through
        `agent_end`. A turn-level failure is logged, not raised: an auto-resume
        reaction must not tear down the session.
        """
        request_id = AgentMessageID()
        self._output_messages.put(RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id))
        self._turn_in_flight.set()
        interrupted = False
        try:
            self._consume_until_turn_end()
        except PiCrashError as error:
            logger.info("PiAgent auto-resume reaction turn failed: {}", error)
            interrupted = True
        finally:
            self._turn_in_flight.clear()
            self._output_messages.put(
                RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=request_id, interrupted=interrupted)
            )

    def _cancel_all_background_tasks(self) -> None:
        """SIGTERM every still-running background and sub-agent child by signalling its process group.

        Each child is spawned detached (its own group leader), so it escapes pi's
        process group; killing the negative pgid INSIDE the environment tears down
        just that child tree without touching pi. Called on shutdown (`wait`) as the
        no-orphan guarantee, alongside the extension's `session_shutdown` handler.
        Best-effort and idempotent — a child that already exited is a no-op. NOT
        called on a turn interrupt: a backgrounded task runs independently of the
        turn that launched it and must survive the user stopping a later turn.
        """
        process = self._process
        with self._background_tasks_lock:
            pgids = list(self._background_tasks.values())
            self._background_tasks.clear()
            for group in self._subagent_tasks.values():
                pgids.extend(group)
            self._subagent_tasks.clear()
        for pgid in pgids:
            if process is not None and pgid > 0:
                try:
                    self.environment.run_process_to_completion(
                        ["bash", "-c", f"kill -TERM -{pgid} 2>/dev/null || true"],
                        secrets={},
                        timeout=5.0,
                        is_checked_after=False,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.debug("PiAgent async-task cancel for pgid {} failed: {}", pgid, e)

    def _handle_agent_end(self, parsed: ParsedAgentEnd, state: _TurnState) -> bool:
        """Turn boundary — return True so the dispatcher yields control.

        A turn that launched a background task ends here like any other (the task
        runs independently; its completion is surfaced out-of-band — see
        `_drain_idle_background_events`), so the user is unblocked the moment the
        task starts.

        Per-message finalization happens in `_handle_message_end`, which
        emits each `ResponseBlockAgentMessage` with the IDs its partials
        already advertised. `agent_end` is the single signal that the
        agent run is fully idle; pi emits it once per `prompt`
        command. If `message_end` never fired for the current
        accumulating message (an edge case — e.g. abort mid-stream), the
        accumulated text is finalized here using the partials' IDs so
        the UI still settles on a stable block. A `stopReason:"error"`
        on any assistant message in the final transcript is retried when it
        carries a known-transient provider failure (see
        `_raise_for_error_stop_reason`) and otherwise raises `PiCrashError`; an
        unexpected `stopReason:"aborted"` raises too, EXCEPT when an abort is
        expected (interrupt pending, or shutdown), which is the interrupted
        boundary and finalizes the partial text instead.
        `willRetry: true` means pi will start another agent run, typically
        after a transient failure — the current turn still ends so the caller
        can drain the next pump.
        """
        abort_expected = self._is_abort_expected()
        for message in parsed.messages:
            if message.role != "assistant" or message.stop_reason not in ("error", "aborted"):
                continue
            if message.stop_reason == "aborted":
                if abort_expected:
                    # Expected interrupted boundary: finalize the partial below, don't raise.
                    continue
                reason = extract_assistant_text(message) or message.error_message or state.accumulated_text
                raise PiCrashError(humanize_pi_failure_reason(reason), exit_code=None, metadata=None)
            self._raise_for_error_stop_reason(message, state)
        if state.accumulated_text:
            self._output_messages.put(
                ResponseBlockAgentMessage(
                    message_id=state.first_message_id,
                    role="assistant",
                    assistant_message_id=state.assistant_message_id,
                    content=(TextBlock(text=state.accumulated_text),),
                )
            )
        self._emit_turn_metrics(parsed, state)
        return True

    def _emit_turn_metrics(self, parsed: ParsedAgentEnd, state: _TurnState) -> None:
        """Emit the per-turn footer metrics at the agent-run boundary.

        Mirrors Claude's `TurnMetricsAgentMessage` (output_processor
        `_flush_pending_turn_metrics`): the footer under a completed assistant
        turn shows wall-clock duration, this turn's token totals, and the files it
        changed. Emitted BEFORE the turn's terminating `RequestSuccess` so
        message_conversion stamps it onto the in-progress chat message before
        finalizing (see `_attach_turn_metrics`). Token totals are summed across the
        run's assistant messages (pi reports usage per message); an interrupted
        turn with no usage still emits duration + changed files so the footer
        renders. pi exposes no numeric context-window threshold on the wire, so
        the context fields stay unset (the "% context" chip is Claude-only — see
        TokenPopoverContent). Duplicate `willRetry` runs do not reach here (the
        retry loop rebuilds `_TurnState`), so this fires once per user turn.
        """
        input_tokens, output_tokens = sum_message_usage(parsed.messages)
        turn_metrics = TurnMetrics(
            duration_seconds=time.monotonic() - state.start_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=None,
            changed_files=list(state.changed_files),
        )
        self._output_messages.put(TurnMetricsAgentMessage(message_id=AgentMessageID(), turn_metrics=turn_metrics))

    def _handle_auto_retry_end(self, parsed: ParsedAutoRetryEnd, state: _TurnState) -> None:
        if not parsed.success:
            reason = parsed.final_error or state.accumulated_text or "pi exhausted retries"
            raise PiCrashError(humanize_pi_failure_reason(reason), exit_code=None, metadata=None)
        # Successful retry — a new agent run is about to begin; do not yield.

    def _handle_compaction_start(self, state: _TurnState) -> None:
        """Map pi's compaction_start onto the Compacting chrome.

        Emits AutoCompactingAgentMessage so is_auto_compacting flips True and
        the StatusPill shows "Compacting...". pi's `reason`
        (manual/threshold/overflow) is deliberately not surfaced — Sculptor's
        chrome is a single Compacting state with no per-reason distinction
        (Claude parity). Arms the stick-prevention Done in
        _consume_until_turn_end via `compaction_open`.
        """
        state.compaction_open = True
        self._output_messages.put(AutoCompactingAgentMessage(message_id=AgentMessageID()))

    def _handle_compaction_end(self, state: _TurnState) -> None:
        """Map pi's compaction_end onto clearing the Compacting chrome.

        ALWAYS emits AutoCompactingDoneAgentMessage so the pill never sticks,
        including the aborted / error_message cases. We do NOT raise here: a
        genuine failure is surfaced only if pi itself ends the run in error (the
        agent_end / message_end error paths handle that). `willRetry:true`
        (overflow) means pi re-runs the prompt; the turn extends via the normal
        agent_end boundary, so this is non-terminal. pi's `result.summary` is not
        rendered (Claude shows no equivalent). Idempotent: a Done with no
        preceding start (resumed mid-stream) is harmless.
        """
        state.compaction_open = False
        self._output_messages.put(AutoCompactingDoneAgentMessage(message_id=AgentMessageID()))

    def _handle_extension_error(self, parsed: ParsedExtensionError) -> None:
        """Fail loud on an error from our pinned extension; log foreign ones.

        A thrown extension surfaces as a non-terminal `extension_error`
        (RPC §5.2/§8). An error from the extension Sculptor loaded (`-e <path>`)
        fails the turn visibly via `PiCrashError` rather than continuing with a
        silently broken backchannel. An error from any other extension path
        stays log-only.
        """
        if parsed.extension_path in self._loaded_extension_paths:
            text = parsed.error or "the Sculptor backchannel extension raised an error"
            raise PiCrashError(text, exit_code=None, metadata=None)
        logger.info(
            "PiAgent extension_error from foreign extension: extension={} event={} error={}",
            parsed.extension_path,
            parsed.event,
            parsed.error,
        )

    def _handle_extension_ui_request(self, parsed: ExtensionUiRequest) -> None:
        """Dispatch an extension UI request (never a turn boundary).

        Two of our pinned extensions speak this lane:
        - The backchannel extension opens blocking `select` (multiple-choice /
          plan approval) and `input` (free-form) dialogs. Each becomes an
          `AskUserQuestionAgentMessage`, and the request id is recorded so
          `_deliver_question_answer` can post the matching `extension_ui_response`.
          pi blocks until then (we never set a `timeout`), so the turn stays open
          while the consume loop keeps draining.
        - The background-task extension reports a task's completion as a
          fire-and-forget `notify` carrying our structured marker; that reconciles
          the task into the current turn (the turn ends at its own `agent_end` — a
          backgrounded task does not hold it open).

        Any other fire-and-forget method (`setStatus`/…) or a foreign `notify`
        needs no response and is ignored.
        """
        if parsed.method == "notify":
            completion = parse_background_completion(parsed.message)
            if completion is not None:
                # A task that completes while a user turn is in flight is reconciled
                # into that turn; the reaction the extension triggers (deliverAs
                # "followUp") runs after this turn and is consumed by the idle-drain.
                self._handle_background_completion(completion)
                self._note_awaiting_reaction()
                return
            sub_completion = parse_subagent_completion(parsed.message)
            if sub_completion is not None:
                self._handle_subagent_completion(sub_completion)
                self._note_awaiting_reaction()
                return
            logger.debug("PiAgent ignoring non-task notify extension_ui_request")
            return
        if parsed.method not in ("select", "input"):
            logger.debug("PiAgent ignoring non-dialog extension_ui_request method: {}", parsed.method)
            return
        question_data = self._build_question_data(parsed)
        with self._backchannel_lock:
            self._pending_ui_request_id = parsed.id
        self._output_messages.put(
            AskUserQuestionAgentMessage(message_id=AgentMessageID(), question_data=question_data)
        )

    def _build_question_data(self, parsed: ExtensionUiRequest) -> AskUserQuestionData:
        """Build the AskUserQuestion payload from a backchannel dialog request.

        The `exit_plan_mode` tool's `select` uses the plan-approval sentinel
        title, which maps to the canonical Sculptor plan-approval question (so
        the frontend shows "Waiting for plan approval" and the gated methods
        agree). Any other dialog is a regular question: `select` (options) →
        multiple choice, `input` (no options) → free-form. `other_label` lets the
        user type a free-form answer too; pi returns the typed value verbatim.
        """
        # The question's tool_use_id is the originating tool call's id (not the
        # ui_request id) so the frontend correlates the answered question with the
        # rendered ToolUseBlock / ToolResultBlock. Fall back to the ui_request id
        # only if no backchannel tool call was seen (unexpected — the tool issues
        # the dialog).
        tool_use_id = self._pending_backchannel_tool_call_id or parsed.id
        if parsed.method == "select" and parsed.title == PLAN_APPROVAL_DIALOG_TITLE:
            return make_plan_approval_question(tool_use_id=tool_use_id)
        return build_ask_user_question_data(parsed.title or "", parsed.options or [], tool_use_id)

    def _deliver_question_answer(self, message: UserQuestionAnswerMessage) -> None:
        """Post the user's answer back to the dialog pi is blocked on.

        Runs on the request-handling thread while the dispatcher thread drains
        stdout. Emits the answer's own `RequestStarted` immediately and defers
        its `RequestSuccess` to the turn boundary (`_finalize_pending_answers`),
        mirroring Claude's `_try_deliver_answer_to_mcp`. A plan approval also
        clears plan mode and emits `PlanModeAgentMessage(False)`. An answer with
        no pending dialog is stale (the frontend gate should prevent it): emit a
        terminal `RequestSkipped` so the request resolves, and drop it.
        """
        with self._backchannel_lock:
            request_id = self._pending_ui_request_id
            if request_id is None:
                logger.info(
                    "PiAgent received question answer with no pending dialog (stale); skipping. tool_use_id={}",
                    message.tool_use_id,
                )
                self._output_messages.put(RequestSkippedAgentMessage(request_id=message.message_id))
                return
            self._pending_ui_request_id = None
            self._pending_answer_request_ids.append(message.message_id)
        if self._is_in_plan_mode and is_plan_approval(message):
            self._is_in_plan_mode = False
            self._output_messages.put(PlanModeAgentMessage(message_id=AgentMessageID(), is_in_plan_mode=False))
        self._output_messages.put(
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=message.message_id)
        )
        self._send_rpc({"type": "extension_ui_response", "id": request_id, **extension_ui_response_body(message)})
