import json
import os
import signal
import time
import uuid
from contextlib import AbstractContextManager
from pathlib import Path
from queue import Queue
from subprocess import TimeoutExpired
from threading import Event
from typing import Callable
from typing import Mapping

from loguru import logger

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import RunningProcess
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.state.messages import Message
from imbue_core.secrets_utils import Secret
from imbue_core.thread_utils import ObservableThread
from sculptor.agents.default.claude_code_sdk.diff_tracker import DiffTracker
from sculptor.agents.default.claude_code_sdk.harness import ClaudeCodeHarness
from sculptor.agents.default.claude_code_sdk.mcp_server import SculptorMcpServer
from sculptor.agents.default.claude_code_sdk.output_processor import ClaudeOutputProcessor
from sculptor.agents.default.claude_code_sdk.output_processor import is_first_user_message_of_conversation
from sculptor.agents.default.claude_code_sdk.process_manager_utils import get_claude_command
from sculptor.agents.default.claude_code_sdk.process_manager_utils import get_user_instructions
from sculptor.agents.default.claude_code_sdk.process_manager_utils import is_plan_approval
from sculptor.agents.default.claude_code_sdk.process_manager_utils import is_session_id_valid
from sculptor.agents.default.claude_code_sdk.transcript_collector import TranscriptCollector
from sculptor.agents.default.constants import ENTITY_MENTIONS_SYSTEM_PROMPT
from sculptor.agents.default.constants import MODEL_SHORTNAME_MAP
from sculptor.agents.default.errors import InterruptFailure
from sculptor.agents.default.utils import get_state_file_contents
from sculptor.agents.default.utils import get_turn_request_id
from sculptor.agents.default.utils import get_warning_message
from sculptor.common.plugin import get_plugin_dirs
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import ContextClearedMessage
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import PlanModeAgentMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.interfaces.agents.errors import ClaudeBinaryNotFoundError
from sculptor.interfaces.agents.errors import ErrorType
from sculptor.interfaces.agents.errors import IllegalOperationError
from sculptor.interfaces.agents.errors import UncleanTerminationAgentError
from sculptor.interfaces.agents.errors import WaitTimeoutAgentError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.workspace_service.environment_manager.env_file_parser import load_project_env_vars
from sculptor.services.workspace_service.setup_command_runner import SetupReminderState
from sculptor.services.workspace_service.setup_command_runner import SetupStateProvider
from sculptor.utils.build import get_internal_folder


