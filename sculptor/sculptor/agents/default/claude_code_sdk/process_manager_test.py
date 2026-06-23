import contextlib
import shutil
import signal
import tempfile
from pathlib import Path
from queue import Queue
from subprocess import TimeoutExpired
from typing import Generator
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

import pytest

from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.default.claude_code_sdk.process_manager import ClaudeProcessManager
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LOCAL_WORKSPACE_DIR
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.services.workspace_service.setup_command_runner import FailedSetup
from sculptor.services.workspace_service.setup_command_runner import RunningSetup
from sculptor.services.workspace_service.setup_command_runner import SetupReminderState
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import QuestionOption
from sculptor.state.chat_state import UserQuestion
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel


@pytest.fixture
def local_environment(
    test_root_concurrency_group: ConcurrencyGroup,
) -> Generator[AgentExecutionEnvironment, None, None]:
    workspace_dir = LOCAL_WORKSPACE_DIR / uuid4().hex
    workspace_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = workspace_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    try:
        local_env = LocalEnvironment.create(
            environment_id=LocalEnvironmentID(str(workspace_dir)),
            project_id=ProjectID(),
            concurrency_group=test_root_concurrency_group,
            repo_host_path=repo_dir,
        )
        mock_cg = MagicMock(spec=ConcurrencyGroup)
        dep_service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        yield LocalAgentExecutionEnvironment(local_env, TaskID(), dep_service)
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


def _make_process_manager(
    local_environment: AgentExecutionEnvironment,
    setup_state_provider=None,
) -> ClaudeProcessManager:
    """Create a ClaudeProcessManager for testing."""
    return ClaudeProcessManager(
        environment=local_environment,
        task_id=TaskID(),
        in_testing=True,
        secrets={},
        output_message_queue=Queue(),
        handle_user_message_callback=lambda msg: contextlib.nullcontext(),
        system_prompt="",
        harness=CLAUDE_CODE_HARNESS,
        setup_state_provider=setup_state_provider,
    )


class _StubProvider:
    def __init__(self, result: SetupReminderState | None) -> None:
        self._result = result
        self.calls = 0

    def get_reminder_state(self) -> SetupReminderState | None:
        self.calls += 1
        return self._result


def test_fetch_setup_state_returns_none_when_provider_missing(
    local_environment: AgentExecutionEnvironment,
) -> None:
    process_manager = _make_process_manager(local_environment, setup_state_provider=None)
    assert process_manager._fetch_setup_state(is_first_message=True) is None


def test_fetch_setup_state_skips_provider_on_subsequent_messages(
    local_environment: AgentExecutionEnvironment,
) -> None:
    provider = _StubProvider(RunningSetup(command="npm ci", pid=1, log_path="/tmp/x"))
    process_manager = _make_process_manager(local_environment, setup_state_provider=provider)
    result = process_manager._fetch_setup_state(is_first_message=False)
    assert result is None
    assert provider.calls == 0


def test_fetch_setup_state_returns_running_on_first_message(
    local_environment: AgentExecutionEnvironment,
) -> None:
    running = RunningSetup(command="npm ci", pid=42, log_path="/tmp/log")
    provider = _StubProvider(running)
    process_manager = _make_process_manager(local_environment, setup_state_provider=provider)
    result = process_manager._fetch_setup_state(is_first_message=True)
    assert result == running
    assert provider.calls == 1


def test_fetch_setup_state_returns_failed_on_first_message(
    local_environment: AgentExecutionEnvironment,
) -> None:
    failed = FailedSetup(command="npm ci", exit_code=2, log_path="/tmp/log")
    provider = _StubProvider(failed)
    process_manager = _make_process_manager(local_environment, setup_state_provider=provider)
    result = process_manager._fetch_setup_state(is_first_message=True)
    assert result == failed


