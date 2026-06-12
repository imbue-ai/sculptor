import json
import shlex
import threading
import time
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock

import pytest

from imbue_core.agents.data_types.ids import TaskID
from sculptor.agents.default.claude_code_sdk.btw_process_manager import BtwProcessManager
from sculptor.agents.default.claude_code_sdk.btw_process_manager import NoBtwSessionAvailable
from sculptor.agents.default.claude_code_sdk.btw_process_manager import get_btw_claude_command
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.interfaces.agents.errors import ClaudeBinaryNotFoundError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.data_types import BtwUpdate


def _make_environment(
    *,
    session_id: str | None = None,
    validated_session_id: str | None = None,
    binary_path: str | None = "/bin/claude",
    process: MagicMock | None = None,
) -> AgentExecutionEnvironment:
    """Build a MagicMock environment that reads the two state files and
    optionally returns a fake subprocess."""
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_state_path.return_value = Path("/state")
    env.get_tool_binary_path.return_value = binary_path

    def fake_read_file(path: str, mode: str = "r") -> str:
        if path.endswith("/session_id"):
            if session_id is None:
                raise FileNotFoundError(path)
            return session_id
        if path.endswith("/validated_session_id"):
            if validated_session_id is None:
                raise FileNotFoundError(path)
            return validated_session_id
        raise FileNotFoundError(path)

    env.read_file.side_effect = fake_read_file
    if process is not None:
        env.run_process_in_background.return_value = process
    return env


def _make_process(lines: list[str], returncode: int = 0, stderr: str = "") -> MagicMock:
    """Fake RunningProcess: replays the given stdout lines then finishes."""
    queue: Queue[tuple[str, bool]] = Queue()
    for line in lines:
        queue.put((line, True))

    process = MagicMock()
    process.get_queue.return_value = queue
    process.is_finished.side_effect = [False] * len(lines) + [True]
    process.wait.return_value = returncode
    process.read_stderr.return_value = stderr
    return process


def _text_delta_line(text: str) -> str:
    return json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        }
    )


