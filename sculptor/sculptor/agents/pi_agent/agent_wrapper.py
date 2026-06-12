"""PiAgent — `DefaultAgentWrapper` subclass wrapping `pi --mode rpc`.

The agent spawns a long-lived `pi --mode rpc --session-dir <dir>
--session-id <id> --append-system-prompt <prompt> [--skill <dir> ...]`
subprocess and pumps user turns over JSONL stdin/stdout. The session flags
persist the conversation as a JSONL file under a per-task dir and pin its id
Sculptor-side, so relaunching after an agent-process restart resumes the full
conversation (`supports_session_resume`). The `--skill` flags point pi at the
workspace's Claude-visible skill sources so its skill set matches the slash
picker's (`supports_skills`). Pi's stdout multiplexes three channels
(`response`, `extension_ui_request`, and the `AgentSessionEvent` union);
the dispatcher distinguishes them by top-level `type`. Pi's tool calls
render as rich tool blocks (`supports_tool_use_rendering=True`): the
issuing assistant message's `toolCall` content blocks become
`ToolUseBlock`s (name + input, shown while running) and the
tool-execution lane's `tool_execution_end` becomes the `ToolResultBlock`
(the result, shown when done), correlated by the shared tool-call id (see
`tool_rendering.py` for the pi→Claude name/arg adaptation). A finished
file-mutating tool (`edit`/`write`/`bash`) additionally triggers
`on_diff_needed` so the workspace diff is regenerated — pi runs the tools
against the workspace itself and emits no other signal that files changed.

Wire-protocol reference: the pi RPC protocol notes (pi 0.78.0).
"""

from __future__ import annotations

import json
import os
import queue
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Event
from typing import Any
from typing import Mapping
from typing import assert_never

from loguru import logger
from packaging.version import InvalidVersion
from packaging.version import Version
from pydantic import PrivateAttr
from pydantic import ValidationError

from sculptor.agents.default.agent_wrapper import DefaultAgentWrapper
from sculptor.agents.default.utils import get_state_file_contents
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
from sculptor.agents.pi_agent.output_processor import parse_rpc_message
from sculptor.agents.pi_agent.tool_rendering import build_tool_result_content
from sculptor.agents.pi_agent.tool_rendering import extract_text_from_tool_payload
from sculptor.agents.pi_agent.tool_rendering import map_pi_tool_call
from sculptor.common.plugin import get_plugin_dirs
from sculptor.foundation.common import generate_id
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
from sculptor.interfaces.agents.errors import AgentCrashed
from sculptor.interfaces.agents.errors import PiBinaryNotFoundError
from sculptor.interfaces.agents.errors import PiCrashError
from sculptor.interfaces.agents.errors import PiVersionMismatchError
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import ToolUseID
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.dependency_management_service import parse_pi_version
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.state.chat_state import ContentBlockTypes
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.claude_state import get_tool_invocation_string
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message
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

# Control messages for capabilities pi does not support; `_push_message` drops
# them (pi has no RPC equivalent) and logs each at error level — the frontend
# gate should keep them from reaching pi, so one arriving means a gate has
# failed. Each maps to the capability whose handler will replace its drop:
#   UserQuestionAnswerMessage        → supports_interactive_backchannel
#   ClearContextUserMessage          → supports_context_reset
_DEAD_LETTER_MESSAGE_TYPES: tuple[type[Message], ...] = (
    UserQuestionAnswerMessage,
    ClearContextUserMessage,
)