class ClaudeProcessManager:
    def __init__(
        self,
        environment: AgentExecutionEnvironment,
        task_id: TaskID,
        in_testing: bool,
        secrets: Mapping[str, str | Secret],
        output_message_queue: Queue[Message],
        handle_user_message_callback: Callable[[UserMessageUnion], AbstractContextManager[None, bool | None]],
        system_prompt: str,
        harness: ClaudeCodeHarness,
        on_diff_needed: Callable[[], None] | None = None,
        workspace_id: WorkspaceID | None = None,
        setup_state_provider: SetupStateProvider | None = None,
    ):
        self.environment = environment
        self.task_id = task_id
        self.in_testing = in_testing
        self._secrets = secrets
        self._output_messages = output_message_queue
        # there are no untracked changes at this point, so we can use the fast path
        self._diff_tracker: DiffTracker = DiffTracker(self.environment)
        self._system_prompt: str = system_prompt
        self._on_diff_needed = on_diff_needed
        self._workspace_id = workspace_id
        self._setup_state_provider = setup_state_provider
        self._harness: ClaudeCodeHarness = harness
        self._fast_mode: bool = False
        self._effort: str | None = "xhigh"
        self._handle_user_message_callback = handle_user_message_callback
        self._message_processing_thread: ObservableThread | None = None
        self._process: RunningProcess | None = None
        # The request_id of the message currently being processed (its
        # message_id, matching the RequestStarted/RequestSuccess the wrapper
        # emits). interrupt_current_message's pathological Phase D uses it to
        # emit RequestSuccess(interrupted=True) directly when the worker thread
        # can no longer be relied on to do so. None between turns.
        self._in_flight_request_id: AgentMessageID | None = None
        # Count of worker threads that survived a full stdin→SIGTERM→SIGKILL
        # interrupt escalation and had to be leaked (SCU-1340 Phase D). An
        # observable signal that the pathological path was hit; should stay 0.
        self._leaked_interrupt_worker_thread_count: int = 0
        self._is_interrupted: Event = Event()
        self._session_id_written_event: Event = Event()
        self._is_fake_claude: bool = False
        self._is_in_plan_mode: bool = False
        project_env = load_project_env_vars(environment.get_root_path())
        verbose_log = bool(
            project_env.get("SCULPTOR_VERBOSE_AGENT_LOG") or os.environ.get("SCULPTOR_VERBOSE_AGENT_LOG")
        )
        transcript_path = environment.get_artifacts_path() / "transcript.jsonl"
        environment.get_artifacts_path().mkdir(parents=True, exist_ok=True)
        self._transcript_file = open(str(transcript_path), "a")  # noqa: SIM115
        self._transcript_collector = TranscriptCollector(verbose=verbose_log, file=self._transcript_file)
        # The MCP server outlives any single CLI invocation. Each new
        # ``ClaudeOutputProcessor.__init__`` rebinds its ``respond`` callback to
        # the freshly-spawned CLI's stdin via ``set_respond``; the placeholder
        # below keeps things safe before the first invocation.
        self._mcp_server: SculptorMcpServer = SculptorMcpServer(
            respond=self._noop_mcp_respond,
            harness=self._harness,
        )
        # ``UserQuestionAnswerMessage`` IDs whose ``RequestStarted`` has been
        # emitted by ``_try_deliver_answer_to_mcp`` but whose
        # ``RequestSuccess`` is being deferred until the current CLI invocation
        # finishes (so the agent's post-answer ``tool_result`` + follow-up
        # content lands in the right in-progress chat message). Drained by
        # ``_process_single_message`` after ``_read_output_from_process``
        # returns.
        self._pending_answer_request_ids: list[AgentMessageID] = []

    @staticmethod
    def _noop_mcp_respond(control_request_id: str, response_data: dict) -> None:
        """Placeholder MCP `respond` callback used between CLI invocations.

        ``deliver_answer`` should never be called when no CLI is running, but
        if it ever is we log instead of crashing — Phase 3's proactive-resume
        path will replace this with a real send path.
        """
        logger.info("Dropped MCP response for request_id={} — no live CLI process bound", control_request_id)

    def _fetch_setup_state(self, is_first_message: bool) -> SetupReminderState | None:
        setup_state_provider = self._setup_state_provider
        if not is_first_message or setup_state_provider is None:
            return None
        fetch_started = time.monotonic()
        result = setup_state_provider.get_reminder_state()
        logger.debug("setup reminder fetch took {:.3f}s for first message", time.monotonic() - fetch_started)
        return result

    def _record_and_write_stdin(self, process: RunningProcess, stdin_line: str) -> None:
        self._transcript_collector.record_stdin(stdin_line)
        process.write_stdin(stdin_line)

    def _resolve_claude_binary_path(self) -> str:
        binary_path = self.environment.get_tool_binary_path(self._harness.binary_dependency)
        if binary_path is None:
            raise ClaudeBinaryNotFoundError()
        return binary_path

    def process_input_message(
        self, message: ChatInputUserMessage | ResumeAgentResponseRunnerMessage | UserQuestionAnswerMessage
    ) -> None:
        # Mid-turn happy path: if the message is an answer to a tool the
        # currently-running Claude is blocked on, deliver it through the MCP
        # server and skip the respawn.
        if isinstance(message, UserQuestionAnswerMessage) and self._try_deliver_answer_to_mcp(message):
            return
        message_processing_thread = self._message_processing_thread
        if message_processing_thread is not None:
            message_processing_thread.join(timeout=0.01)
            if message_processing_thread.is_alive():
                # SCU-1426: the worker thread is still parked on a question, yet an
                # answer reached here that matched no pending MCP call (so
                # _try_deliver_answer_to_mcp bailed). After a restart the CLI
                # re-issues the dangling question under a fresh tool_use_id, so a
                # re-delivered, already-consumed answer no longer matches — it is
                # stale. Discarding it (rather than raising) keeps us from wedging
                # the task (RUNNING, Stop a no-op; the SCU-1404 / SCU-1405 family)
                # while the worker stays parked. Emit a terminal RequestSkipped so
                # the runner's in-flight bookkeeping and the frontend chat message
                # both resolve. Note we only discard in *this* parked-thread case:
                # when the worker thread is not alive, an unmatched answer falls
                # through to the respawn path below, which is the legitimate
                # "answer after the turn ended" continuation. A non-answer message
                # here is a genuine illegal overlap and still raises.
                if isinstance(message, UserQuestionAnswerMessage):
                    logger.info(
                        "Discarding stale question answer {} — worker thread still parked and no pending MCP call matches tool_use_id={}",
                        message.message_id,
                        message.tool_use_id,
                    )
                    self._output_messages.put(RequestSkippedAgentMessage(request_id=message.message_id))
                    return
                raise IllegalOperationError("Cannot process new message while last message is still being processed")
        self._process = None
        # A resumed turn continues an earlier user turn, so track that turn's id
        # (for_user_message_id) -- the interrupt paths key their terminal
        # RequestSuccess on _in_flight_request_id, and it must match the original
        # chat message. See get_turn_request_id.
        self._in_flight_request_id = get_turn_request_id(message)
        self._session_id_written_event.clear()
        # Reset the interrupt flag so a stale set() from a previous turn (or a
        # set() that fired before this thread existed) doesn't short-circuit
        # this brand-new turn.
        self._is_interrupted.clear()
        self._message_processing_thread = self.environment.concurrency_group.start_new_thread(
            target=self._process_single_message,
            args=(message,),
        )

    def _try_deliver_answer_to_mcp(self, message: UserQuestionAnswerMessage) -> bool:
        """Resolve a held MCP `tools/call` mid-turn.

        Returns True if the answer was delivered through the MCP server (no
        respawn needed); False if no matching pending call exists. On False,
        ``process_input_message`` either respawns a fresh turn from the answer
        (the normal "answer after the turn ended" continuation) or, when the
        worker thread is still parked on a re-issued question, discards the
        stale answer instead of wedging (SCU-1426).
        """
        process = self._process
        if process is None or process.is_finished():
            return False
        if not self._mcp_server.has_pending_call(message.tool_use_id):
            return False
        if self._is_in_plan_mode and is_plan_approval(message):
            self._is_in_plan_mode = False
            self._output_messages.put(PlanModeAgentMessage(message_id=AgentMessageID(), is_in_plan_mode=False))
        self._mcp_server.deliver_answer(message)
        # The answer's `RequestSuccess` is deferred to ``_process_single_message``
        # so it fires AFTER the CLI's tool_result + follow-up text reaches the
        # frontend. Emitting it eagerly here would finalize the in-progress
        # chat message prematurely and leave the agent's post-answer content
        # orphaned in a never-completed second in-progress message.
        self._output_messages.put(
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=message.message_id)
        )
        self._pending_answer_request_ids.append(message.message_id)
        return True

    def process_clear_context_message(self, message: ClearContextUserMessage) -> None:
        message_processing_thread = self._message_processing_thread
        if message_processing_thread is not None:
            message_processing_thread.join(timeout=0.01)
            if message_processing_thread.is_alive():
                raise IllegalOperationError("Cannot process new message while last message is still being processed")
        self._process = None
        self._in_flight_request_id = message.message_id
        self._session_id_written_event.clear()
        self._is_interrupted.clear()
        self._message_processing_thread = self.environment.concurrency_group.start_new_thread(
            target=self._process_clear_context_message,
            args=(message,),
        )

    def interrupt_current_message(self, message: InterruptProcessUserMessage) -> None:
        with self._handle_user_message_callback(message):
            # Mark the turn as cancelled FIRST, before any gates. Even if the
            # message-processing thread hasn't yet spawned the CLI (or hasn't
            # been scheduled at all), it will see this flag at the checkpoints
            # in _process_single_message and exit cleanly. Without this,
            # interrupts that arrived before the CLI process existed were
            # silently dropped (PROD-1549).
            self._is_interrupted.set()
            message_processing_thread = self._message_processing_thread
            if message_processing_thread is None or not message_processing_thread.is_alive():
                # The worker thread is gone, so it can no longer emit this turn's
                # terminal RequestSuccess itself. If a turn is still in flight,
                # reconcile it directly so the frontend's in-progress chat message
                # resolves instead of staying stuck "thinking" (SCU-1405) — the
                # no-signal sibling of _escalate_interrupt's SIGKILL-survivor tail.
                logger.info("Message processing thread is not alive; flag set, no signal escalation needed")
                self._resolve_in_flight_request_as_interrupted()
                return
            try:
                # TODO: we want to wait for a valid session id but it'll block the event loop right now and requires a larger refactor
                self._wait_until_interrupt_is_safe(should_wait_for_valid_session=False)
            except InterruptFailure as e:
                # This is expected when the user clicks Stop before the session ID is
                # fully written. The interrupt still proceeds (the process is terminated
                # below) and the user message is rolled back, which is the correct
                # behavior. No need to surface this as a user-visible warning.
                logger.info("Interrupt occurred before session was fully initialized: {}", e)
            else:
                logger.debug("Done waiting for a valid session id and process - the agent is now safe to interrupt")
            # Phase A — stdin interrupt (the graceful path). Ask the CLI to
            # interrupt itself, then wait for the worker thread to finish.
            # Joining matters: it guarantees the chat-message's wrapper-level
            # else branch runs BEFORE the interrupt-message's else branch, which
            # is what causes the original chat message to receive
            # RequestSuccess(interrupted=True) — i.e. the user-visible
            # "Interrupted by user" indicator.
            if self._process is not None:
                self._send_interrupt_control_request()
            message_processing_thread.join(timeout=5.0)
            if not message_processing_thread.is_alive():
                return
            self._escalate_interrupt(message_processing_thread)

    def _escalate_interrupt(self, message_processing_thread: ObservableThread) -> None:
        """Force-stop a worker thread that ignored the stdin interrupt.

        SCU-1340: signals are sent to the process *group* directly from this
        (the interrupt) thread via ``RunningProcess.kill_now`` — NOT through the
        worker thread's own ``terminate``/``_shutdown_popen`` path, which can be
        wedged precisely when we need it most. The total budget is ~9 s and is
        visible here in code rather than hidden behind the subprocess wrapper's
        30 s shutdown timeout. Every step logs before it acts so an operator
        reading logs after the fact can see which phase succeeded.

        Stop is a user action and must never crash the agent runner, so this
        never raises: the pathological tail (Phase D) leaks the thread, records
        it, and emits a terminal RequestSuccess so the frontend recovers.
        """
        process = self._process
        if process is None:
            # The CLI never spawned; the interrupt flag set above is enough for
            # the worker to bail at its next checkpoint. Nothing to signal.
            logger.info("Worker thread still alive after stdin interrupt, but no process to signal")
            return

        # Phase B — SIGTERM the process group (visible, no thread coordination).
        # info-level: escalating past a missed stdin interrupt is routine for a
        # busy CLI; the loud signal is reserved for the pathological tail below.
        logger.info("stdin interrupt did not stop the agent within 5s; sending SIGTERM to the process group")
        process.kill_now(signal.SIGTERM)
        message_processing_thread.join(timeout=2.0)
        if not message_processing_thread.is_alive():
            return

        # Phase C — SIGKILL the process group. A process that ignored SIGTERM is
        # genuinely unusual, so this one is warning-level.
        logger.warning("SIGTERM did not stop the agent within 2s; sending SIGKILL to the process group")
        process.kill_now(signal.SIGKILL)
        message_processing_thread.join(timeout=2.0)
        if not message_processing_thread.is_alive():
            return

        # Phase D — pathological: the worker survived SIGKILL on its own process
        # group (e.g. stuck in an uninterruptible kernel wait, or zombied). We
        # cannot reap it here. Be honest: record the leak loudly, and emit
        # RequestSuccess(interrupted=True) DIRECTLY so the frontend's in-progress
        # chat message resolves instead of staying stuck "thinking" — rather than
        # depending on the wedged worker's wrapper to emit it.
        self._leaked_interrupt_worker_thread_count += 1
        log_exception(
            RuntimeError("Message processing thread survived SIGKILL on its process group"),
            "Stop did not reach a terminal state; leaking worker thread (leaked so far: {leaked})",
            leaked=self._leaked_interrupt_worker_thread_count,
            priority=ExceptionPriority.MEDIUM_PRIORITY,
        )
        self._resolve_in_flight_request_as_interrupted()

    def _resolve_in_flight_request_as_interrupted(self) -> None:
        """Emit a terminal RequestSuccess(interrupted=True) for the in-flight
        request, if any, so the frontend's in-progress chat message resolves
        instead of staying stuck "thinking".

        Used on the two interrupt paths where the worker thread can no longer be
        relied on to emit the turn's own terminal message: ``interrupt_current_message``'s
        no-op branch (the worker is already gone) and ``_escalate_interrupt``'s
        Phase D (the worker survived SIGKILL). No-ops when no turn is in flight.
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

    def get_exception_if_exists(self) -> BaseException | None:
        if self._message_processing_thread is not None and self._message_processing_thread.exception_raw is not None:
            return self._message_processing_thread.exception_raw
        return None

    def _send_interrupt_control_request(self) -> None:
        """Send an interrupt control request to Claude via the stdin control protocol.

        Falls back to SIGTERM on the process group if the stdin write fails
        (e.g. pipe already closed).
        """
        process = self._process
        if process is None:
            return
        try:
            request_id = f"req_interrupt_{uuid.uuid4().hex[:8]}"
            control_request = {
                "type": "control_request",
                "request_id": request_id,
                "request": {"subtype": "interrupt"},
            }
            self._record_and_write_stdin(process, json.dumps(control_request) + "\n")
            logger.info("Sent interrupt control request: {}", request_id)
        except (OSError, AssertionError) as e:
            # stdin pipe may already be closed or process wasn't started with stdin=PIPE.
            # SIGTERM the process group directly (not via terminate's worker-thread
            # shutdown path) so foreground subprocesses die too (SCU-1340).
            logger.warning("Failed to send interrupt control request ({}), falling back to SIGTERM", e)
            process.kill_now(signal.SIGTERM)

    @staticmethod
    def _build_stdin_user_message(content: str) -> str:
        """Build a JSON user message for the stdin control protocol."""
        # session_id is required by the CLI's stdin JSON schema but an empty
        # string makes it reuse the current session (we pass --resume separately).
        message = {
            "type": "user",
            "session_id": "",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
        }
        return json.dumps(message) + "\n"

    def _build_initialize_control_request(self) -> str:
        """Build an initialize control request that registers a PreCompact hook.

        Sent on stdin before the user message so the CLI can send hook_callback
        control requests on stdout when auto-compaction triggers.
        """
        pre_compact_callback_id = self._harness.pre_compact_callback_id
        control_request = {
            "type": "control_request",
            "request_id": f"req_init_{uuid.uuid4().hex[:8]}",
            "request": {
                "subtype": "initialize",
                "hooks": {
                    # Register the callback for both auto- and manual-triggered
                    # compaction so we can surface the "Compacting..." indicator
                    # in either case.
                    "PreCompact": [
                        {
                            "matcher": "auto",
                            "hookCallbackIds": [pre_compact_callback_id],
                        },
                        {
                            "matcher": "manual",
                            "hookCallbackIds": [pre_compact_callback_id],
                        },
                    ],
                },
            },
        }
        return json.dumps(control_request) + "\n"

    def stop(self, timeout: float, is_waiting: bool = False) -> None:
        try:
            thread_wait_time = max(timeout - 5.0, timeout / 2.0)
            process_wait_time = timeout - thread_wait_time
            process = self._process
            if process is not None:
                # Try closing stdin first to let the process exit cleanly from EOF
                process.close_stdin()
                if is_waiting:
                    try:
                        process.wait(process_wait_time)
                    except TimeoutExpired:
                        # The process didn't exit in time. Terminate it instead of crashing —
                        # the agent's work is already done if we got here via _handle_completed_agent.
                        logger.info("Process did not exit within {}s, terminating", process_wait_time)
                        process.terminate(force_kill_seconds=2.0)
                else:
                    process.terminate(force_kill_seconds=process_wait_time)
            message_processing_thread = self._message_processing_thread
            if message_processing_thread is not None:
                # NOTE: if there is an exception in the message processing thread, calling .join() will raise it
                message_processing_thread.join(timeout=thread_wait_time)
                # FIXME: we need more consistent handling -- all .join() calls must be followed by checking that the thread is no longer alive
                if message_processing_thread.is_alive():
                    if is_waiting:
                        raise WaitTimeoutAgentError(
                            f"Failed to join message processing thread within {timeout} seconds"
                        )
                    else:
                        raise UncleanTerminationAgentError(
                            f"Failed to terminate message processing thread within {thread_wait_time} seconds"
                        )
        finally:
            # The transcript file is opened once per ClaudeProcessManager in
            # __init__, and a fresh manager is constructed every time an agent
            # task starts or resumes in the long-lived backend. Closing it on
            # every stop path (including the raise paths above) prevents leaking
            # one fd per agent run until garbage collection. close() is
            # idempotent, so a second stop() does not raise.
            self._transcript_collector.close()

    def _get_combined_system_prompt(self) -> str:
        full_system_prompt = self._harness.hidden_system_prompt + self._harness.system_prompt_addendum

        # Conditionally add entity mentions instructions when the feature is enabled
        user_config = get_user_config_instance()
        if user_config.enable_entity_mentions:
            full_system_prompt = f"{full_system_prompt}\n{ENTITY_MENTIONS_SYSTEM_PROMPT}"

        # Add environment-specific content (e.g., mode instructions)
        env_system_prompt = self.environment.get_system_prompt()
        if env_system_prompt:
            full_system_prompt = f"{full_system_prompt}\n{env_system_prompt}"

        if self._system_prompt:
            full_system_prompt = (
                f"{full_system_prompt}\n <User instructions>\n{self._system_prompt}\n </User instructions>"
            )
        return full_system_prompt

    def _wait_until_interrupt_is_safe(self, should_wait_for_valid_session: bool) -> None:
        start_time = time.time()
        process_start_timeout = 5.0
        while self._process is None and time.time() - start_time < process_start_timeout:
            time.sleep(0.01)
        if self._process is None:
            raise InterruptFailure(
                f"Claude code process has not started in {process_start_timeout} seconds, cannot interrupt"
            )
        session_id_state_file = self._harness.session_id_state_file_name
        if should_wait_for_valid_session:
            session_id_written_timeout = 30.0
            if not self._session_id_written_event.wait(timeout=session_id_written_timeout):
                raise InterruptFailure(
                    f"Session ID not written in {session_id_written_timeout} seconds - the interrupted user message may be rolled back"
                )
            session_id = get_state_file_contents(self.environment, session_id_state_file)
            assert session_id is not None
            start_time = time.time()
            session_id_valid_timeout = 10.0
            while not is_session_id_valid(session_id, self.environment, self._harness, is_session_running=True):
                time.sleep(0.1)
                if time.time() - start_time > session_id_valid_timeout:
                    raise InterruptFailure(
                        f"Session ID not valid in {session_id_valid_timeout} seconds - the interrupted user message may be rolled back"
                    )
        else:
            if not self._session_id_written_event.is_set():
                raise InterruptFailure(
                    "The interrupt occurred before the session id was written - the interrupted user message will be rolled back"
                )
            else:
                session_id = get_state_file_contents(self.environment, session_id_state_file)
                assert session_id is not None
                if not is_session_id_valid(session_id, self.environment, self._harness, is_session_running=True):
                    raise InterruptFailure(
                        "The interrupt occurred before the session id was written properly - the interrupted user message will be rolled back"
                    )

    def _maybe_save_files_to_environment(self, message: UserMessageUnion) -> tuple[str, ...]:
        if not isinstance(message, ChatInputUserMessage):
            return tuple()

        file_paths = []
        for local_file_path in message.files:
            filename = local_file_path.split("/")[-1]
            if os.path.isabs(local_file_path):
                source = Path(local_file_path)
            else:
                source = get_internal_folder() / "uploads" / local_file_path

            try:
                file_content = source.read_bytes()
            except FileNotFoundError:
                logger.warning("Skipping missing file attachment: {}", source)
                continue

            file_path = self.environment.get_attachments_path() / filename
            self.environment.write_file(path=str(file_path), content=file_content, mode="wb")
            file_paths.append(str(file_path))

        return tuple(file_paths)

    def _process_single_message(self, message: UserMessageUnion) -> None:
        with self._handle_user_message_callback(message):
            # An interrupt may have arrived before this thread was scheduled
            # (the request-handling dispatcher and this worker run on different
            # threads). Bail out without doing any work; the wrapper's else
            # branch will still emit RequestSuccess(interrupted=True) for the
            # original chat message, since `_was_interrupted` was set in
            # _push_message before interrupt_current_message was called.
            if self._is_interrupted.is_set():
                logger.info("Skipping message processing — interrupt arrived before turn started")
                return
            # if the message includes files, we need to save them to the environment first
            file_paths = self._maybe_save_files_to_environment(message)

            # Track plan mode state from ChatInputUserMessage flags
            if isinstance(message, ChatInputUserMessage):
                if message.enter_plan_mode:
                    self._is_in_plan_mode = True
                elif message.exit_plan_mode:
                    self._is_in_plan_mode = False
            elif isinstance(message, UserQuestionAnswerMessage):
                if self._is_in_plan_mode and is_plan_approval(message):
                    self._is_in_plan_mode = False
                    self._output_messages.put(PlanModeAgentMessage(message_id=AgentMessageID(), is_in_plan_mode=False))

            is_first_message = is_first_user_message_of_conversation(self.environment, self._harness)
            env_var_names = self.environment.get_project_env_var_names()
            setup_state = self._fetch_setup_state(is_first_message)
            user_instructions = get_user_instructions(
                message=message,  # pyre-fixme[6]
                file_paths=file_paths,
                is_in_plan_mode=self._is_in_plan_mode,
                env_var_names=env_var_names,
                is_first_message=is_first_message,
                setup_state=setup_state,
            )
            filename = f"{self.environment.get_state_path()}/user_instructions_{message.message_id}.txt"
            self.environment.write_file(filename, user_instructions)
            session_id_state_file = self._harness.session_id_state_file_name
            validated_session_id_state_file = self._harness.validated_session_id_state_file_name
            maybe_session_id = get_state_file_contents(self.environment, session_id_state_file)
            if maybe_session_id is not None:
                if is_session_id_valid(maybe_session_id, self.environment, self._harness, is_session_running=False):
                    # if the session id is valid, we can resume from it and we should save it to the state file
                    self.environment.write_file(
                        str(self.environment.get_state_path() / validated_session_id_state_file), maybe_session_id
                    )
                else:
                    self._output_messages.put(
                        get_warning_message(
                            "Rolling back to the last valid session id - this means your last user message may not be in the agent context",
                            None,
                            self.task_id,
                        )
                    )
                    # otherwise, use the previous validated session id if it exists
                    maybe_session_id = get_state_file_contents(self.environment, validated_session_id_state_file)
            combined_system_prompt = self._get_combined_system_prompt()
            if isinstance(message, (ChatInputUserMessage, ResumeAgentResponseRunnerMessage)):
                self._is_fake_claude = message.model_name in (LLMModel.FAKE_CLAUDE, LLMModel.FAKE_CLAUDE_2)
            maybe_model = (
                MODEL_SHORTNAME_MAP.get(message.model_name)
                if isinstance(message, (ChatInputUserMessage, ResumeAgentResponseRunnerMessage)) and message.model_name
                else None
            )
            if isinstance(message, (ChatInputUserMessage, ResumeAgentResponseRunnerMessage)):
                self._fast_mode = message.fast_mode
                self._effort = message.effort
            plugin_dirs = get_plugin_dirs()
            claude_command = get_claude_command(
                system_prompt=combined_system_prompt,
                session_id=maybe_session_id,
                model_name=maybe_model,
                enable_streaming=True,
                is_fake_claude=self._is_fake_claude,
                plugin_dirs=plugin_dirs,
                fast_mode=self._fast_mode,
                effort=self._effort,
                resolve_binary_path=self._resolve_claude_binary_path,
                harness=self._harness,
            )
            logger.info("Executing claude command in environment: {}", " ".join(claude_command))
            if self._is_fake_claude:
                logger.info("FakeClaude prompt (stdin): {}", user_instructions)

            # Forward CLAUDE_* env vars from the parent process so that
            # debugging/testing vars like CLAUDE_AUTOCOMPACT_PCT_OVERRIDE
            # reach the claude child process.  Secrets take the highest
            # priority in the env merge (see local_environment.py).
            claude_env_vars = {k: v for k, v in os.environ.items() if k.startswith("CLAUDE_")}
            child_env = {**self._secrets, **claude_env_vars}
            # Re-check before spawning the CLI. The setup work above can take
            # several seconds in slow environments (e.g. cold-starting offload
            # sandboxes), and an interrupt that arrived during that window
            # would otherwise have to fall through the stdin-interrupt /
            # SIGTERM path after a process we never wanted got spawned.
            if self._is_interrupted.is_set():
                logger.info("Skipping CLI spawn — interrupted during turn setup")
                return
            # SCU-211: spawn the agent CLI in its own process group so that
            # Stop's SIGTERM/SIGKILL cascades to any foreground subprocesses
            # the CLI spawned (e.g. the sh process behind a Bash tool call).
            # Without this, the CLI dies but its children become orphans and
            # keep running.
            process = self.environment.run_process_in_background(
                claude_command, secrets=child_env, open_stdin=True, isolate_process_group=True
            )
            self._process = process
            # Send an initialize control request (registers a PreCompact hook
            # callback for auto-compaction detection) followed by the user message.
            self._record_and_write_stdin(process, self._build_initialize_control_request())
            self._record_and_write_stdin(process, self._build_stdin_user_message(user_instructions))
            cli_succeeded = False
            try:
                self._read_output_from_process(process, claude_command)
                cli_succeeded = True
            finally:
                # After the CLI completes, finalize any answers delivered
                # mid-turn via the MCP server. We deferred their RequestSuccess
                # so the post-answer ``tool_result`` + follow-up content reaches
                # the frontend's in-progress chat message before it gets
                # finalized. This must run on the interrupt path too, otherwise
                # the answer's request_id stays as the active
                # in_progress_user_message_id on the frontend and the StatusPill
                # is stuck "thinking" until the user clicks Stop a second time.
                while self._pending_answer_request_ids:
                    pending_id = self._pending_answer_request_ids.pop(0)
                    self._output_messages.put(
                        RequestSuccessAgentMessage(
                            message_id=AgentMessageID(),
                            request_id=pending_id,
                            interrupted=not cli_succeeded,
                        )
                    )

            # reinitialize the diff tracker with the new tree hash - this will clear the in-memory snapshots but that is okay because we have the new tree hash
            self._diff_tracker.update_initial_tree_sha()

    def _process_clear_context_message(self, message: UserMessageUnion) -> None:
        with self._handle_user_message_callback(message):
            # Clear context by removing both session ID state files.
            # The next message will start a fresh claude session without --resume.
            session_id_state_file = self._harness.session_id_state_file_name
            validated_session_id_state_file = self._harness.validated_session_id_state_file_name
            session_id_path = str(self.environment.get_state_path() / session_id_state_file)
            validated_session_id_path = str(self.environment.get_state_path() / validated_session_id_state_file)
            for path in (session_id_path, validated_session_id_path):
                try:
                    self.environment.delete_file_or_directory(path)
                except OSError:
                    pass
            self._output_messages.put(ContextClearedMessage(message_id=AgentMessageID()))
            logger.info("Cleared context for task {}", self.task_id)

    def _on_plan_mode_changed(self, is_in_plan_mode: bool) -> None:
        self._is_in_plan_mode = is_in_plan_mode

    @staticmethod
    def _shutdown_process(process: RunningProcess) -> bool:
        """Close stdin and wait for the process to exit, escalating to SIGTERM/SIGKILL.

        This must run unconditionally after every turn — including when output
        processing raised an exception — to avoid leaking the CLI process.

        The shutdown sequence matches the official claude-agent-sdk:
        close stdin → wait 5 s → SIGTERM → wait 5 s → SIGKILL.

        Returns True if the process had to be force-terminated (SIGTERM/SIGKILL),
        meaning its exit code is an artifact of the kill signal and should not be
        treated as a failure.

        This method never raises — exceptions from wait/terminate are logged and
        swallowed so that this is safe to call from a finally block without
        masking an in-flight exception.
        """
        # Close stdin so the process can exit cleanly after emitting its final
        # message.  This must happen after output processing completes (not
        # before), because the stdin pipe is needed for interrupt control
        # requests during processing.
        process.close_stdin()

        # The Claude CLI flushes its session transcript after receiving EOF on
        # stdin.  We give it 5 s to do so.  If it still hasn't exited — e.g.
        # because a backgrounded child process keeps it alive — we escalate.
        logger.info("Waiting for process to finish")
        try:
            process.wait(timeout=5.0)
            return False
        except TimeoutExpired:
            logger.info("Claude process did not exit 5s after stdin close, sending SIGTERM")
            try:
                process.terminate(force_kill_seconds=5.0)
            except TimeoutExpired:
                logger.info("Claude process did not exit after SIGTERM+SIGKILL, giving up")
            return True

    def _read_output_from_process(
        self,
        process: RunningProcess,
        claude_command: list[str],
    ) -> None:
        try:
            ClaudeOutputProcessor.build_and_process_output(
                process=process,
                source_command=" ".join(claude_command),
                output_message_queue=self._output_messages,
                environment=self.environment,
                diff_tracker=self._diff_tracker,
                task_id=self.task_id,
                session_id_written_event=self._session_id_written_event,
                harness=self._harness,
                streaming_enabled=True,
                on_diff_needed=self._on_diff_needed,
                on_plan_mode_changed=self._on_plan_mode_changed,
                interrupted_event=self._is_interrupted,
                transcript_collector=self._transcript_collector,
                mcp_server=self._mcp_server,
                workspace_id=self._workspace_id,
            )
        finally:
            # Always clear the interrupted flag after output processing completes
            # (whether normally or via exception). Leaving it set causes the idle
            # timeout to fire on subsequent turns that were never interrupted.
            was_interrupted = self._is_interrupted.is_set()
            self._is_interrupted.clear()

            # Always terminate the process, even when output processing raised
            # (e.g. AgentClientError from an error end message).  Without this,
            # the process stays alive waiting on stdin and leaks.
            was_force_killed = self._shutdown_process(process)

        # Exit-code diagnostics — only reachable when output processing succeeded
        # (no exception).  When it raised, the process is already cleaned up above.
        assert process.returncode is not None, "Process return code should be set by now"
        logger.info(
            "Process returned return code {}, {}, {}", process.returncode, process.read_stdout(), process.read_stderr()
        )
        if self._is_fake_claude:
            logger.info("FakeClaude response (stdout): {}", process.read_stdout())

        if was_interrupted:
            logger.info("Agent was interrupted, ignoring exit code")
        elif was_force_killed:
            # The process completed its response (end message was emitted and output
            # was captured) but didn't exit in time, so we sent SIGTERM/SIGKILL.
            # The non-zero exit code is an artifact of the kill signal, not a real
            # failure — skip the exit code check.
            logger.info("Process was force-terminated after output completed, ignoring exit code")
        else:
            if process.returncode != 0:
                stdout = process.read_stdout()
                stderr = process.read_stderr()
                # TODO: figure out how to distinguish between claude and environment errors here
                raise AgentClientError(
                    f"Agent died with exit code {process.returncode}",
                    exit_code=process.returncode,
                    metadata={
                        "source_command": " ".join(claude_command),
                        "error": ErrorType.NONZERO_EXIT_CODE,
                        "stderr": stderr[-500:] if stderr else "",
                        "stdout": stdout[-500:] if stdout else "",
                    },
                )
        logger.info("Process finished.")