def test_maybe_save_files_to_environment_saves_binary_image_files(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """Test that _maybe_save_files_to_environment correctly saves binary image files."""
    process_manager = _make_process_manager(local_environment)

    # Create a temporary image file with binary content (PNG header)
    binary_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        tmp_file.write(binary_content)
        tmp_file_path = tmp_file.name

    try:
        message = ChatInputUserMessage(text="Check this image", files=[tmp_file_path])
        saved_paths = process_manager._maybe_save_files_to_environment(message)

        assert len(saved_paths) == 1
        # Verify the file was written correctly by reading it back as bytes
        saved_content = local_environment.read_file(path=saved_paths[0], mode="rb")
        assert saved_content == binary_content
    finally:
        Path(tmp_file_path).unlink(missing_ok=True)


def test_maybe_save_files_to_environment_preserves_filename(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """Test that _maybe_save_files_to_environment preserves the original filename."""
    process_manager = _make_process_manager(local_environment)

    binary_content = b"\xff\xd8\xff\xe0" + b"\x00" * 50  # JPEG header
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, prefix="my_photo_") as tmp_file:
        tmp_file.write(binary_content)
        tmp_file_path = tmp_file.name

    try:
        message = ChatInputUserMessage(text="Check this", files=[tmp_file_path])
        saved_paths = process_manager._maybe_save_files_to_environment(message)

        assert len(saved_paths) == 1
        saved_filename = Path(saved_paths[0]).name
        original_filename = Path(tmp_file_path).name
        assert saved_filename == original_filename
    finally:
        Path(tmp_file_path).unlink(missing_ok=True)


def test_maybe_save_files_to_environment_returns_empty_for_non_chat_messages(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """Test that _maybe_save_files_to_environment returns empty tuple for non-ChatInputUserMessage."""
    process_manager = _make_process_manager(local_environment)

    message = InterruptProcessUserMessage()
    saved_paths = process_manager._maybe_save_files_to_environment(message)

    assert saved_paths == ()


def test_stop_closes_transcript_file_and_is_idempotent(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """stop() must close the per-manager transcript file so the long-lived
    backend does not leak one fd per agent task start/resume.

    A fresh ClaudeProcessManager is constructed for every task start/resume, and
    each one opens ``transcript.jsonl`` in __init__. Before this fix nothing ever
    closed it, so the fd lingered until garbage collection. Closing must also be
    idempotent — stop() can be called more than once during teardown.
    """
    process_manager = _make_process_manager(local_environment)

    # No process or worker thread were ever started, so stop() falls straight
    # through to the transcript-close in its finally block.
    assert not process_manager._transcript_file.closed
    process_manager.stop(timeout=1.0)
    assert process_manager._transcript_file.closed

    # A second stop() must not raise (close() on an already-closed file is a no-op).
    process_manager.stop(timeout=1.0)
    assert process_manager._transcript_file.closed


def test_stop_terminates_process_gracefully_on_wait_timeout(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """Regression test: stop(is_waiting=True) should terminate a stuck process
    instead of raising WaitTimeoutAgentError.

    Previously, when the Claude Code subprocess was slow to exit after completing
    its work, stop() would raise WaitTimeoutAgentError, which propagated through
    ConcurrencyGroup.__exit__ and crashed the task with a ConcurrencyExceptionGroup.
    """
    process_manager = _make_process_manager(local_environment)

    mock_process = MagicMock()
    mock_process.wait.side_effect = TimeoutExpired(cmd=["claude"], timeout=5.0)
    process_manager._process = mock_process

    # Should not raise — it should terminate the stuck process instead
    process_manager.stop(timeout=10.0, is_waiting=True)

    mock_process.wait.assert_called_once()
    mock_process.terminate.assert_called_once_with(force_kill_seconds=2.0)


def test_is_interrupted_cleared_after_output_processing_raises(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """Regression test: _is_interrupted must be cleared even when build_and_process_output
    raises AgentClientError (e.g. after a user interrupt).

    Previously, an interrupted turn would raise AgentClientError from _parse_stream_end_response,
    which propagated out of _read_output_from_process without clearing _is_interrupted. This
    caused subsequent turns to be killed by the idle timeout, which checks _is_interrupted.is_set().
    """
    process_manager = _make_process_manager(local_environment)

    # Simulate the interrupt flag being set (as interrupt_current_message does)
    process_manager._is_interrupted.set()

    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()

    # Simulate build_and_process_output raising AgentClientError (the interrupt error path)
    with patch.object(
        type(process_manager),
        "_read_output_from_process",
        wraps=process_manager._read_output_from_process,
    ):
        with patch(
            "sculptor.agents.default.claude_code_sdk.process_manager.ClaudeOutputProcessor.build_and_process_output",
            side_effect=AgentClientError("error_during_execution", exit_code=1),
        ):
            with pytest.raises(AgentClientError):
                process_manager._read_output_from_process(mock_process, ["claude"])

    # The critical assertion: _is_interrupted must be cleared after the exception
    assert not process_manager._is_interrupted.is_set(), (
        "_is_interrupted was not cleared after AgentClientError — subsequent turns will be killed by the idle timeout"
    )


def test_is_interrupted_cleared_when_process_requires_sigterm(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """Regression test: _is_interrupted must be cleared even when the process
    doesn't exit within 5s and requires SIGTERM (the early-return path).

    This simulates the cascade scenario: the idle timeout breaks the output loop
    (build_and_process_output returns normally), but the CLI process is still
    running. process.wait() times out, SIGTERM is sent, and _read_output_from_process
    returns early. Previously this early return skipped _is_interrupted.clear().
    """
    process_manager = _make_process_manager(local_environment)

    # Simulate the interrupt flag being set
    process_manager._is_interrupted.set()

    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()
    # process.wait() times out → SIGTERM path
    mock_process.wait.side_effect = TimeoutExpired(cmd=["claude"], timeout=5.0)

    with patch(
        "sculptor.agents.default.claude_code_sdk.process_manager.ClaudeOutputProcessor.build_and_process_output",
    ):
        process_manager._read_output_from_process(mock_process, ["claude"])

    assert not process_manager._is_interrupted.is_set(), "_is_interrupted was not cleared after SIGTERM early-return"


def test_slow_exit_after_successful_response_does_not_raise(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """When the CLI completes its response but the process is slow to exit
    (e.g. a backgrounded child keeps it alive), _shutdown_process escalates to
    SIGTERM. The resulting non-zero exit code (143) should not be treated as a
    failure since the response was fully captured.
    """
    process_manager = _make_process_manager(local_environment)

    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()
    # process.wait() times out → SIGTERM path
    mock_process.wait.side_effect = TimeoutExpired(cmd=["claude"], timeout=5.0)
    # After SIGTERM, the process has exit code 143 (128 + 15).
    mock_process.returncode = 143
    mock_process.read_stdout.return_value = ""
    mock_process.read_stderr.return_value = ""

    with patch(
        "sculptor.agents.default.claude_code_sdk.process_manager.ClaudeOutputProcessor.build_and_process_output",
    ):
        # This should NOT raise.  The response was fully captured; the non-zero
        # exit code is an artifact of SIGTERM, not a real failure.
        process_manager._read_output_from_process(mock_process, ["claude"])

    # Verify shutdown was attempted: close_stdin → wait → terminate
    mock_process.close_stdin.assert_called_once()
    mock_process.wait.assert_called_once_with(timeout=5.0)
    mock_process.terminate.assert_called_once_with(force_kill_seconds=5.0)


def test_shutdown_exception_does_not_mask_original_error(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """When build_and_process_output raises and _shutdown_process also fails
    (e.g. the process resists SIGTERM), the original AgentClientError should
    propagate — not be replaced by the TimeoutExpired from shutdown.
    """
    process_manager = _make_process_manager(local_environment)

    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()
    # process.wait() times out, then terminate() also times out
    mock_process.wait.side_effect = TimeoutExpired(cmd=["claude"], timeout=5.0)
    mock_process.terminate.side_effect = TimeoutExpired(cmd=["claude"], timeout=5.0)

    original_error = AgentClientError("API returned an error", exit_code=1)

    with patch(
        "sculptor.agents.default.claude_code_sdk.process_manager.ClaudeOutputProcessor.build_and_process_output",
        side_effect=original_error,
    ):
        with pytest.raises(AgentClientError, match="API returned an error"):
            process_manager._read_output_from_process(mock_process, ["claude"])


def _drain_queue(queue: Queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def test_interrupt_escalates_to_sigkill_without_crashing_when_worker_is_wedged(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """SCU-1340: when the message-processing (worker) thread survives the stdin
    interrupt, SIGTERM, AND SIGKILL on its process group — the pathological case
    (e.g. an uninterruptible kernel wait or zombie) — ``interrupt_current_message``
    must NOT raise.

    Stop is a user action and must never crash the agent runner. Before the fix
    this raised ``TimeoutError("Message processing thread failed to terminate")``
    (the exact crash in the ticket's production trace). The phased escalation
    must instead:

      (a) propagate no exception out of ``interrupt_current_message``,
      (b) escalate SIGTERM then SIGKILL to the process group *from the interrupt
          thread* (``kill_now``) rather than depending on the wedged worker
          thread's own shutdown path,
      (c) emit ``RequestSuccess(interrupted=True)`` for the in-flight request so
          the frontend's chat message resolves instead of staying stuck
          "thinking" forever, and
      (d) record the leaked worker thread in an observable counter.
    """
    process_manager = _make_process_manager(local_environment)

    # A worker thread that never exits no matter how often we join it — models a
    # thread wedged in an uninterruptible wait that even SIGKILL cannot reap.
    wedged_thread = MagicMock()
    wedged_thread.is_alive.return_value = True
    process_manager._message_processing_thread = wedged_thread

    # A process whose ``kill_now`` is a no-op: signals are "sent" but the worker
    # still never dies (the pathological process group surviving SIGKILL).
    mock_process = MagicMock()
    process_manager._process = mock_process

    in_flight_id = AgentMessageID()
    process_manager._in_flight_request_id = in_flight_id

    # (a) Must not raise.
    process_manager.interrupt_current_message(InterruptProcessUserMessage())

    # (b) Both SIGTERM and SIGKILL were sent to the process group, and the
    # wedged worker's ``terminate`` shutdown path was NOT relied on.
    sent_signals = [c.args[0] for c in mock_process.kill_now.call_args_list]
    assert signal.SIGTERM in sent_signals, "SIGTERM was never sent to the process group"
    assert signal.SIGKILL in sent_signals, "escalation to SIGKILL on the process group never happened"
    mock_process.terminate.assert_not_called()

    # (c) RequestSuccess(interrupted=True) was emitted for the in-flight request.
    emitted = _drain_queue(process_manager._output_messages)
    successes = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage)]
    assert any(m.request_id == in_flight_id and m.interrupted for m in successes), (
        "interrupt_current_message must emit RequestSuccess(interrupted=True) directly in the pathological case so the frontend's chat message does not stay stuck 'thinking'"
    )

    # (d) The leaked worker thread is counted somewhere observable.
    assert process_manager._leaked_interrupt_worker_thread_count == 1


def test_interrupt_reconciles_stuck_thinking_when_worker_thread_is_dead(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """SCU-1405: when the user clicks Stop and the message-processing (worker)
    thread is no longer alive while a turn is still in flight, Stop must NOT be a
    silent no-op — it must emit ``RequestSuccess(interrupted=True)`` for the
    in-flight request so the frontend's chat message resolves instead of staying
    stuck "thinking" forever.

    This is the no-op branch of ``interrupt_current_message`` (the
    ``process_manager.py:"Message processing thread is not alive"`` log line in
    the ticket's production trace). It is the sibling of the SCU-1340 Phase D
    pathological tail (worker *wedged*): there the worker survives SIGKILL, here
    the worker is already gone, but both leave the same orphaned in-flight
    request that the frontend renders as a perpetual "thinking" spinner. The
    worker can die without its wrapper emitting a terminal message (e.g. a
    BaseException the wrapper's ``except Exception`` does not catch), so Stop is
    the last line of defense and must reconcile the UI in this state too.

    Before the fix the no-op branch sets the interrupt flag and returns without
    emitting anything, so this test fails (no RequestSuccess is produced).
    """
    process_manager = _make_process_manager(local_environment)

    # A worker thread that has already finished — ``is_alive()`` is False — which
    # routes ``interrupt_current_message`` into its no-op branch.
    dead_thread = MagicMock()
    dead_thread.is_alive.return_value = False
    process_manager._message_processing_thread = dead_thread
    # The CLI process is gone along with the dead worker thread.
    process_manager._process = None

    # A turn is still in flight from the frontend's point of view: its
    # RequestStarted was emitted but no terminal RequestSuccess ever followed.
    in_flight_id = AgentMessageID()
    process_manager._in_flight_request_id = in_flight_id

    # Must not raise — Stop is a user action and must never crash the runner.
    process_manager.interrupt_current_message(InterruptProcessUserMessage())

    # The fix: a terminal RequestSuccess(interrupted=True) is emitted for the
    # in-flight request so the stuck "thinking" chat message resolves.
    emitted = _drain_queue(process_manager._output_messages)
    successes = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage)]
    assert any(m.request_id == in_flight_id and m.interrupted for m in successes), (
        "interrupt_current_message must emit RequestSuccess(interrupted=True) in the no-op branch (dead worker thread) so the frontend's in-progress chat message does not stay stuck 'thinking'"
    )


def test_resume_in_flight_request_id_is_for_user_message_id(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """A ``ResumeAgentResponseRunnerMessage`` continues an earlier user turn, so the
    in-flight request id the manager tracks for it must be that turn's id
    (``for_user_message_id``) -- NOT the resume message's own freshly generated
    ``message_id``.

    ``_in_flight_request_id`` is what the interrupt paths
    (``_resolve_in_flight_request_as_interrupted``) key their terminal
    ``RequestSuccess`` on. If it holds the resume's own id, an interrupt during a
    resumed turn emits a completion that never matches the original chat message,
    leaving the StatusPill stuck "thinking" and the run-loop unable to advance.
    """
    process_manager = _make_process_manager(local_environment)
    original_user_message_id = AgentMessageID()
    resume_message = ResumeAgentResponseRunnerMessage(
        for_user_message_id=original_user_message_id,
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    # Sanity: the resume message has its own id, distinct from the turn it resumes.
    assert resume_message.message_id != original_user_message_id

    # ``_in_flight_request_id`` is assigned synchronously, before the worker
    # thread is started; patch the spawn so no real CLI runs.
    with patch.object(ConcurrencyGroup, "start_new_thread"):
        process_manager.process_input_message(resume_message)

    assert process_manager._in_flight_request_id == original_user_message_id, (
        f"resume must track for_user_message_id as in-flight; got {process_manager._in_flight_request_id}"
    )


def _make_question_answer(tool_use_id: str) -> UserQuestionAnswerMessage:
    question = UserQuestion(
        question="Pick a color",
        header="Color",
        options=[QuestionOption(label="Red", description=""), QuestionOption(label="Blue", description="")],
        multi_select=False,
    )
    return UserQuestionAnswerMessage(
        answers={"Pick a color": "Red"},
        question_data=AskUserQuestionData(questions=[question], tool_use_id=tool_use_id),
        tool_use_id=tool_use_id,
    )


def test_stale_question_answer_with_no_pending_call_is_discarded_not_wedged(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """SCU-1426: a UserQuestionAnswerMessage whose tool_use_id matches no pending
    MCP call must be discarded — not respawned, and never raised on.

    This is the ticket's crash site (the ``raise IllegalOperationError`` in
    ``process_input_message``). After a restart during an in-flight,
    AskUserQuestion-bearing turn, the runner can re-deliver an already-consumed
    answer whose original question no longer exists: on resume the CLI re-issues
    the dangling question under a *new* ``tool_use_id``, so the stale answer
    matches no pending MCP call. ``_try_deliver_answer_to_mcp`` therefore bails,
    and the old behaviour fell through to the respawn guard and raised
    ``IllegalOperationError`` while the worker thread was still parked on the
    re-issued question — wedging the task (``outcome=RUNNING`` with no live
    process, Stop a no-op; the same RUNNING-but-wedged family as SCU-1404 /
    SCU-1405).

    A question-answer that matches no pending question can never be the start of
    a fresh turn (an answer is not a prompt), so the fix discards it — emitting
    ``RequestSkippedAgentMessage`` so the runner's in-flight bookkeeping and the
    frontend's chat message both resolve — instead of respawning or raising.
    """
    process_manager = _make_process_manager(local_environment)

    # A worker thread is still parked on a (re-issued) question — alive.
    parked_thread = MagicMock()
    parked_thread.is_alive.return_value = True
    process_manager._message_processing_thread = parked_thread

    # A live CLI process is bound, but its MCP server holds no pending call
    # matching the stale answer's tool_use_id (the re-issued question got a fresh
    # tool_use_id; the registry has no entry for the stale one).
    mock_process = MagicMock()
    mock_process.is_finished.return_value = False
    process_manager._process = mock_process

    stale_answer = _make_question_answer(tool_use_id="toolu_already_consumed")
    assert not process_manager._mcp_server.has_pending_call(stale_answer.tool_use_id)

    # Must NOT raise IllegalOperationError (the wedge) ...
    process_manager.process_input_message(stale_answer)

    # ... must NOT respawn a fresh turn (the parked worker is left untouched) ...
    assert process_manager._message_processing_thread is parked_thread, (
        "a stale answer must not respawn a new message-processing turn"
    )
    # ... and must emit a terminal RequestSkipped so the stale answer resolves
    # instead of leaving the runner / frontend waiting on it forever.
    emitted = _drain_queue(process_manager._output_messages)
    assert any(
        isinstance(m, RequestSkippedAgentMessage) and m.request_id == stale_answer.message_id for m in emitted
    ), "stale answer must be discarded via RequestSkippedAgentMessage — not respawned or raised on"
