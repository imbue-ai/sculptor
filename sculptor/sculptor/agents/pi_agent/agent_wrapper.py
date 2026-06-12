"""PiAgent — `DefaultAgentWrapper` subclass wrapping `pi --mode rpc`.

The agent spawns a long-lived `pi --mode rpc --session-dir <dir> --session-id
<id> --no-extensions -e <pinned extension> --append-system-prompt <prompt>`
subprocess and pumps user turns over JSONL stdin/stdout. The session flags
persist the conversation as a JSONL file under a per-task dir and pin its id
Sculptor-side, so relaunching after an agent-process restart resumes the full
conversation (`supports_session_resume`). The pinned `sculptor_backchannel`
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

Wire-protocol reference: the pi RPC protocol notes (pi 0.78.0).
"""

from __future__ import annotations

import json
import os
import queue
import time
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

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.common import generate_id
from imbue_core.ids import AssistantMessageID
from imbue_core.ids import ToolUseID
from imbue_core.sculptor.state.chat_state import AskUserQuestionData
from imbue_core.sculptor.state.chat_state import ContentBlockTypes
from imbue_core.sculptor.state.chat_state import QuestionOption
from imbue_core.sculptor.state.chat_state import TextBlock
from imbue_core.sculptor.state.chat_state import ToolResultBlock
from imbue_core.sculptor.state.chat_state import ToolUseBlock
from imbue_core.sculptor.state.chat_state import UserQuestion
from imbue_core.sculptor.state.chat_state import make_plan_approval_question
from imbue_core.sculptor.state.claude_state import get_tool_invocation_string
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from imbue_core.secrets_utils import Secret
from imbue_core.thread_utils import ObservableThread
from sculptor.agents.default.agent_wrapper import DefaultAgentWrapper
from sculptor.agents.default.utils import get_state_file_contents
from sculptor.agents.pi_agent.backchannel import PI_QUESTION_HEADER
from sculptor.agents.pi_agent.backchannel import PLAN_APPROVAL_DIALOG_TITLE
from sculptor.agents.pi_agent.backchannel import extension_ui_response_body
from sculptor.agents.pi_agent.backchannel import is_plan_approval
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
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import PlanModeAgentMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
from sculptor.interfaces.agents.errors import AgentCrashed
from sculptor.interfaces.agents.errors import PiBinaryNotFoundError
from sculptor.interfaces.agents.errors import PiCrashError
from sculptor.interfaces.agents.errors import PiVersionMismatchError
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.dependency_management_service import parse_pi_version
from sculptor.services.user_config.user_config import get_user_config_instance

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
#   InterruptProcessUserMessage      → supports_interruption
#   ClearContextUserMessage          → supports_context_reset
# ResumeAgentResponseRunnerMessage (supports_session_resume) and
# UserQuestionAnswerMessage (supports_interactive_backchannel) are no longer here —
# `_push_message` now handles both (resume directly; the answer via
# `_deliver_question_answer`).
_DEAD_LETTER_MESSAGE_TYPES: tuple[type[Message], ...] = (
    InterruptProcessUserMessage,
    ClearContextUserMessage,
)

# The backchannel extension shipped with Sculptor (package data; see
# pyproject.toml). Resolved next to this module so it works from an installed
# build as well as a repo checkout, then written into the environment at launch.
_BACKCHANNEL_EXTENSION_FILENAME: str = "sculptor_backchannel.ts"
_EXTENSIONS_SOURCE_DIR: Path = Path(__file__).resolve().parent / "extensions"