# If pi's abort-induced `agent_end` does not arrive within this grace window
# (pi wedged or ignoring the abort), escalate to SIGTERM; the process-exit
# fallback in `_consume_until_turn_end` then resolves the turn.
_INTERRUPT_ESCALATION_GRACE_SECONDS: float = 5.0


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
    """

    claude_name: str
    claude_input: dict[str, Any]
    assistant_message_id: AssistantMessageID
    # Accumulated (not delta) tool output from the latest `tool_execution_update`,
    # used as the result text if `tool_execution_end` carries no result body.
    partial_text: str = ""


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

    Gating on the discovered set is what keeps the rewrite safe: pseudo-skills
    (`/clear`, `/copy`, `/btw`) are parsed frontend-side and never reach here
    nor appear in that set, and ordinary text that merely starts with `/` is
    left alone. A plugin-namespaced name (`<plugin>:<skill>`) is reduced to its
    bare `<skill>` because pi registers plugin skills un-namespaced (tracked as
    a FOLLOWUPS divergence in the tranche MR).
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

    __slots__ = ("accumulated_text", "assistant_message_id", "first_message_id", "prompt_id", "tool_calls")

    def __init__(self, prompt_id: str) -> None:
        self.prompt_id = prompt_id
        self.accumulated_text = ""
        self.assistant_message_id = AssistantMessageID(generate_id())
        self.first_message_id = AgentMessageID()
        self.tool_calls: dict[str, _ToolCall] = {}

    def reset_accumulator(self) -> None:
        self.accumulated_text = ""
        self.assistant_message_id = AssistantMessageID(generate_id())
        self.first_message_id = AgentMessageID()


class PiAgent(DefaultAgentWrapper):
    # Narrows the inherited `harness: Harness` field — the registry owns
    # construction, so no agent↔harness import cycle exists.
    harness: PiHarness
    config: PiAgentConfig
    git_hash: str
    _input_agent_messages: Queue[ChatInputUserMessage] = PrivateAttr(default_factory=Queue)
    _shutdown_event: Event = PrivateAttr(default_factory=Event)
    _message_processing_thread: ObservableThread | None = PrivateAttr(default=None)
    # The pi session id this process resumes / creates (pinned via --session-id);
    # persisted in PI_SESSION_ID_STATE_FILE so a restart reuses it.
    _session_id: str = PrivateAttr(default="")
    # Set while a turn is actively draining pi's stdout — gates the interrupt
    # escalation so an interrupt that races in between turns never SIGTERMs an
    # idle (but healthy) pi.
    _turn_in_flight: Event = PrivateAttr(default_factory=Event)
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
        # NOTE for phase 04 (context reset): `new_session` starts a fresh session
        # id within this dir. When that handler lands it MUST overwrite
        # PI_SESSION_ID_STATE_FILE with the new id (read it back via get_state /
        # session_info_changed) so a later resume targets the post-clear session,
        # not this one.
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
        # `--session-id` (Sculptor-pinned id, "creating it if missing") is the
        # resume lever, chosen over `--session <id>`: it never errors on an
        # absent/corrupt session (real pi 0.78.0 exits non-zero for an unknown
        # `--session`), so a lost session file degrades to a loud fresh start
        # rather than a crash loop. Pi also tolerates a truncated JSONL tail,
        # resuming the valid prefix. See the MR for the lever rationale.
        command = [
            binary,
            "--mode",
            "rpc",
            "--session-dir",
            str(session_dir),
            "--session-id",
            self._session_id,
            "--append-system-prompt",
            system_prompt,
            *skill_args,
        ]
        self._process = self.environment.run_process_in_background(
            command,
            secrets=merged_secrets,
            open_stdin=True,
        )
        if is_resume:
            # Best-effort guard against SILENT context loss: confirm pi actually
            # resumed the session we asked for. Control flow is unchanged either
            # way (`--session-id` cannot crash-loop); a mismatch / empty session
            # is logged loud. Safe to read stdout here because the message-
            # processing thread (the only other reader of the process queue) is
            # not started until after this returns.
            self._verify_resumed_session(self._session_id)
        self._message_processing_thread = self.concurrency_group.start_new_thread(
            target=self._process_message_queue,
        )

    def _push_message(self, message: Message) -> bool:
        if isinstance(message, ChatInputUserMessage):
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
        if isinstance(message, _DEAD_LETTER_MESSAGE_TYPES):
            # See _DEAD_LETTER_MESSAGE_TYPES. Returns False so the base class's
            # generic handling still runs.
            logger.error(
                "PiAgent dropping unsupported control message {} for task {} — a frontend capability gate should have prevented it",
                type(message).__name__,
                self.task_id,
            )
            return False
        # StopAgentUserMessage, RemoveQueuedMessageUserMessage, and
        # ManualSyncMergeIntoAgentAttemptedMessage are handled by the base class
        # after this False return — handled, not dropped, so not dead-lettered.
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
        (a repo without `.claude/skills` is normal); flag order is deterministic
        (the helper's discovery order) so `get_commands`-based debugging is
        stable.
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

    def _send_rpc(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None:
            return
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            process.write_stdin(line)
        except Exception as e:  # noqa: BLE001
            logger.debug("PiAgent write_stdin failed: {}", e)

    def _request_state_blocking(self, timeout: float = 10.0) -> dict[str, Any] | None:
        """Send `get_state` and return pi's reported `RpcSessionState` data (RPC §5.1).

        Reads pi's stdout queue directly, so it is ONLY safe to call before the
        message-processing thread starts (start-time resume verification) — both
        drain the same queue. Returns None on timeout / process exit / no
        matching response.
        """
        process = self._process
        if process is None:
            return None
        request_id = generate_id()
        self._send_rpc({"type": "get_state", "id": request_id})
        out_queue = process.get_queue()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.is_finished() and out_queue.empty():
                return None
            try:
                line, is_stdout = out_queue.get(timeout=0.1)
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
            if (
                isinstance(event, dict)
                and event.get("type") == "response"
                and event.get("command") == "get_state"
                and event.get("id") == request_id
            ):
                data = event.get("data")
                return data if isinstance(data, dict) else None
        return None

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
            try:
                message = self._input_agent_messages.get(timeout=0.5)
            except queue.Empty:
                continue
            self._run_prompt_turn(message)

    def _run_prompt_turn(self, message: ChatInputUserMessage) -> None:
        with self._handle_user_message(message):
            # A fresh turn starts un-interrupted: clear interrupt state left by an
            # interrupt that raced in with no turn in flight, which would otherwise
            # mis-mark this turn as interrupted.
            self._was_interrupted.clear()
            self._interrupt_pending.clear()
            self._cancel_interrupt_escalation()
            prompt_id = generate_id()
            self._turn_in_flight.set()
            prompt_text = _rewrite_skill_invocation(message.text, self._discovered_skill_names)
            self._send_rpc({"type": "prompt", "id": prompt_id, "message": prompt_text})
            try:
                self._consume_until_turn_end(prompt_id)
            finally:
                # Turn over: stand down escalation and drop interrupt-pending so a
                # late grace-window thread can't SIGTERM the next turn's pi.
                self._turn_in_flight.clear()
                self._interrupt_pending.clear()
                self._cancel_interrupt_escalation()

    def _consume_until_turn_end(self, prompt_id: str = "") -> None:
        """Drive pi's stdout until the current agent run terminates.

        Top-level dispatch routes on `event["type"]` into three lanes:
        `response` (command-ACK; correlate by `id`; `success: false` on
        the outstanding `prompt` raises `PiCrashError`),
        `extension_ui_request` (logged and discarded; pi-basic loads no
        extensions), and everything else (the `AgentSessionEvent` union,
        dispatched per-`type`).
        """
        process = self._process
        assert process is not None
        out_queue = process.get_queue()
        state = _TurnState(prompt_id=prompt_id)

        while not self._shutdown_event.is_set():
            if process.is_finished() and out_queue.empty():
                return
            try:
                line, is_stdout = out_queue.get(timeout=0.1)
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
            message = parsed.error or "pi rejected the prompt"
            raise PiCrashError(message, exit_code=None, metadata=None)
        logger.debug("PiAgent received response: command={} success={}", parsed.command, parsed.success)

    def _dispatch_event(self, parsed: ParsedRpcMessage, state: _TurnState) -> bool:
        """Dispatch one parsed RPC message. Returns True when the turn ends.

        A single `match` over the typed union makes the three lanes explicit:
        `response` (correlated by `id`), `extension_ui_request` (discarded —
        no extensions are loaded), and the session-event union. `agent_end`
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
                logger.debug("PiAgent ignoring extension_ui_request (no extensions loaded): {}", parsed)
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
            case (
                ParsedTurnStart()
                | ParsedTurnEnd()
                | ParsedMessageStart()
                | ParsedQueueUpdate()
                | ParsedCompactionStart()
                | ParsedCompactionEnd()
                | ParsedAutoRetryStart()
                | ParsedSessionInfoChanged()
                | ParsedThinkingLevelChanged()
                | ParsedUnknownEvent()
            ):
                # Events this harness does not consume (turn/queue/compaction/
                # retry/session notices) plus any unrecognized type.
                logger.debug("PiAgent ignoring unconsumed event: {}", type(parsed).__name__)
                return False
            case _ as unreachable:
                assert_never(unreachable)

    def _refresh_diff_if_file_change(self, parsed: ParsedToolExecutionEnd) -> None:
        """Refresh the workspace diff after a successful file-mutating tool.

        Pi runs its own `edit`/`write`/`bash` loop and emits no signal that
        files changed beyond these tool-execution events, so Sculptor must
        regenerate the diff artifact itself. Mirrors Claude's `on_diff_needed`
        path (`should_send_diff_and_branch_name_artifacts`): trigger on a
        file-change tool, skip on tool errors.
        """
        on_diff_needed = self.on_diff_needed
        if on_diff_needed is None:
            return
        if parsed.tool_name in FILE_CHANGE_TOOL_NAMES and not parsed.is_error:
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
            text = state.accumulated_text or err.reason or "pi reported an in-stream error"
            raise PiCrashError(text, exit_code=None, metadata=None)
        # Other inner variants (text_start / text_end / thinking_* /
        # toolcall_* / start / done) are deliberately discarded.
        logger.debug("PiAgent ignoring assistantMessageEvent variant: {}", inner_type)

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
        A terminal-error `stopReason` raises `PiCrashError`;
        `stopReason:"aborted"` does too UNLESS an abort is expected (an
        interrupt is pending, or shutdown) — then it is the interrupted
        boundary and the partial content is finalized normally. Non-assistant
        `message_end`s (notably the role="user" prompt echo pi emits at
        agent-run start) are dropped.
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
        stop_reason = parsed.message.stop_reason
        if stop_reason == "error" or (stop_reason == "aborted" and not self._is_abort_expected()):
            text = extract_assistant_text(parsed.message) or state.accumulated_text or "pi message ended in error"
            raise PiCrashError(text, exit_code=None, metadata=None)
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
                )
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
        self._refresh_diff_if_file_change(parsed)
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

    def _handle_agent_end(self, parsed: ParsedAgentEnd, state: _TurnState) -> bool:
        """Turn boundary — return True so the dispatcher yields control.

        Per-message finalization happens in `_handle_message_end`, which
        emits each `ResponseBlockAgentMessage` with the IDs its partials
        already advertised. `agent_end` is the single signal that the
        agent run is fully idle; pi emits it once per `prompt`
        command. If `message_end` never fired for the current
        accumulating message (an edge case — e.g. abort mid-stream), the
        accumulated text is finalized here using the partials' IDs so
        the UI still settles on a stable block. A terminal `stopReason`
        on any assistant message in the final transcript raises
        `PiCrashError` — EXCEPT `stopReason:"aborted"` when an abort is
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
            if message.stop_reason == "aborted" and abort_expected:
                # Expected interrupted boundary: finalize the partial below, don't raise.
                continue
            text = extract_assistant_text(message) or state.accumulated_text or "pi agent ended in error"
            raise PiCrashError(text, exit_code=None, metadata=None)
        if state.accumulated_text:
            self._output_messages.put(
                ResponseBlockAgentMessage(
                    message_id=state.first_message_id,
                    role="assistant",
                    assistant_message_id=state.assistant_message_id,
                    content=(TextBlock(text=state.accumulated_text),),
                )
            )
        return True

    def _handle_auto_retry_end(self, parsed: ParsedAutoRetryEnd, state: _TurnState) -> None:
        if not parsed.success:
            text = parsed.final_error or state.accumulated_text or "pi exhausted retries"
            raise PiCrashError(text, exit_code=None, metadata=None)
        # Successful retry — a new agent run is about to begin; do not yield.

    def _handle_extension_error(self, parsed: ParsedExtensionError) -> None:
        # Non-terminal: extensions are not loaded in pi-basic but pi could
        # still surface one from its own bundled defaults.
        logger.info(
            "PiAgent extension_error: extension={} event={} error={}",
            parsed.extension_path,
            parsed.event,
            parsed.error,
        )
