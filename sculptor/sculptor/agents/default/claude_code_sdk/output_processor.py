import json
import re
import time
from datetime import datetime
from queue import Empty
from queue import Queue
from threading import Event
from typing import Any
from typing import Callable

from loguru import logger

from sculptor.agents.default.artifact_creation import get_file_artifact_messages
from sculptor.agents.default.artifact_creation import should_refresh_task_list
from sculptor.agents.default.artifact_creation import should_send_diff_and_branch_name_artifacts
from sculptor.agents.default.claude_code_sdk.constants import TRANSIENT_ERROR_CODES
from sculptor.agents.default.claude_code_sdk.diff_tracker import DiffTracker
from sculptor.agents.default.claude_code_sdk.errors import ClaudeAPIError
from sculptor.agents.default.claude_code_sdk.harness import ClaudeCodeHarness
from sculptor.agents.default.claude_code_sdk.mcp_server import SculptorMcpServer
from sculptor.agents.default.claude_code_sdk.process_manager_utils import parse_claude_code_json_lines
from sculptor.agents.default.claude_code_sdk.transcript_collector import TranscriptCollector
from sculptor.agents.default.utils import get_state_file_contents
from sculptor.agents.default.utils import get_warning_message
from sculptor.database.models import AgentMessageID
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingDoneAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskNotificationAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskStartedAgentMessage
from sculptor.interfaces.agents.agent import ContextSummaryMessage
from sculptor.interfaces.agents.agent import Message
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PlanModeAgentMessage
from sculptor.interfaces.agents.agent import ResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import StreamingMessageCompleteAgentMessage
from sculptor.interfaces.agents.agent import TaskID
from sculptor.interfaces.agents.agent import TurnMetricsAgentMessage
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.agent import WarningAgentMessage
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.interfaces.agents.errors import AgentTransientError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import WorkspaceID
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import ContentBlockTypes
from sculptor.state.chat_state import FileBlock
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolInput
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.chat_state import TurnMetrics
from sculptor.state.chat_state import make_plan_approval_question
from sculptor.state.claude_state import ContentBlockStopEvent
from sculptor.state.claude_state import MessageStartEvent
from sculptor.state.claude_state import MessageStopEvent
from sculptor.state.claude_state import ParsedAssistantResponse
from sculptor.state.claude_state import ParsedEndResponse
from sculptor.state.claude_state import ParsedInitResponse
from sculptor.state.claude_state import ParsedStreamEvent
from sculptor.state.claude_state import ParsedTaskNotificationResponse
from sculptor.state.claude_state import ParsedTaskStartedResponse
from sculptor.state.claude_state import ParsedTaskUpdatedResponse
from sculptor.state.claude_state import ParsedToolResultResponse
from sculptor.state.claude_state import TextBlockStartEvent
from sculptor.state.claude_state import TextDeltaEvent
from sculptor.state.claude_state import ToolBlockStartEvent
from sculptor.state.claude_state import ToolInputDeltaEvent
from sculptor.state.claude_state import extract_media_tags_from_text
from sculptor.state.claude_state import split_text_and_media
from sculptor.state.messages import AssistantMessageID
from sculptor.web.data_types import OpenFileUiAction
from sculptor.web.ui_actions import publish_ui_action

# Matches a trailing incomplete <img or <video tag at the end of streamed text.
# During streaming, tokens arrive one at a time so we may see partial tags like
# ``<img src='/path/to/scr`` before the closing ``>`` arrives.  This pattern
# detects them so we can hide the fragment from the user.
_RE_TRAILING_MEDIA_TAG = re.compile(r"<(?:img|video)\b[^>]*$", re.IGNORECASE)

# Tools whose task_updated{completed} cleanup must be delayed by one turn.
# Monitor emits a follow-up event-delivery turn after task_updated, so clearing
# the task at the current turn's result/success would drop that delivery turn.
# Bash run_in_background does NOT do this — its task_updated indicates the bash
# subprocess is genuinely done, with no further turns coming.
_DEFERRED_COMPLETION_TOOLS: frozenset[str] = frozenset({"Monitor"})

# Grace period for the deferred cleanup. If no follow-up turn arrives within
# this window after task_updated{completed} for a deferred tool, the loop
# force-cleans-up so it can exit. This handles the rare case where the CLI
# drops both task_notification AND the follow-up event-delivery turn (observed
# when Monitor completes while a foreground tool is also executing).
_DEFERRED_CLEANUP_GRACE_SECONDS: float = 5.0

# Interval between diagnostic logs emitted while the output loop waits, after the
# final message, for still-pending background tasks or a scheduled wakeup turn.
_BACKGROUND_TASK_WAIT_LOG_INTERVAL_SECONDS: float = 10.0

# After the main loop exits with a get_context_usage request still pending, how
# long to keep draining the queue for the matching control response before giving
# up and flushing turn metrics without a context snapshot.
_CONTEXT_USAGE_DRAIN_TIMEOUT_SECONDS: float = 2.0

# Claude Code built-in commands that require an interactive terminal (TUI) and
# are not available when running in print mode (which is how Sculptor invokes
# Claude Code). When one of these is sent, Claude Code returns "Unknown skill: X"
# — but the skill isn't unknown, it's just unavailable. We detect this and show a
# more helpful message.
_CLAUDE_CODE_TUI_COMMANDS: frozenset[str] = frozenset(
    {
        "config",
        "cost",
        "doctor",
        "fast",
        "help",
        "init",
        "listen",
        "login",
        "logout",
        "memory",
        "model",
        "permissions",
        "resume",
        "review",
        "status",
        "terminal-setup",
        "vim",
    }
)


def _rewrite_unknown_skill_message(message: str) -> str:
    """Rewrite 'Unknown skill: X' messages from Claude Code to be more helpful.

    When Claude Code runs in print mode, TUI-only commands like /memory return
    'Unknown skill: memory'. This function replaces the misleading message with
    one that explains the command is not available in Sculptor.
    """
    if not message.startswith("Unknown skill:"):
        return message
    skill_name = message.removeprefix("Unknown skill:").strip()
    if skill_name in _CLAUDE_CODE_TUI_COMMANDS:
        return f"The /{skill_name} command is not available in Sculptor."
    return message


def _format_usage_limit_message(resets_at: object) -> str:
    """Build the user-facing message for a usage-limit rejection.

    ``resets_at`` is the CLI's ``rate_limit_info.resetsAt`` — a Unix timestamp
    in seconds (the CLI computes ``resetsAt - Date.now() / 1000``). When it is
    present and valid, append the local reset time so the user knows when they
    can continue.
    """
    base = "Claude usage limit reached."
    # bool is a subclass of int — exclude it so a stray ``True`` isn't formatted.
    if isinstance(resets_at, (int, float)) and not isinstance(resets_at, bool) and resets_at > 0:
        try:
            reset_local = datetime.fromtimestamp(resets_at)
        except (OverflowError, OSError, ValueError):
            return base
        return f"{base} Your limit will reset at {reset_local:%Y-%m-%d %H:%M:%S}."
    return base


def _is_synthetic_user(data: dict) -> bool:
    """Return True if a ``user`` frame looks like the post-compaction summary.

    The CLI puts ``isSynthetic: true`` at the top level, but we also check
    inside ``message`` in case the shape changes across CLI versions.
    """
    if data.get("isSynthetic"):
        return True
    message = data.get("message")
    if isinstance(message, dict) and message.get("isSynthetic"):
        return True
    return False


def _extract_summary_text_from_synthetic_user(data: dict) -> str | None:
    """Extract the compaction summary text from a synthetic user frame.

    Handles content as a plain string (observed shape from claude 2.1.x) and
    as a list of content blocks (shape used by the fake CLI and potentially
    future CLI versions). Returns None if no text can be extracted.
    """
    message = data.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    return text
    return None


def is_first_user_message_of_conversation(environment: AgentExecutionEnvironment, harness: ClaudeCodeHarness) -> bool:
    """Return True iff this conversation has not yet seen a Claude session init.

    The signal is the presence of the harness's session-id state file in the
    workspace state directory, which ``ClaudeOutputProcessor._parse_init_response``
    (in this module) writes on the very first init response of each session.
    Because the file lives on disk, the answer survives ``ProcessManager``
    re-instantiation across Sculptor restarts. If the lifecycle of that file
    ever changes, the semantics of this helper must be re-validated.
    """
    return get_state_file_contents(environment, harness.session_id_state_file_name) is None