# Prepended to a turn's prompt while the agent is in plan mode. Drives the pi
# agent to explore read-only and present its plan via the `exit_plan_mode` tool
# for approval — the pi analogue of Claude's `is_in_plan_mode` user-instructions.
# (Divergence, REQ-CAP-ALL-3: read-only is requested in the prompt, not enforced
# by a tool allowlist this tranche — see the MR's Proposed FOLLOWUPS entry.)
_PLAN_MODE_PROMPT_PREFIX: str = """[PLAN MODE]
You are in plan mode. Investigate the request using read-only tools only (read files, inspect with read-only bash, grep, find, ls) and do NOT modify any files or run state-changing commands. Produce a clear, numbered plan describing what you would do. When the plan is ready, call the `exit_plan_mode` tool to present it to the user for approval. Do not begin implementing until the user approves; if they request revisions, refine the plan and call `exit_plan_mode` again.

The user's request follows:
"""


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
    # Absolute paths pi was launched with via `-e` (the pinned extension set);
    # used by the fail-loud posture to tell our extension's errors from foreign.
    _loaded_extension_paths: tuple[str, ...] = PrivateAttr(default=())
    # Interactive-backchannel state, shared between the dispatcher thread (which
    # sets `_pending_ui_request_id` when our extension opens a dialog) and the
    # request-handling thread (which clears it and writes the answer in
    # `_deliver_question_answer`). Guarded by `_backchannel_lock`.
    _backchannel_lock: Lock = PrivateAttr(default_factory=Lock)
    _pending_ui_request_id: str | None = PrivateAttr(default=None)
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
        if isinstance(message, UserQuestionAnswerMessage):
            # Mid-turn answer to a backchannel dialog the agent is blocked on:
            # delivered here on the request-handling thread (mirrors Claude's
            # `_try_deliver_answer_to_mcp`), not queued like a new prompt.
            self._deliver_question_answer(message)
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
        for filename in (_BACKCHANNEL_EXTENSION_FILENAME,):
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

    def _send_rpc(self, payload: dict[str, Any]) -> None:
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

    def _process_message_queue(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                message = self._input_agent_messages.get(timeout=0.5)
            except queue.Empty:
                continue
            self._update_plan_mode_from_message(message)
            with self._handle_user_message(message):
                prompt_id = generate_id()
                self._send_rpc({"type": "prompt", "id": prompt_id, "message": self._build_prompt_text(message)})
                turn_failed = False
                try:
                    self._consume_until_turn_end(prompt_id)
                except BaseException:
                    turn_failed = True
                    raise
                finally:
                    # Finalize any backchannel answer delivered mid-turn (its
                    # RequestSuccess was deferred to here so the post-answer
                    # content reached the frontend first). Runs on the failure
                    # path too, so the answer's request resolves instead of
                    # pinning the frontend "thinking" (mirrors Claude).
                    self._finalize_pending_answers(interrupted=turn_failed)

    def _update_plan_mode_from_message(self, message: ChatInputUserMessage) -> None:
        """Track plan mode across turns from the chat input's toggle flags.

        Mirrors `ClaudeProcessManager` (`process_manager.py:590-594`): entering
        sets the flag, leaving clears it; plan approval clears it later in
        `_deliver_question_answer`.
        """
        if message.enter_plan_mode:
            self._is_in_plan_mode = True
        elif message.exit_plan_mode:
            self._is_in_plan_mode = False

    def _build_prompt_text(self, message: ChatInputUserMessage) -> str:
        """The prompt text, with the plan-mode preamble while in plan mode."""
        if self._is_in_plan_mode:
            return f"{_PLAN_MODE_PROMPT_PREFIX}{message.text}"
        return message.text

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
        A terminal-error `stopReason` raises `PiCrashError`. Non-assistant
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
        if parsed.message.stop_reason in ("error", "aborted"):
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
        `PiCrashError`. `willRetry: true` means pi will start another
        agent run, typically after a transient failure — the current
        turn still ends so the caller can drain the next pump.
        """
        for message in parsed.messages:
            if message.role == "assistant" and message.stop_reason in ("error", "aborted"):
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
        """Fail loud on an error from our pinned extension; log foreign ones.

        A thrown extension surfaces as a non-terminal `extension_error`
        (RPC §5.2/§8). The locked posture for this tranche is **fail loud**: an
        error from the extension Sculptor loaded (`-e <path>`) fails the turn
        visibly via `PiCrashError` rather than continuing with a silently broken
        backchannel. An error from any other extension path stays log-only.
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
        """Map a backchannel dialog onto an AskUserQuestion and hold the turn.

        Our extension only opens blocking `select` (multiple-choice / plan
        approval) and `input` (free-form) dialogs. Each becomes an
        `AskUserQuestionAgentMessage`, and the request id is recorded so
        `_deliver_question_answer` can post the matching `extension_ui_response`.
        pi blocks until then (we never set a `timeout`), so the consume loop just
        keeps draining stdout — the turn is not over. Fire-and-forget methods
        (`notify`/`setStatus`/…) need no response and are ignored.
        """
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
        if parsed.method == "select" and parsed.title == PLAN_APPROVAL_DIALOG_TITLE:
            return make_plan_approval_question(tool_use_id=parsed.id)
        options = [QuestionOption(label=option, description="") for option in (parsed.options or [])]
        return AskUserQuestionData(
            questions=[
                UserQuestion(
                    question=parsed.title or "",
                    header=PI_QUESTION_HEADER,
                    options=options,
                    multi_select=False,
                    other_label="Other",
                )
            ],
            tool_use_id=parsed.id,
        )

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