def test_get_btw_claude_command_flags() -> None:
    command = get_btw_claude_command(
        claude_binary_path="/bin/claude",
        main_session_id="abc-123",
        question="why did you pick sqlite?",
    )
    assert command[:2] == ["bash", "-c"]
    body = command[2]
    tokens = shlex.split(body)
    assert tokens[0] == "exec"
    assert "IS_SANDBOX=1" in tokens
    assert "/bin/claude" in tokens
    assert "abc-123" in tokens
    assert tokens[tokens.index("--resume") + 1] == "abc-123"
    assert "--fork-session" in tokens
    assert "--no-session-persistence" in tokens
    assert tokens[tokens.index("-p") + 1] == "why did you pick sqlite?"
    assert tokens[tokens.index("--model") + 1] == "haiku"
    assert tokens[tokens.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in tokens
    assert "--disable-slash-commands" in tokens
    assert "--append-system-prompt" in tokens
    assert "--output-format=stream-json" in tokens
    assert "--include-partial-messages" in tokens
    assert "--verbose" in tokens
    assert "--dangerously-skip-permissions" in tokens


def test_get_btw_claude_command_quotes_question() -> None:
    dangerous = "rm -rf / ; echo 'oops'"
    command = get_btw_claude_command(
        claude_binary_path="/bin/claude",
        main_session_id="abc",
        question=dangerous,
    )
    body = command[2]
    # The question must survive shlex.split as a single argument — no bare
    # semicolons or command chaining can escape into bash.
    tokens = shlex.split(body)
    assert tokens[tokens.index("-p") + 1] == dangerous


def _manager(environment: AgentExecutionEnvironment) -> BtwProcessManager:
    return BtwProcessManager(
        environment=environment,
        task_id=TaskID(),
        workspace_id=WorkspaceID(),
        publish=lambda _: None,
        harness=CLAUDE_CODE_HARNESS,
    )


def test_read_session_id_returns_primary_when_present() -> None:
    env = _make_environment(session_id="session-abc")
    assert _manager(env).read_session_id() == "session-abc"


def test_read_session_id_falls_back_to_validated() -> None:
    env = _make_environment(validated_session_id="validated-xyz")
    assert _manager(env).read_session_id() == "validated-xyz"


def test_read_session_id_returns_none_when_both_missing() -> None:
    env = _make_environment()
    assert _manager(env).read_session_id() is None


def test_wait_for_session_id_returns_immediately_when_already_present() -> None:
    env = _make_environment(session_id="session-now")
    start = time.monotonic()
    result = _manager(env).wait_for_session_id(timeout=1.0)
    elapsed = time.monotonic() - start
    assert result == "session-now"
    assert elapsed < 0.2, f"wait took {elapsed:.3f}s — should have returned without polling"


def test_wait_for_session_id_returns_none_after_timeout() -> None:
    env = _make_environment()
    start = time.monotonic()
    result = _manager(env).wait_for_session_id(timeout=0.2)
    elapsed = time.monotonic() - start
    assert result is None
    assert 0.2 <= elapsed < 1.0, f"wait elapsed {elapsed:.3f}s — should be ~0.2s"


def test_wait_for_session_id_picks_up_late_write() -> None:
    """Cold-start race: file appears mid-wait (mirrors main agent's
    `system/init` writing the session file after `/btw` already arrived)."""
    state: dict[str, str | None] = {"session_id": None}

    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_state_path.return_value = Path("/state")

    def fake_read_file(path: str, mode: str = "r") -> str:
        if path.endswith("/session_id"):
            value = state["session_id"]
            if value is None:
                raise FileNotFoundError(path)
            return value
        raise FileNotFoundError(path)

    env.read_file.side_effect = fake_read_file

    def write_after_delay() -> None:
        time.sleep(0.15)
        state["session_id"] = "session-late"

    writer = threading.Thread(target=write_after_delay)
    writer.start()
    try:
        result = _manager(env).wait_for_session_id(timeout=2.0)
    finally:
        writer.join()

    assert result == "session-late"


def test_run_btw_raises_no_session_available_when_missing() -> None:
    env = _make_environment()
    manager = _manager(env)
    with pytest.raises(NoBtwSessionAvailable):
        manager.run_btw(question="hi", request_id="req-1")


def test_run_btw_raises_on_missing_binary() -> None:
    env = _make_environment(session_id="abc", binary_path=None)
    manager = _manager(env)
    with pytest.raises(ClaudeBinaryNotFoundError):
        manager.run_btw(question="hi", request_id="req-1")


def test_publish_emits_running_then_done() -> None:
    process = _make_process([_text_delta_line("Hel"), _text_delta_line("lo")])
    env = _make_environment(session_id="abc", process=process)
    updates: list[BtwUpdate] = []
    manager = BtwProcessManager(
        environment=env,
        task_id=TaskID(),
        workspace_id=WorkspaceID(),
        publish=updates.append,
        harness=CLAUDE_CODE_HARNESS,
    )

    manager.run_btw(question="hi", request_id="req-1")

    assert updates[0].state == "running"
    assert updates[0].answer == ""
    assert updates[-1].state == "done"
    assert updates[-1].answer == "Hello"


def test_publish_emits_error_on_nonzero_exit_code() -> None:
    process = _make_process([_text_delta_line("par")], returncode=2, stderr="boom")
    env = _make_environment(session_id="abc", process=process)
    updates: list[BtwUpdate] = []
    manager = BtwProcessManager(
        environment=env,
        task_id=TaskID(),
        workspace_id=WorkspaceID(),
        publish=updates.append,
        harness=CLAUDE_CODE_HARNESS,
    )

    manager.run_btw(question="hi", request_id="req-1")

    assert updates[-1].state == "error"
    error_message = updates[-1].error_message
    assert error_message is not None
    assert "boom" in error_message