class ClaudeOutputProcessor:
    def __init__(
        self,
        process: RunningProcess,
        source_command: str,
        output_message_queue: Queue[Message],
        environment: AgentExecutionEnvironment,
        diff_tracker: DiffTracker | None,
        task_id: TaskID,
        session_id_written_event: Event,
        harness: ClaudeCodeHarness,
        streaming_enabled: bool = True,
        on_diff_needed: Callable[[], None] | None = None,
        on_plan_mode_changed: Callable[[bool], None] | None = None,
        interrupted_event: Event | None = None,
        transcript_collector: TranscriptCollector | None = None,
        mcp_server: SculptorMcpServer | None = None,
        workspace_id: WorkspaceID | None = None,
    ):
        self.process = process
        self.source_command = source_command
        self.output_message_queue = output_message_queue
        self.environment = environment
        self.diff_tracker = diff_tracker
        self.task_id = task_id
        self.session_id_written_event = session_id_written_event
        self._harness: ClaudeCodeHarness = harness
        self.streaming_enabled = streaming_enabled
        self.on_diff_needed = on_diff_needed
        self._on_plan_mode_changed = on_plan_mode_changed
        self._interrupted_event: Event | None = interrupted_event
        self._transcript_collector = transcript_collector
        self._mcp_server: SculptorMcpServer | None = mcp_server
        self._workspace_id = workspace_id
        # Most recent .claude/plans/* path observed via Write/Edit/MultiEdit tool
        # blocks. Read by _maybe_handle_exit_plan_mode to populate the synthesized
        # approval question and to publish OpenFileUiAction. Cleared post-publish
        # so the next turn starts fresh.
        self._recent_plan_file_path: str | None = None
        if self._mcp_server is not None:
            self._mcp_server.set_respond(self._respond_to_control_request)

        self.queue = self.process.get_queue()
        # The current assistant message ID corresponds to the entire turn, which may contain multiple messages (assistant message + tool results)
        # We happen to set the current_message_id to be the messageID of the first assistant message in the turn
        # We might want to consider distinguishing between turn ID and message ID in the future
        self.current_turn_id: AssistantMessageID | None = None
        self.last_assistant_message: ResponseBlockAgentMessage | None = None
        self.tool_use_map: dict[str, tuple[str, ToolInput]] = {}
        self._tool_start_times: dict[str, float] = {}
        self.found_final_message = False
        self._turn_start_time: float = time.monotonic()
        # Track background tasks that have started but not yet completed.
        # After the final result message, the output loop must stay alive
        # until all background tasks finish (otherwise close_stdin + SIGTERM
        # kills in-flight Bash background tasks).
        self._pending_background_tasks: set[str] = set()
        # Task IDs that received task_updated with status=completed/failed/stopped.
        # The CLI emits task_updated when a background task finishes mid-turn
        # (while busy with another tool call), but may not emit
        # task_notification. At result time, pending tasks in this set are
        # cleared to prevent the output loop from waiting forever.
        self._completed_via_task_updated: set[str] = set()
        # Tasks whose task_updated{completed} cleanup is deferred by one turn.
        # Used for Monitor, which emits a follow-up event-delivery turn after
        # the task_updated; clearing immediately at the current turn's result
        # cuts off that delivery turn before the agent can react. Promoted to
        # _completed_via_task_updated when the next ``system/init`` arrives.
        self._completed_pending_deferred: set[str] = set()
        # Wall-clock deadline for the deferred cleanup. If no follow-up turn
        # arrives within this grace period (e.g. Monitor's task_notification
        # was dropped while another tool was executing), the idle path force-
        # promotes the deferred set so the loop can exit.
        self._completed_pending_deferred_deadline: float | None = None
        # task_id -> originating tool name (e.g. "Bash", "Monitor"). Recorded
        # at task_started time so task_updated handling can distinguish tools
        # that need deferred cleanup (Monitor) from those that don't (Bash).
        self._task_id_to_tool_name: dict[str, str] = {}
        # Timestamp when found_final_message was set. Used for diagnostic
        # logging when waiting for background task notifications.
        self._final_message_time: float | None = None
        # Last time we emitted a diagnostic log for background task waiting.
        self._last_bg_task_log_time: float = 0.0
        # Whether the agent called ScheduleWakeup during this turn. When set,
        # the output loop stays alive after the first result message, waiting
        # for the wakeup turn (a second init → assistant → result cycle) to
        # arrive from the CLI.
        self._pending_wakeup: bool = False
        # Last time we received any stdout line from the CLI. Used to detect
        # hangs where the CLI stops producing output after an interrupt.
        self._last_output_time: float = time.monotonic()
        # After an interrupt, if the CLI produces no output for this long
        # before the end-of-turn message, we assume it's hung and break out
        # of the loop. The process manager will then SIGTERM the CLI. This
        # only applies after an interrupt has been sent — during normal
        # operation, tool execution can take arbitrarily long.
        self._idle_timeout_seconds: float = 60.0

        self._is_streaming_turn = False
        # Finalized streaming content blocks, keyed by the SDK's streaming index.
        # The dict is sparse — a missing index means that slot was media-only or
        # never produced a renderable block. Empty-string TextBlocks must never
        # appear here; they are filtered at the materialization boundary.
        self._completed_streaming_blocks: dict[int, ContentBlockTypes] = {}
        self._text_accumulators: dict[int, str] = {}
        self._tool_accumulators: dict[int, dict[str, Any]] = {}
        # FileBlocks (plus the interleaved text after them) extracted from streamed
        # text by _finalize_block_from_accumulator, keyed by the streaming index of
        # the text block they were extracted from. Keying by source index lets
        # _materialize_content splice each <img>/<video> back in right after its
        # source text — preserving the order the model emitted it — even when a tool
        # block precedes that text in the same message.
        self._extracted_file_blocks: dict[int, list[TextBlock | FileBlock]] = {}
        # Persistent message ID for the ChatMessage, generated at the first MessageStartEvent.
        # Used in partials and the first ResponseBlockAgentMessage to ensure stable IDs.
        self._first_response_message_id: AgentMessageID | None = None
        self._used_first_response_id: bool = False
        # Tracks the parent_tool_use_id for the current streaming turn (non-null for subagent messages).
        self._current_parent_tool_use_id: str | None = None
        # Tracks the parent_tool_use_id of the most recently STARTED turn, persisting
        # across MessageStop (which clears _current_parent_tool_use_id). Used to
        # detect subagent context switches so the next ChatMessage gets a fresh
        # _first_response_message_id and doesn't collide with the prior turn.
        self._last_response_parent_tool_use_id: str | None = None
        # Set of turn IDs that were processed via streaming. Used to route the
        # ParsedAssistantResponse to the streaming persistence path even after
        # MessageStopEvent has reset _is_streaming_turn.
        self._streamed_turn_ids: set[str] = set()
        # Buffer for persistence ResponseBlockAgentMessage during active streaming.
        # Claude Code emits the ParsedAssistantResponse (type: "assistant") before
        # content_block_stop and message_stop. If we emit the persistence message
        # immediately, it arrives in message_conversion before the streaming partial,
        # causing duplicate ToolUseBlocks. Buffer it until after MessageStopEvent.
        self._buffered_persistence_message: ResponseBlockAgentMessage | None = None

        # Tool IDs already handled by _maybe_handle_ask_user_question /
        # _maybe_handle_exit_plan_mode / _maybe_handle_enter_plan_mode.
        # Prevents duplicate signals when both the ParsedAssistantResponse
        # path and the streaming content_block_stop path fire for the same tool.
        self._intercepted_tool_ids: set[str] = set()

        # Auto-compaction detection state
        self._session_id: str | None = None
        self._auto_compacting_emitted: bool = False

        # End-of-turn context usage request state
        self._pending_context_request_id: str | None = None
        self._context_request_counter: int = 0
        # Turn metrics stashed by _parse_stream_end_response; emitted once the
        # post-loop drain receives the get_context_usage response so the
        # context snapshot can be attached. Flushed with whatever context data
        # is available if the response never arrives.
        self._pending_turn_metrics: TurnMetrics | None = None

    @classmethod
    def build_and_process_output(
        cls,
        process: RunningProcess,
        source_command: str,
        output_message_queue: Queue[Message],
        environment: AgentExecutionEnvironment,
        diff_tracker: DiffTracker | None,
        task_id: TaskID,
        session_id_written_event: Event,
        harness: ClaudeCodeHarness,
        streaming_enabled: bool = True,
        on_diff_needed: Callable[[], None] | None = None,
        on_plan_mode_changed: Callable[[bool], None] | None = None,
        interrupted_event: Event | None = None,
        transcript_collector: TranscriptCollector | None = None,
        mcp_server: SculptorMcpServer | None = None,
        workspace_id: WorkspaceID | None = None,
    ) -> bool:
        processor = cls(
            process=process,
            source_command=source_command,
            output_message_queue=output_message_queue,
            environment=environment,
            diff_tracker=diff_tracker,
            task_id=task_id,
            session_id_written_event=session_id_written_event,
            harness=harness,
            streaming_enabled=streaming_enabled,
            on_diff_needed=on_diff_needed,
            on_plan_mode_changed=on_plan_mode_changed,
            interrupted_event=interrupted_event,
            transcript_collector=transcript_collector,
            mcp_server=mcp_server,
            workspace_id=workspace_id,
        )
        return processor._process_output()

    def _process_output(self) -> bool:
        while (not self.found_final_message or self._pending_background_tasks or self._pending_wakeup) and (
            not self.process.is_finished() or not self.queue.empty()
        ):
            try:
                line, is_stdout = self.queue.get(timeout=0.1)
            except Empty:
                now = time.monotonic()
                if not self.found_final_message:
                    # Detect hung CLI after interrupt: if we sent an interrupt
                    # but no stdout line has arrived for _idle_timeout_seconds
                    # and we never got the end-of-turn message, the CLI is
                    # stuck. Break out so the process manager can SIGTERM it.
                    # During normal operation (no interrupt), we wait
                    # indefinitely — tool execution can take arbitrarily long.
                    if self._interrupted_event is not None and self._interrupted_event.is_set():
                        idle = now - self._last_output_time
                        if idle >= self._idle_timeout_seconds:
                            logger.warning(
                                "CLI idle for {:.0f}s without end-of-turn message — assuming hung (pending_bg_tasks={}, process_finished={}, turn_elapsed={:.0f}s)",
                                idle,
                                self._pending_background_tasks,
                                self.process.is_finished(),
                                now - self._turn_start_time,
                            )
                            break
                else:
                    # Force-promote deferred completions whose grace period has
                    # expired. The follow-up event-delivery turn never arrived
                    # (e.g. CLI dropped it because another tool was executing
                    # when the deferred-tool task completed). Promoting moves
                    # the task into _completed_via_task_updated so the cleanup
                    # path at the next result/success — or the immediate cleanup
                    # below — clears it and lets the loop exit.
                    if (
                        self._completed_pending_deferred
                        and self._completed_pending_deferred_deadline is not None
                        and now >= self._completed_pending_deferred_deadline
                    ):
                        logger.info(
                            "Deferred-completion grace period expired ({:.1f}s); force-clearing {} task(s): {}",
                            _DEFERRED_CLEANUP_GRACE_SECONDS,
                            len(self._completed_pending_deferred),
                            self._completed_pending_deferred,
                        )
                        completed_mid_turn = self._pending_background_tasks & self._completed_pending_deferred
                        if completed_mid_turn:
                            self._pending_background_tasks -= completed_mid_turn
                        self._completed_pending_deferred.clear()
                        self._completed_pending_deferred_deadline = None
                    # Periodic diagnostic logging when waiting for background
                    # tasks or a scheduled wakeup after the final message.
                    if (
                        self._pending_background_tasks or self._pending_wakeup
                    ) and now - self._last_bg_task_log_time >= _BACKGROUND_TASK_WAIT_LOG_INTERVAL_SECONDS:
                        self._last_bg_task_log_time = now
                        elapsed = now - (self._final_message_time or now)
                        logger.info(
                            "Waiting {:.0f}s for {} background task(s): {} pending_wakeup={} (process_finished={}, queue_empty={}, reader_thread_alive={})",
                            elapsed,
                            len(self._pending_background_tasks),
                            self._pending_background_tasks,
                            self._pending_wakeup,
                            self.process.is_finished(),
                            self.queue.empty(),
                            getattr(getattr(self.process, "_thread", None), "is_alive", lambda: "unknown")(),
                        )
                continue

            self._last_output_time = time.monotonic()

            if not line.strip():
                continue
            if not is_stdout:
                # stderr lines are not surfaced to the UI; discard them.
                continue
            logger.trace("Received line from process: {}", line.strip())

            if self._transcript_collector is not None:
                self._transcript_collector.record_stdout(line)

            # Usage-limit rejection (SCU-1129): the CLI reports a rejected
            # rate_limit_event and then pauses without a terminating result, so
            # end the turn with an error instead of waiting forever.
            self._raise_if_usage_limit_rejected(line)

            # Check for control_response matching our pending context usage request.
            context_response = self._is_context_usage_response(line)
            if context_response is not None:
                self._handle_context_usage_response(context_response)
                continue

            # Handle control_request messages from the CLI (permission
            # requests and hook callbacks).
            if self._maybe_handle_control_request(line):
                continue

            # Detect the start of compaction from the system/status frame. This
            # fires for both auto-compaction and user-triggered `/compact` (sent
            # as a plain user message). For auto-compaction the PreCompact hook
            # callback typically sets the flag first, but setting it again is
            # idempotent.
            if not self._auto_compacting_emitted:
                self._maybe_detect_compaction_start(line)

            # Compaction completion: after the start signal the CLI sends
            # system/status, system/compact_boundary, then a synthetic user
            # message containing the compaction summary.  We skip system
            # messages (they're internal compaction protocol) and wait for the
            # user message with isSynthetic=true, which is the actual summary.
            # Any other non-system message (assistant, result) triggers the
            # generic fallback.
            if self._auto_compacting_emitted:
                try:
                    data_peek = json.loads(line)
                    msg_type = data_peek.get("type") if isinstance(data_peek, dict) else None
                    msg_subtype = data_peek.get("subtype") if isinstance(data_peek, dict) else None
                    if isinstance(data_peek, dict) and msg_type == "user" and _is_synthetic_user(data_peek):
                        # The synthetic user message carries the real summary.
                        self._complete_auto_compaction_with_summary(data_peek)
                    elif msg_type == "system" and msg_subtype == "compact_boundary":
                        # The CLI emits compact_boundary between pre- and
                        # post-compaction streaming. Reset the chat-id state
                        # here so the next MessageStartEvent mints a fresh id
                        # for the post-compaction turn. Doing it later (in the
                        # completion handlers) is too late on the fallback
                        # path: by then the post-compaction streaming has
                        # already populated _first_response_message_id and
                        # _streamed_turn_ids, and the same assistant line is
                        # about to be reprocessed via the streamed-turn branch
                        # in _process_output, which would crash on the null.
                        self._reset_streaming_state_for_compaction()
                    elif msg_type in ("assistant", "result"):
                        # Only these types indicate compaction finished without
                        # a summary arriving — every other frame (system status,
                        # hook callbacks, rate_limit_event, non-synthetic user
                        # echoes, etc.) can appear mid-compaction and must not
                        # dismiss the indicator.
                        logger.info(
                            "Compaction completion fallback triggered by {} message",
                            msg_type,
                        )
                        self._complete_auto_compaction_fallback()
                    else:
                        logger.debug(
                            "Ignoring {} message during compaction; keeping indicator up",
                            msg_type,
                        )
                except (json.JSONDecodeError, ValueError, AttributeError) as e:
                    logger.debug("Non-JSON line during compaction (keeping indicator up): {}", e)

            try:
                result = parse_claude_code_json_lines(
                    line,
                    self.tool_use_map,
                    self.diff_tracker,
                )
            except json.JSONDecodeError as e:
                # Non-JSON lines can appear when the Anthropic API returns
                # malformed data or the CLI emits unexpected debug output.
                # Rather than crashing the agent, skip the bad line and surface
                # a warning so the user knows something went wrong.
                truncated_line = line[:200] + ("..." if len(line) > 200 else "")
                warning = get_warning_message(
                    message=f"Received malformed output from Claude CLI (non-JSON line): {truncated_line}",
                    error=e,
                    task_id=self.task_id,
                )
                self.output_message_queue.put(warning)
                continue

            if result is None:
                continue

            if isinstance(result, ParsedStreamEvent):
                self._handle_stream_event(result)
                # No further processing needed for stream events
                continue

            if isinstance(result, ParsedInitResponse):
                self._parse_init_response(result)

            elif isinstance(result, ParsedEndResponse):
                self._parse_stream_end_response(result)

            elif isinstance(result, ParsedAssistantResponse):
                if result.message_id in self._streamed_turn_ids:
                    # This turn was already displayed via streaming partials. Only emit
                    # the persistence message for DB storage (no UI duplication).
                    # Use the pre-generated ID for the first ResponseBlockAgentMessage,
                    # so it matches the ChatMessage.id set by partials.
                    if not self._used_first_response_id:
                        message_id = self._first_response_message_id
                        assert message_id is not None
                        self._used_first_response_id = True
                    else:
                        message_id = AgentMessageID()
                    persistence_msg = ResponseBlockAgentMessage(
                        role="assistant",
                        message_id=message_id,
                        assistant_message_id=AssistantMessageID(result.message_id),
                        content=tuple(result.content_blocks),
                        parent_tool_use_id=result.parent_tool_use_id,
                    )
                    self.last_assistant_message = persistence_msg

                    # Claude Code emits ParsedAssistantResponse BEFORE
                    # content_block_stop / message_stop.  If a PreToolUse hook
                    # (e.g. AskUserQuestion) blocks the CLI at this point, the
                    # content_block_stop events are never emitted, so
                    # _finalize_block_from_accumulator never runs.  Detect
                    # interceptable tools here as a fallback so we don't lose
                    # AUQ/ExitPlanMode/EnterPlanMode signals.
                    for block in result.content_blocks:
                        if isinstance(block, ToolUseBlock):
                            self.tool_use_map[block.id] = (block.name, block.input)
                            self._maybe_record_plan_file_write(block)
                            self._maybe_handle_ask_user_question(block)
                            self._maybe_handle_exit_plan_mode(block)
                            self._maybe_handle_enter_plan_mode(block)

                    if self._is_streaming_turn:
                        # Buffer this message so it's emitted after
                        # StreamingMessageCompleteAgentMessage, allowing
                        # message_conversion to deduplicate via existing_tool_use_ids.
                        logger.trace("Buffering persistence message until streaming completes")
                        self._buffered_persistence_message = persistence_msg
                    else:
                        logger.trace("Emitting assistant response for persistence")
                        self.output_message_queue.put(persistence_msg)
                else:
                    self._parse_assistant_response(result)

            elif isinstance(result, ParsedToolResultResponse):
                self._parse_tool_result_response(result)

            elif isinstance(result, ParsedTaskStartedResponse):
                logger.debug("Background task started: task_id={} tool_use_id={}", result.task_id, result.tool_use_id)
                self._pending_background_tasks.add(result.task_id)
                # Record which tool launched this task. Used by task_updated
                # handling to defer cleanup for tools (e.g. Monitor) that emit
                # follow-up event-delivery turns. tool_use_map is populated by
                # _parse_assistant_response, which always emits the tool_use
                # before the CLI emits task_started.
                tool_use_info = self.tool_use_map.get(result.tool_use_id)
                if tool_use_info is not None:
                    self._task_id_to_tool_name[result.task_id] = tool_use_info[0]
                self.output_message_queue.put(
                    BackgroundTaskStartedAgentMessage(
                        message_id=AgentMessageID(),
                        background_task_id=result.task_id,
                        tool_use_id=result.tool_use_id,
                        description=result.description,
                        task_type=result.task_type,
                    )
                )

            elif isinstance(result, ParsedTaskNotificationResponse):
                logger.debug("Background task completed: task_id={} status={}", result.task_id, result.status)
                self._pending_background_tasks.discard(result.task_id)
                # If the task was deferred (Monitor's bash exited and we were
                # waiting on the follow-up turn), the actual notification
                # arriving supersedes the deferred path — drop the deferred
                # entry so it doesn't promote later as a stale completion.
                self._completed_pending_deferred.discard(result.task_id)
                if not self._completed_pending_deferred:
                    self._completed_pending_deferred_deadline = None
                # A new turn (init → assistant → result) always follows a
                # task_notification, so reset found_final_message to keep the
                # loop open for it.  Without this, the loop exits immediately
                # after the last pending task is cleared — before reading the
                # post-notification assistant response.
                self.found_final_message = False
                self.output_message_queue.put(
                    BackgroundTaskNotificationAgentMessage(
                        message_id=AgentMessageID(),
                        background_task_id=result.task_id,
                        tool_use_id=result.tool_use_id,
                        status=result.status,
                        summary=result.summary,
                        duration_seconds=(result.duration_ms / 1000.0) if result.duration_ms is not None else None,
                    )
                )
                # Note: we intentionally do NOT reset _first_response_message_id
                # here.  The notification is an out-of-band status signal and must
                # not disturb the streaming state of the current turn.  The reset
                # happens in _parse_init_response when the new request cycle begins
                # (system/init always follows the notification).  See SCU-267.

            elif isinstance(result, ParsedTaskUpdatedResponse):
                # task_updated with patch.status="completed" is emitted when a
                # background task finishes mid-turn (while the CLI is busy
                # executing another tool call). The CLI may not emit
                # task_notification in this case. Record the completion so
                # _parse_stream_end_response can clear it at result time.
                #
                # Exception: for tools in _DEFERRED_COMPLETION_TOOLS (Monitor),
                # the CLI emits a follow-up event-delivery turn AFTER
                # task_updated. Clearing at the current turn's result/success
                # would drop that delivery turn. Defer cleanup until the next
                # init promotes the entry, or the grace period expires.
                if result.status in ("completed", "failed", "stopped"):
                    logger.info(
                        "Background task updated: task_id={} status={}",
                        result.task_id,
                        result.status,
                    )
                    tool_name = self._task_id_to_tool_name.get(result.task_id, "")
                    if tool_name in _DEFERRED_COMPLETION_TOOLS:
                        self._completed_pending_deferred.add(result.task_id)
                        if self._completed_pending_deferred_deadline is None:
                            self._completed_pending_deferred_deadline = (
                                time.monotonic() + _DEFERRED_CLEANUP_GRACE_SECONDS
                            )
                    else:
                        self._completed_via_task_updated.add(result.task_id)

        logger.debug(
            "Process stream ended (found_final_message={}, pending_bg_tasks={}, pending_wakeup={}, process_finished={}, queue_empty={})",
            self.found_final_message,
            self._pending_background_tasks,
            self._pending_wakeup,
            self.process.is_finished(),
            self.queue.empty(),
        )

        # After the main loop exits, if we have a pending get_context_usage request
        # (sent at end-of-turn), briefly drain remaining queue lines to catch the
        # response. Without this, found_final_message causes the loop to exit before
        # the control response arrives, leaving the indicator with stale data.
        if self._pending_context_request_id is not None:
            deadline = time.monotonic() + _CONTEXT_USAGE_DRAIN_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                try:
                    line, is_stdout = self.queue.get(timeout=0.1)
                except Empty:
                    if self.process.is_finished():
                        break
                    continue
                if is_stdout:
                    context_response = self._is_context_usage_response(line)
                    if context_response is not None:
                        self._handle_context_usage_response(context_response)
                        break

        # If TurnMetrics was stashed but the context response never arrived,
        # flush it now without context data so the turn footer at least shows
        # duration/tokens.
        self._flush_pending_turn_metrics()

        # When the process was interrupted (killed before emitting ParsedEndResponse),
        # emit fallback metrics with just the elapsed duration so the turn footer
        # can display "Stopped · X.Xs" instead of only "Stopped".
        if not self.found_final_message:
            elapsed = time.monotonic() - self._turn_start_time
            changed_files = self.diff_tracker.get_changed_file_paths() if self.diff_tracker else []
            self.output_message_queue.put(
                TurnMetricsAgentMessage(
                    turn_metrics=TurnMetrics(duration_seconds=elapsed, changed_files=changed_files)
                )
            )
            if self._transcript_collector is not None:
                self._transcript_collector.finalize_turn(status="interrupted")

        return self.found_final_message

    def _raise_if_usage_limit_rejected(self, line: str) -> None:
        """Surface a usage-limit error when the CLI reports the request was rejected.

        The Claude CLI emits a ``rate_limit_event`` frame whenever its rate-limit
        state changes. When the account usage limit is reached the frame carries
        ``rate_limit_info.status == "rejected"`` and the CLI then *pauses* — it
        keeps the process alive waiting for the limit to reset and never emits a
        terminating ``result``. These frames are informational (the CLI's own SDK
        adapter ignores them, and so does ``parse_claude_code_json_lines``), so
        the output loop would otherwise wait forever and the "Thinking..."
        indicator would spin indefinitely (SCU-1129).

        Detect the rejection and raise a transient error so the turn ends with an
        error block, exactly like the API-429 path. Overage (pay-as-you-go)
        credit being available means the request can still proceed, so only a
        rejection with no usable overage is treated as terminal.
        """
        # Cheap pre-filter so we don't json-parse every (often large) stdout line.
        if "rate_limit_event" not in line:
            return
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(data, dict) or data.get("type") != "rate_limit_event":
            return
        rate_limit_info = data.get("rate_limit_info")
        if not isinstance(rate_limit_info, dict) or rate_limit_info.get("status") != "rejected":
            return
        # Overage available → the CLI can keep going on pay-as-you-go credit, so
        # the turn is not actually blocked; leave it alone.
        if rate_limit_info.get("overageStatus") in ("allowed", "allowed_warning"):
            return
        # Interrupts are handled separately by the process manager; don't convert
        # an interrupted turn into a usage-limit error.
        if self._interrupted_event is not None and self._interrupted_event.is_set():
            return
        message = _format_usage_limit_message(rate_limit_info.get("resetsAt"))
        logger.info("Usage limit reached (rate_limit_event status=rejected): {}", message)
        raise AgentTransientError(message, exit_code=self.process.returncode)

    def _parse_init_response(self, result: ParsedInitResponse) -> None:
        session_id = result.session_id
        self._session_id = session_id
        session_file_path = self.environment.get_state_path() / self._harness.session_id_state_file_name
        self.environment.write_file(str(session_file_path), session_id)
        self.session_id_written_event.set()
        logger.info("Stored session_id: {}", session_id)

        # A ScheduleWakeup fires as a second init message on the same session.
        # When the wakeup init arrives, reset found_final_message so the loop
        # processes the wakeup turn (assistant → result) instead of exiting.
        if self._pending_wakeup:
            logger.info("Wakeup init received — resetting for wakeup turn")
            self._pending_wakeup = False
            self.found_final_message = False

        # A deferred-completion task (e.g. Monitor) is waiting for its follow-up
        # event-delivery turn. This init *is* that follow-up turn, so promote
        # the deferred entries: they will be cleared at this new turn's
        # result/success, giving the agent the entire follow-up turn to react
        # to the event before the loop exits.
        if self._completed_pending_deferred:
            logger.info(
                "Deferred-completion follow-up turn started; promoting {} task(s) for cleanup",
                len(self._completed_pending_deferred),
            )
            self._completed_via_task_updated.update(self._completed_pending_deferred)
            self._completed_pending_deferred.clear()
            self._completed_pending_deferred_deadline = None

        # A new request cycle means the next MessageStartEvent should get its
        # own ChatMessage ID.  Reset here (not in the task-notification handler)
        # so the reset never interrupts an active streaming turn.  See SCU-267.
        self._first_response_message_id = None
        self._used_first_response_id = False

        # Request context usage immediately so the indicator refreshes at the
        # start of each CLI process. This covers post-compaction, post-clear,
        # and normal turn starts.
        self._send_context_usage_request()

    def _parse_stream_end_response(self, result: ParsedEndResponse) -> None:
        logger.debug("Stream ended")

        # Build per-turn metrics from the end response.  We stash them instead
        # of emitting immediately so the downstream get_context_usage response
        # (which arrives after _parse_stream_end_response returns, handled by
        # the post-loop drain in _process_output) can attach the context
        # snapshot to the same TurnMetrics before emission.  This gives each
        # turn footer an accurate point-in-time value.
        # Use wall-clock time from when the output processor was created, not
        # the API-reported duration_ms which only measures LLM response time.
        elapsed = time.monotonic() - self._turn_start_time
        input_tokens = result.input_tokens
        output_tokens = result.output_tokens
        if input_tokens is not None and output_tokens is not None:
            changed_files = self.diff_tracker.get_changed_file_paths() if self.diff_tracker else []
            self._pending_turn_metrics = TurnMetrics(
                duration_seconds=elapsed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=None,
                changed_files=changed_files,
            )

        # Refresh workspace diff if any file-changing tools were used during this turn.
        # This serves as a fallback for cases where _parse_tool_result_response was not
        # reached (e.g. due to tool result parsing failures), as tool_use_map is populated
        # from assistant response streaming events which always succeed.
        on_diff_needed = self.on_diff_needed
        if on_diff_needed is not None:
            for tool_name, tool_input in self.tool_use_map.values():
                if should_send_diff_and_branch_name_artifacts(tool_name, tool_input):
                    logger.info("Stream ended with file-changing tools used, refreshing workspace diff")
                    on_diff_needed()
                    break

        # Request an accurate context snapshot right after the turn ends.
        self._send_context_usage_request()

        # if there is an error, raise the appropriate error to be handled in the context manager
        # However, if the agent was interrupted, suppress the error — the process manager
        # handles interrupts separately (see _read_output_from_process in process_manager.py).
        if result.is_error:
            if self._interrupted_event is not None and self._interrupted_event.is_set():
                logger.info("Suppressing error end response because agent was interrupted: {}", result.result)
            elif result.result.startswith("API Error"):
                logger.info("API Error: stdout={}, stderr={}", self.process.read_stdout(), self.process.read_stderr())
                if any(result.result.startswith(f"API Error: {code}") for code in TRANSIENT_ERROR_CODES):
                    raise AgentTransientError(result.result, exit_code=self.process.returncode)
                raise ClaudeAPIError(result.result, exit_code=self.process.returncode)
            else:
                raise AgentClientError(result.result, exit_code=self.process.returncode)

        # Claude Code may return a non-error result with no assistant messages — e.g. when
        # an invalid slash command like "/fixbug" is sent, the result contains "Unknown skill:
        # fixbug" but is_error is false and no assistant response is emitted. Surface the
        # result text as a warning so the user sees it.
        if self.last_assistant_message is None and result.result:
            message = _rewrite_unknown_skill_message(result.result)
            self.output_message_queue.put(get_warning_message(message, None, self.task_id))

        if self._transcript_collector is not None:
            self._transcript_collector.finalize_turn(status="completed", cost_usd=result.total_cost_usd)

        self.found_final_message = True
        self._final_message_time = time.monotonic()

        # Clear pending background tasks that already completed via task_updated.
        # The CLI emits task_updated(status=completed) when a background task
        # finishes mid-turn, but may not emit task_notification. Without this,
        # the output loop would wait forever for a notification that never comes.
        completed_mid_turn = self._pending_background_tasks & self._completed_via_task_updated
        if completed_mid_turn:
            logger.info(
                "Clearing {} background task(s) that completed mid-turn (via task_updated): {}",
                len(completed_mid_turn),
                completed_mid_turn,
            )
            self._pending_background_tasks -= completed_mid_turn

        if self._pending_background_tasks:
            logger.info(
                "Final message received with {} still-pending background task(s): {}",
                len(self._pending_background_tasks),
                self._pending_background_tasks,
            )

    def _parse_assistant_response(self, result: ParsedAssistantResponse) -> None:
        new_message_id = result.message_id
        new_blocks = result.content_blocks

        # Track tool names and file paths from ToolUseBlocks
        for block in new_blocks:
            if isinstance(block, ToolUseBlock):
                self.tool_use_map[block.id] = (block.name, block.input)
                self._tool_start_times[block.id] = time.monotonic()
                self._maybe_record_plan_file_write(block)
                self._maybe_handle_ask_user_question(block)
                self._maybe_handle_exit_plan_mode(block)
                self._maybe_handle_enter_plan_mode(block)

        logger.debug("Streaming new assistant message {}", new_message_id)
        logger.trace("New blocks: {}", new_blocks)
        if self.current_turn_id is None:
            self.current_turn_id = new_message_id
        self.last_assistant_message = ResponseBlockAgentMessage(
            role="assistant",
            message_id=AgentMessageID(),
            assistant_message_id=AssistantMessageID(new_message_id),
            content=tuple(new_blocks),
            parent_tool_use_id=result.parent_tool_use_id,
        )
        self.output_message_queue.put(self.last_assistant_message)
        # Keep the parent-tool tracker in lockstep with non-streamed messages.
        # Concurrent subagent output reaches the parent stream as full,
        # non-streamed `assistant` lines carrying a parent_tool_use_id rather
        # than as stream events, so MessageStartEvent never sees them. The next
        # streamed MessageStart compares new_parent against
        # _last_response_parent_tool_use_id to decide whether to mint a fresh
        # ChatMessage ID; if an interleaved subagent message left it stale, the
        # following main-agent turn (parent None -> None) would reuse the prior
        # turn's ID. The frontend keys chat messages by ID, so the colliding
        # turns overwrite each other and the agent's work vanishes. See SCU-1421.
        self._last_response_parent_tool_use_id = result.parent_tool_use_id

    def _parse_tool_result_response(self, result: ParsedToolResultResponse) -> None:
        assert self.current_turn_id is not None
        # Add tool results to current assistant message
        new_blocks: list[ToolResultBlock] = []
        logger.debug("Adding tool result to assistant message")
        logger.debug("{} new blocks", len(result.content_blocks))
        logger.trace("New blocks: {}", result.content_blocks)
        will_send_diff_and_branch_name_artifacts = False
        should_refresh_tasks = False
        now = time.monotonic()
        for block in result.content_blocks:
            assert isinstance(block, ToolResultBlock)
            start_time = self._tool_start_times.pop(block.tool_use_id, None)
            if start_time is not None:
                duration = now - start_time
                block = block.model_copy(update={"duration_seconds": duration})
            new_blocks.append(block)
            tool_info = self.tool_use_map.get(block.tool_use_id, None)
            if tool_info and not block.is_error:
                tool_name, tool_input = tool_info
                if not will_send_diff_and_branch_name_artifacts:
                    will_send_diff_and_branch_name_artifacts = should_send_diff_and_branch_name_artifacts(
                        tool_name, tool_input
                    )
                if not should_refresh_tasks and should_refresh_task_list(tool_name):
                    should_refresh_tasks = True

        self.last_assistant_message = ResponseBlockAgentMessage(
            role="assistant",
            message_id=AgentMessageID(),
            assistant_message_id=AssistantMessageID(self.current_turn_id),
            content=tuple(new_blocks),
            parent_tool_use_id=result.parent_tool_use_id,
        )
        self.output_message_queue.put(self.last_assistant_message)

        # Detect accepted ScheduleWakeup from the tool_use_result metadata.
        # When scheduledFor is set, Claude Code has accepted the wakeup and
        # will fire a second turn after the delay.
        if result.scheduled_wakeup_for is not None:
            logger.info(
                "ScheduleWakeup accepted (scheduledFor={}) — will keep process alive for wakeup turn",
                result.scheduled_wakeup_for,
            )
            self._pending_wakeup = True

        artifact_messages_to_send: list[UpdatedArtifactAgentMessage | WarningAgentMessage] = []

        if will_send_diff_and_branch_name_artifacts:
            logger.info("Contents of message indicate likely git state change, refreshing workspace diff")
            if self.on_diff_needed is not None:
                self.on_diff_needed()

        if should_refresh_tasks:
            if self._session_id is None:
                logger.info("Skipping task-list refresh: session_id not yet set (init response not seen)")
            else:
                artifact_messages_to_send.extend(
                    get_file_artifact_messages(
                        artifact_name=ArtifactType.PLAN,
                        environment=self.environment,
                        harness=self._harness,
                        session_id=self._session_id,
                        task_id=self.task_id,
                    )
                )

        for artifact_message in artifact_messages_to_send:
            if artifact_message is not None:
                self.output_message_queue.put(artifact_message)

    def _maybe_detect_compaction_start(self, line: str) -> None:
        """Detect the ``system/status status="compacting"`` frame.

        The CLI emits this frame at the start of a ``/compact`` command. This
        is our primary signal for user-typed ``/compact`` (the PreCompact hook
        also fires via ``_handle_hook_callback``, so whichever signal arrives
        first sets the flag). Idempotent with the hook callback path.
        """
        if self._auto_compacting_emitted:
            return
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        if data.get("type") != "system" or data.get("subtype") != "status":
            return
        if data.get("status") != "compacting":
            return
        logger.info("Compaction started (detected via system/status)")
        self._auto_compacting_emitted = True
        self.output_message_queue.put(AutoCompactingAgentMessage(message_id=AgentMessageID()))

    def _complete_auto_compaction_with_summary(self, data: dict) -> None:
        """Dismiss the indicator and emit a ContextSummaryMessage with the real summary.

        Called when a ``user`` message with ``isSynthetic: true`` arrives after
        compaction — this is the CLI's compaction summary.
        """
        logger.info("Auto-compaction completed (summary received via isSynthetic user message)")
        self._auto_compacting_emitted = False
        self.output_message_queue.put(AutoCompactingDoneAgentMessage(message_id=AgentMessageID()))

        summary_text = _extract_summary_text_from_synthetic_user(data)
        if summary_text is None:
            logger.warning(
                "Compaction summary extraction failed; data keys={}, message type={}",
                list(data.keys()),
                type(data.get("message")).__name__,
            )
            summary_text = "Context was automatically compacted."
        self.output_message_queue.put(ContextSummaryMessage(content=summary_text))
        # Refresh context usage after compaction so the indicator reflects the reduced token count.
        self._send_context_usage_request()

    def _complete_auto_compaction_fallback(self) -> None:
        """Dismiss the indicator with a generic summary when no real summary was found."""
        logger.info("Auto-compaction completed (output resumed, no summary found)")
        self._auto_compacting_emitted = False
        self.output_message_queue.put(AutoCompactingDoneAgentMessage(message_id=AgentMessageID()))
        self.output_message_queue.put(ContextSummaryMessage(content="Context was automatically compacted."))
        # Refresh context usage after compaction so the indicator reflects the reduced token count.
        self._send_context_usage_request()

    def _reset_streaming_state_for_compaction(self) -> None:
        """Reset streaming state so the post-compaction response gets a fresh ChatMessage ID.

        The CLI does not emit ``system/init`` after compaction (it sends
        ``system/status`` + ``system/compact_boundary`` instead), so the normal
        reset in ``_parse_init_response`` never fires. Without this, the
        post-compaction streaming reuses the pre-compaction ChatMessage ID,
        causing the frontend to deduplicate and reorder messages.

        Called when ``system/compact_boundary`` is observed — before the
        post-compaction ``MessageStartEvent`` fires, so the next
        ``MessageStartEvent`` sees ``_first_response_message_id is None`` and
        mints a fresh id. Calling this later (from the completion handlers)
        breaks the streamed-turn invariant in ``_process_output``.
        """
        self._first_response_message_id = None
        self._used_first_response_id = False
        self._is_streaming_turn = False
        self._completed_streaming_blocks = {}
        self._text_accumulators = {}
        self._tool_accumulators = {}
        self._extracted_file_blocks = {}
        self._current_parent_tool_use_id = None

    def _maybe_handle_ask_user_question(self, tool_block: ToolUseBlock) -> bool:
        """Detect ``mcp__sculptor__ask_user_question`` tool calls and emit an
        ephemeral message.

        Returns True if the tool block was an MCP AskUserQuestion call, False
        otherwise. Idempotent: a second call with the same tool_block.id is a
        no-op.
        """
        ask_tool_fqn = self._harness.mcp_ask_tool_fqn
        if tool_block.name != ask_tool_fqn:
            return False
        if tool_block.id in self._intercepted_tool_ids:
            return True
        self._intercepted_tool_ids.add(tool_block.id)

        # Stay in lockstep with the MCP server's strict input validation
        # (``mcp_server._validate_arguments``). The MCP server independently
        # responds with a JSON-RPC error so the agent can retry — no need to
        # surface a warning chip in chat.
        if not self._harness.is_valid_ask_user_question_input(tool_block.name, tool_block.input):
            logger.info(
                "AskUserQuestion tool input failed schema validation; skipping panel emission. input={}",
                tool_block.input,
            )
            return False
        question_data = AskUserQuestionData.model_validate(
            {**tool_block.input, "tool_use_id": tool_block.id}, strict=True
        )

        self.output_message_queue.put(
            AskUserQuestionAgentMessage(
                message_id=AgentMessageID(),
                question_data=question_data,
            )
        )
        if self._mcp_server is not None:
            self._mcp_server.register_tool_use_id(tool_block.id, ask_tool_fqn, tool_input=tool_block.input)
        return True

    def _maybe_record_plan_file_write(self, tool_block: ToolUseBlock) -> None:
        """Remember the latest plan-file path so a subsequent ExitPlanMode
        can carry it forward."""
        plan_path = self._harness.get_plan_file_path_from_tool_use(tool_block)
        if plan_path is not None:
            self._recent_plan_file_path = plan_path

    def _maybe_handle_exit_plan_mode(self, tool_block: ToolUseBlock) -> bool:
        """Detect ``mcp__sculptor__exit_plan_mode`` tool calls and emit a
        synthesized plan approval question.

        Returns True if the tool block was an MCP ExitPlanMode call, False
        otherwise. Idempotent: a second call with the same tool_block.id is a
        no-op.
        """
        exit_plan_mode_tool_fqn = self._harness.mcp_exit_plan_mode_tool_fqn
        if tool_block.name != exit_plan_mode_tool_fqn:
            return False
        if tool_block.id in self._intercepted_tool_ids:
            return True
        self._intercepted_tool_ids.add(tool_block.id)

        # ``mcp__sculptor__exit_plan_mode`` accepts any object input per its
        # advertised schema, so no per-field validation is needed here.

        # Agent is still in plan mode until the user actually approves: revision
        # and dismissal both keep it in plan mode. The approval path in
        # ClaudeProcessManager._try_deliver_answer_to_mcp emits the False
        # transition when it clears `_is_in_plan_mode`.

        plan_file_path = self._recent_plan_file_path
        self.output_message_queue.put(
            AskUserQuestionAgentMessage(
                message_id=AgentMessageID(),
                question_data=make_plan_approval_question(
                    tool_block.id,
                    plan_file_path=plan_file_path,
                ),
            )
        )
        if self._workspace_id is not None and plan_file_path is not None:
            publish_ui_action(
                OpenFileUiAction(
                    workspace_id=self._workspace_id,
                    file_path=plan_file_path,
                    mode="file",
                )
            )
        # One-shot: clear so a second ExitPlanMode without a fresh plan write
        # doesn't re-publish the stale path.
        self._recent_plan_file_path = None
        if self._mcp_server is not None:
            self._mcp_server.register_tool_use_id(tool_block.id, exit_plan_mode_tool_fqn, tool_input=tool_block.input)
        return True

    def _maybe_handle_enter_plan_mode(self, tool_block: ToolUseBlock) -> bool:
        """Detect EnterPlanMode tool calls and emit a plan mode state signal.

        Returns True if the tool block was an EnterPlanMode call, False otherwise.
        Idempotent: a second call with the same tool_block.id is a no-op.
        """
        if tool_block.name != "EnterPlanMode":
            return False
        if tool_block.id in self._intercepted_tool_ids:
            return True
        self._intercepted_tool_ids.add(tool_block.id)

        self.output_message_queue.put(PlanModeAgentMessage(message_id=AgentMessageID(), is_in_plan_mode=True))
        if self._on_plan_mode_changed is not None:
            self._on_plan_mode_changed(True)
        return True

    def _record_and_write_stdin(self, stdin_line: str) -> None:
        if self._transcript_collector is not None:
            self._transcript_collector.record_stdin(stdin_line)
        self.process.write_stdin(stdin_line)

    def _maybe_handle_control_request(self, line: str) -> bool:
        """Handle control_request messages from the CLI.

        Handles three subtypes:
        - ``"can_use_tool"``: Auto-approve permission requests (the agent runs
          in a sandbox so all tools are allowed).
        - ``"hook_callback"``: Detect the PreCompact hook to show the
          "Auto-compacting..." indicator.
        - Any other control_request: silently ignored (returns True so the
          line is not passed to the normal parser).

        Returns True if the line was a control_request (handled or ignored),
        False otherwise so the caller can continue with normal parsing.
        """
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return False

        if not isinstance(data, dict) or data.get("type") != "control_request":
            return False

        request = data.get("request", {})
        request_id = data.get("request_id", "")
        subtype = request.get("subtype", "")

        if subtype == "can_use_tool":
            self._approve_permission_request(request_id, request)
        elif subtype == "hook_callback":
            self._handle_hook_callback(request_id, request)
        elif subtype == "mcp_message":
            self._handle_mcp_message(request_id, request)
        # Other control_request subtypes (e.g. unknown future additions) are
        # silently consumed so the normal parser doesn't choke on them.

        return True

    def _handle_mcp_message(self, request_id: str, request: dict) -> None:
        """Route SDK-MCP `tools/call` invocations into Sculptor's MCP server.

        The Claude CLI delivers SDK MCP tool calls through this control_request
        envelope. For our `sculptor` server we hand off to the long-lived
        `SculptorMcpServer`; anything else is responded to with a JSON-RPC
        error so the CLI doesn't hang.
        """
        server_name = request.get("server_name")
        message = request.get("message") or {}
        if server_name == self._harness.mcp_server_name and self._mcp_server is not None:
            self._mcp_server.handle_message(request_id, message)
            return
        logger.info("Ignoring mcp_message for unknown/disabled server {!r}", server_name)
        self._respond_to_control_request(
            request_id,
            {
                "mcp_response": {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": -32600, "message": "Unknown MCP server"},
                }
            },
        )

    def _approve_permission_request(self, request_id: str, request: dict) -> None:
        """Auto-approve a ``can_use_tool`` permission request."""
        tool_name = request.get("tool_name", "")
        logger.info("Auto-approving permission request for tool '{}' (request_id={})", tool_name, request_id)
        self._respond_to_control_request(
            request_id,
            {
                "behavior": "allow",
                "updatedInput": request.get("input", {}),
            },
        )

    def _handle_hook_callback(self, request_id: str, request: dict) -> None:
        """Handle a ``hook_callback`` control request.

        If the callback ID matches the PreCompact hook registered via the
        ``initialize`` control request, emit ``AutoCompactingAgentMessage``
        to show the "Auto-compacting..." indicator.  For any other callback,
        respond with an empty success to unblock the CLI.
        """
        callback_id = request.get("callback_id", "")
        if callback_id == self._harness.pre_compact_callback_id:
            logger.info("Auto-compaction started (detected via PreCompact hook callback)")
            self._auto_compacting_emitted = True
            self.output_message_queue.put(AutoCompactingAgentMessage(message_id=AgentMessageID()))
        self._respond_to_control_request(request_id, {})

    def _respond_to_control_request(self, request_id: str, response_data: dict) -> None:
        """Send a success ``control_response`` on stdin."""
        response = {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
                "response": response_data,
            },
        }
        try:
            self._record_and_write_stdin(json.dumps(response) + "\n")
        except (OSError, AssertionError) as e:
            logger.info("Failed to send control response for request_id={}: {}", request_id, e)

    def _send_context_usage_request(self) -> None:
        """Send a get_context_usage control request on stdin.

        No-ops if a request is already pending (prevents stacking).
        """
        if self._pending_context_request_id is not None:
            return

        self._context_request_counter += 1
        request_id = f"ctx_{self._context_request_counter}"
        request = {
            "type": "control_request",
            "request_id": request_id,
            "request": {"subtype": "get_context_usage"},
        }
        try:
            self._record_and_write_stdin(json.dumps(request) + "\n")
        except (OSError, AssertionError) as e:
            logger.debug("Failed to send get_context_usage request: {}", e)
            return

        self._pending_context_request_id = request_id
        logger.debug("Sent get_context_usage request (id={})", request_id)

    def _is_context_usage_response(self, line: str) -> dict[str, Any] | None:
        """Check if a stdout line is a control_response matching our pending request.

        Returns the inner response payload dict if it matches, or None otherwise.
        """
        if self._pending_context_request_id is None:
            return None

        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(data, dict) or data.get("type") != "control_response":
            return None

        response = data.get("response", {})
        if response.get("request_id") != self._pending_context_request_id:
            return None

        self._pending_context_request_id = None
        return response.get("response", {})

    def _handle_context_usage_response(self, response: dict[str, Any]) -> None:
        """Process a get_context_usage response and flush per-turn context metrics."""
        total_tokens = response.get("totalTokens", 0)
        max_tokens = response.get("maxTokens", 0)
        percentage = response.get("percentage", 0.0)
        auto_compact_threshold = response.get("autoCompactThreshold")

        logger.debug("Context usage response: {}% ({}/{} tokens)", percentage, total_tokens, max_tokens)

        # Flush any pending TurnMetrics with this turn's context snapshot
        # attached. See _parse_stream_end_response for why we defer emission.
        self._flush_pending_turn_metrics(
            context_total_tokens=total_tokens,
            auto_compact_threshold=auto_compact_threshold,
        )

    def _flush_pending_turn_metrics(
        self,
        context_total_tokens: int | None = None,
        auto_compact_threshold: int | None = None,
    ) -> None:
        """Emit the stashed TurnMetrics, optionally augmented with context data.

        Called either from _handle_context_usage_response (happy path, context
        data attached) or after the post-loop drain times out (no context).
        """
        pending = self._pending_turn_metrics
        if pending is None:
            return
        self._pending_turn_metrics = None
        enriched = pending.model_copy(
            update={
                "context_total_tokens": context_total_tokens,
                "auto_compact_threshold": auto_compact_threshold,
            }
        )
        self.output_message_queue.put(TurnMetricsAgentMessage(turn_metrics=enriched))

    def _handle_stream_event(self, event: ParsedStreamEvent) -> None:
        """Handle streaming event:
        - Process one streaming event at a time.
        - Merge the event with internal state
        - Emit AgentMessages in output queue
            - Send partial text updates as they arrive
            - Send tool input only when complete
        """
        if not self.streaming_enabled:
            return

        if isinstance(event, MessageStartEvent):
            self._is_streaming_turn = True
            self.current_turn_id = AssistantMessageID(event.message_id)
            self._streamed_turn_ids.add(event.message_id)
            new_parent = event.parent_tool_use_id
            # Generate the persistent ChatMessage ID at each ChatMessage boundary.
            # A new ChatMessage starts when:
            #   (a) the first MessageStart of a new request cycle fires — i.e. after
            #       _parse_init_response reset _first_response_message_id to None,
            #       which covers post-task_notification cycles, AND
            #   (b) the parent_tool_use_id changes between turns (subagent context
            #       switch) — message_conversion flushes the in-progress message
            #       on this transition, and the new in-progress must get its own
            #       ID so the flushed one isn't overwritten by frontend dedup.
            # Without (b), msg_1 (text + Agent tool_use), msg_2 (subagent reply),
            # and msg_3 (main agent again) all share one ID and collapse into a
            # single visible ChatMessage on the frontend — losing the Agent
            # tool_use and the subagent's reply.
            # We compare against _last_response_parent_tool_use_id (which
            # persists across MessageStop) rather than _current_parent_tool_use_id
            # (which _reset_streaming_state clears to None on every MessageStop).
            if self._first_response_message_id is None or self._last_response_parent_tool_use_id != new_parent:
                self._first_response_message_id = AgentMessageID()
                self._used_first_response_id = False
            self._current_parent_tool_use_id = new_parent
            self._last_response_parent_tool_use_id = new_parent

        elif isinstance(event, TextBlockStartEvent):
            self._text_accumulators[event.index] = ""

        elif isinstance(event, ToolBlockStartEvent):
            self._tool_accumulators[event.index] = {
                "id": event.tool_id,
                "name": event.tool_name,
                "input_json": "",
            }

        elif isinstance(event, TextDeltaEvent):
            if event.index in self._text_accumulators:
                self._text_accumulators[event.index] += event.text
                self._emit_partial_message()

        elif isinstance(event, ToolInputDeltaEvent):
            if event.index in self._tool_accumulators:
                # Buffer tool input, don't emit until complete
                self._tool_accumulators[event.index]["input_json"] += event.partial_json

        elif isinstance(event, ContentBlockStopEvent):
            self._finalize_block_from_accumulator(event.index)

        elif isinstance(event, MessageStopEvent):
            # Turn complete - emit marker to signal end of streaming mode.
            self.output_message_queue.put(StreamingMessageCompleteAgentMessage(message_id=AgentMessageID()))
            # Flush buffered persistence message AFTER StreamingMessageComplete so
            # message_conversion sees it with is_streaming_active=False and can
            # deduplicate ToolUseBlocks that were already delivered via streaming.
            buffered = self._buffered_persistence_message
            if buffered is not None:
                # Rebuild content from streaming state — the SDK's raw message
                # may be incomplete (missing text/FileBlocks).
                streamed_content = self._build_streamed_persistence_content()
                if streamed_content:
                    buffered = ResponseBlockAgentMessage(
                        role=buffered.role,
                        message_id=buffered.message_id,
                        assistant_message_id=buffered.assistant_message_id,
                        content=streamed_content,
                        parent_tool_use_id=buffered.parent_tool_use_id,
                    )
                    self.last_assistant_message = buffered
                logger.trace("Flushing buffered persistence message after streaming complete")
                self.output_message_queue.put(buffered)
                self._buffered_persistence_message = None
            self._reset_streaming_state()

    def _finalize_block_from_accumulator(self, index: int) -> None:
        """Finalize a block and optionally emit partial."""
        if index in self._text_accumulators:
            text = self._text_accumulators.pop(index)
            segments = split_text_and_media(text)
            has_files = any(isinstance(s, FileBlock) for s in segments)

            # Place the first TextBlock at the streaming index. Media-only text
            # (no TextBlock in segments) produces no entry — the index stays
            # sparse. The extracted FileBlocks are tracked separately below.
            first_text = next((s for s in segments if isinstance(s, TextBlock)), None)
            if first_text is not None:
                self._add_to_completed_streaming_blocks(index, first_text)

            # Remaining segments (interleaved text/file after the first TextBlock)
            # are tracked keyed by this text block's streaming index, so
            # _materialize_content can splice them back in right after the source
            # text — keeping the model's text -> image -> ... order even when a tool
            # block precedes this text in the same message.
            remaining_segments: list[TextBlock | FileBlock] = []
            found_first_text = False
            for segment in segments:
                if not found_first_text and isinstance(segment, TextBlock):
                    found_first_text = True
                    continue
                remaining_segments.append(segment)
            if remaining_segments:
                self._extracted_file_blocks.setdefault(index, []).extend(remaining_segments)

            if has_files:
                self._emit_partial_message()
        elif index in self._tool_accumulators:
            tool_data = self._tool_accumulators.pop(index)
            try:
                tool_input = json.loads(tool_data["input_json"]) if tool_data["input_json"] else {}
            except json.JSONDecodeError:
                logger.error("Failed to parse tool input")
                tool_input = {}
            tool_block = ToolUseBlock(id=tool_data["id"], name=tool_data["name"], input=tool_input)
            self._add_to_completed_streaming_blocks(index, tool_block)
            self._maybe_record_plan_file_write(tool_block)
            self._maybe_handle_ask_user_question(tool_block)
            self._maybe_handle_exit_plan_mode(tool_block)
            self._maybe_handle_enter_plan_mode(tool_block)
            # Track tool for later tool result processing
            self.tool_use_map[tool_data["id"]] = (tool_data["name"], tool_input)
            self._tool_start_times[tool_data["id"]] = time.monotonic()
            self._emit_partial_message()

    def _add_to_completed_streaming_blocks(self, index: int, block: ContentBlockTypes) -> None:
        """Place a finalized block at its streaming index."""
        self._completed_streaming_blocks[index] = block

    def _emit_partial_message(self) -> None:
        """Emit current turn's partial state."""
        content = self._materialize_content(include_in_progress=True)
        assert self.current_turn_id is not None
        assert self._first_response_message_id is not None
        self.output_message_queue.put(
            PartialResponseBlockAgentMessage(
                message_id=AgentMessageID(),
                content=tuple(content),
                assistant_message_id=self.current_turn_id,
                first_response_message_id=self._first_response_message_id,
                parent_tool_use_id=self._current_parent_tool_use_id,
            )
        )

    def _materialize_content(self, *, include_in_progress: bool) -> list[ContentBlockTypes]:
        """Render streaming state into an ordered, compacted content list.

        This is the single translation point from index-addressed streaming
        state to the list-ordered content that downstream consumers (partials,
        persistence, frontend) operate on. Called with ``include_in_progress=
        True`` for partials (includes active text accumulators) and ``False``
        for the post-stream persistence message (finalized state only).

        Empty and whitespace-only TextBlocks are filtered here — they are
        produced by the SDK's index-addressed protocol (zero-delta text,
        media-only text) and are not user-visible content. Filtering both
        partials and persistence through a single rule is what keeps the two
        message types shape-equivalent; prior divergence caused consecutive
        tool calls to render as multiple groups instead of one.

        Media tags are stripped from in-progress text so partial raw HTML is
        never visible. Incomplete trailing tags (e.g. ``<img src='/tmp/sc``)
        are also hidden until the closing ``>`` arrives.

        Interleaved FileBlocks/TextBlocks extracted from media tags (tracked in
        ``_extracted_file_blocks``, keyed by the source text block's streaming
        index) are spliced in immediately after that source text block, so an
        ``<img>``/``<video>`` stays next to the text the model emitted it in —
        regardless of where tool blocks sit in the message. (Splicing them before
        the first ToolUseBlock instead mis-ordered media whose source text came
        after a tool call.)
        """
        blocks: list[ContentBlockTypes] = []

        finalized_indices = set(self._completed_streaming_blocks)
        accumulator_indices = set(self._text_accumulators) if include_in_progress else set()
        extracted_indices = set(self._extracted_file_blocks)
        # finalized_indices and accumulator_indices are disjoint by construction:
        # _finalize_block_from_accumulator pops from _text_accumulators and writes
        # to _completed_streaming_blocks in a single step. extracted_indices is
        # unioned in too because media-only text (no leading TextBlock) finalizes
        # to an extracted entry with no _completed_streaming_blocks slot.
        for idx in sorted(finalized_indices | accumulator_indices | extracted_indices):
            if idx in self._completed_streaming_blocks:
                block = self._completed_streaming_blocks[idx]
                if not (isinstance(block, TextBlock) and not block.text.strip()):
                    blocks.append(block)
            elif idx in accumulator_indices:
                text = self._text_accumulators[idx]
                cleaned_text, _file_paths = extract_media_tags_from_text(text)
                trailing = _RE_TRAILING_MEDIA_TAG.search(cleaned_text)
                if trailing:
                    cleaned_text = cleaned_text[: trailing.start()]
                if cleaned_text.strip():
                    blocks.append(TextBlock(text=cleaned_text))
            # Splice media extracted from this text block immediately after it, so an
            # <img>/<video> stays adjacent to its source text — even when a tool block
            # precedes the text in the same assistant message.
            extracted = self._extracted_file_blocks.get(idx)
            if extracted:
                blocks.extend(extracted)

        return blocks

    def _build_streamed_persistence_content(self) -> tuple[ContentBlockTypes, ...]:
        """Persistence-shape content: finalized blocks only.

        The SDK's raw "assistant" JSON message may omit text blocks that were
        delivered only through streaming events. Rather than patching gaps in
        the SDK output, this rebuilds the authoritative content from what was
        actually streamed.
        """
        return tuple(self._materialize_content(include_in_progress=False))

    def _reset_streaming_state(self) -> None:
        """Reset streaming state for next turn."""
        self._is_streaming_turn = False
        self._completed_streaming_blocks = {}
        self._text_accumulators = {}
        self._tool_accumulators = {}
        self._extracted_file_blocks = {}
        self._current_parent_tool_use_id = None
