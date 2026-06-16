"""Unit tests for SetupCommandRunner."""

import threading
import time
from pathlib import Path
from threading import Event
from typing import Callable
from unittest.mock import MagicMock

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.services.workspace_service.setup_command_runner import HEAD_BYTES
from sculptor.services.workspace_service.setup_command_runner import LOG_FILENAME
from sculptor.services.workspace_service.setup_command_runner import SetupCommandRunner
from sculptor.services.workspace_service.setup_command_runner import SetupOutputChunk
from sculptor.services.workspace_service.setup_command_runner import SetupStateChanged
from sculptor.services.workspace_service.setup_command_runner import TAIL_BYTES
from sculptor.services.workspace_service.setup_command_runner import TRUNCATION_MARKER


@pytest.fixture
def runner(test_root_concurrency_group: ConcurrencyGroup) -> SetupCommandRunner:
    return SetupCommandRunner(test_root_concurrency_group)


def _wait_until_terminal(runner: SetupCommandRunner, ws_id: str, timeout: float = 5.0) -> SetupStateChanged:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = runner.get_state(ws_id)
        if state is not None and state.status not in ("running", "pending"):
            return state
        time.sleep(0.05)
    raise AssertionError(f"setup did not reach terminal state in {timeout}s")


def _wrap(
    fn: Callable[[Callable[[bytes], None], ReadOnlyEvent], int],
) -> Callable[[str, Callable[[bytes], None], Callable[[int], None], ReadOnlyEvent], int]:
    return lambda _command, on_chunk, _on_pid, shutdown: fn(on_chunk, shutdown)


def test_run_succeeds(runner: SetupCommandRunner, tmp_path: Path) -> None:
    def _execute(on_chunk: Callable[[bytes], None], _shutdown: ReadOnlyEvent) -> int:
        on_chunk(b"hello\n")
        return 0

    persisted: list[SetupStateChanged] = []
    runner.start("ws1", "echo hi", _wrap(_execute), Event(), tmp_path, persisted.append)
    final = _wait_until_terminal(runner, "ws1")
    assert final.status == "succeeded"
    assert final.exit_code == 0
    assert final.run_id is not None
    assert final.log_path == LOG_FILENAME
    assert (tmp_path / LOG_FILENAME).read_bytes().startswith(b"hello")
    assert len(persisted) == 2
    assert persisted[0].status == "running"
    assert persisted[1].status == "succeeded"


def test_run_fails(runner: SetupCommandRunner, tmp_path: Path) -> None:
    def _execute(on_chunk: Callable[[bytes], None], _shutdown: ReadOnlyEvent) -> int:
        on_chunk(b"oops\n")
        return 1

    persisted: list[SetupStateChanged] = []
    runner.start("ws", "false", _wrap(_execute), Event(), tmp_path, persisted.append)
    final = _wait_until_terminal(runner, "ws")
    assert final.status == "failed"
    assert final.exit_code == 1


def test_cancel_transitions_to_failed(runner: SetupCommandRunner, tmp_path: Path) -> None:
    started = threading.Event()

    def _execute(_on_chunk: Callable[[bytes], None], shutdown: ReadOnlyEvent) -> int:
        started.set()
        for _ in range(200):
            if shutdown.is_set():
                return -2
            time.sleep(0.02)
        return 0

    persisted: list[SetupStateChanged] = []
    runner.start("ws", "sleep 60", _wrap(_execute), Event(), tmp_path, persisted.append)
    assert started.wait(timeout=3.0)
    assert runner.cancel("ws") is True
    final = _wait_until_terminal(runner, "ws")
    assert final.status == "failed"
    assert final.exit_code == -2


def test_rerun_after_failure(runner: SetupCommandRunner, tmp_path: Path) -> None:
    call_count = {"n": 0}

    def _execute(on_chunk: Callable[[bytes], None], _shutdown: ReadOnlyEvent) -> int:
        call_count["n"] += 1
        on_chunk(f"run-{call_count['n']}\n".encode())
        return 1 if call_count["n"] == 1 else 0

    persisted: list[SetupStateChanged] = []
    runner.start("ws", "x", _wrap(_execute), Event(), tmp_path, persisted.append)
    first = _wait_until_terminal(runner, "ws")
    assert first.status == "failed"
    first_run_id = first.run_id
    runner.start("ws", "x", _wrap(_execute), Event(), tmp_path, persisted.append)
    second = _wait_until_terminal(runner, "ws")
    assert second.status == "succeeded"
    assert second.run_id != first_run_id
    assert b"run-2" in (tmp_path / LOG_FILENAME).read_bytes()


def test_start_rejects_when_already_running(runner: SetupCommandRunner, tmp_path: Path) -> None:
    release = threading.Event()

    def _execute(_on_chunk: Callable[[bytes], None], _shutdown: ReadOnlyEvent) -> int:
        release.wait(timeout=10.0)
        return 0

    persisted: list[SetupStateChanged] = []
    first = runner.start("ws", "x", _wrap(_execute), Event(), tmp_path, persisted.append)
    assert first.status == "running"
    second = runner.start("ws", "x", _wrap(_execute), Event(), tmp_path, persisted.append)
    assert second.run_id == first.run_id
    release.set()
    final = _wait_until_terminal(runner, "ws")
    assert final.status == "succeeded"


def test_log_buffer_truncation(runner: SetupCommandRunner, tmp_path: Path) -> None:
    payload_bytes = HEAD_BYTES + TAIL_BYTES + 1024 * 64

    def _execute(on_chunk: Callable[[bytes], None], _shutdown: ReadOnlyEvent) -> int:
        chunk = b"x" * 4096
        sent = 0
        while sent < payload_bytes:
            on_chunk(chunk)
            sent += len(chunk)
        return 0

    runner.start("ws", "spam", _wrap(_execute), Event(), tmp_path, MagicMock())
    final = _wait_until_terminal(runner, "ws", timeout=10.0)
    assert final.log_truncated is True
    body = (tmp_path / LOG_FILENAME).read_bytes()
    assert TRUNCATION_MARKER in body
    head, _marker, tail = body.partition(TRUNCATION_MARKER)
    assert len(head) == HEAD_BYTES
    assert len(tail) <= TAIL_BYTES


def test_chunk_seq_resets_per_run(runner: SetupCommandRunner, tmp_path: Path) -> None:
    def _execute(on_chunk: Callable[[bytes], None], _shutdown: ReadOnlyEvent) -> int:
        on_chunk(b"a")
        on_chunk(b"b")
        return 0

    seqs_per_run: dict[str, list[int]] = {}

    def _output_observer(event: SetupOutputChunk) -> None:
        seqs_per_run.setdefault(event.run_id, []).append(event.seq)

    runner.add_output_observer(_output_observer)
    runner.start("ws", "x", _wrap(_execute), Event(), tmp_path, MagicMock())
    _wait_until_terminal(runner, "ws")
    runner.start("ws", "x", _wrap(_execute), Event(), tmp_path, MagicMock())
    _wait_until_terminal(runner, "ws")
    assert len(seqs_per_run) == 2
    for seqs in seqs_per_run.values():
        assert seqs == [1, 2]


def test_mark_failed_for_reconcile(runner: SetupCommandRunner, tmp_path: Path) -> None:
    persisted: list[SetupStateChanged] = []
    state = runner.mark_failed_for_reconcile("ws", started_at=100.0, on_persist=persisted.append)
    assert state.status == "failed"
    assert state.exit_code is None
    assert state.started_at == 100.0
    assert state.finished_at is not None
    assert len(persisted) == 1


def test_stop_all_cancels_running(runner: SetupCommandRunner, tmp_path: Path) -> None:
    def _execute(_on_chunk: Callable[[bytes], None], shutdown: ReadOnlyEvent) -> int:
        for _ in range(200):
            if shutdown.is_set():
                return -1
            time.sleep(0.02)
        return 0

    runner.start("ws", "x", _wrap(_execute), Event(), tmp_path, MagicMock())
    runner.stop_all()
    final = _wait_until_terminal(runner, "ws")
    assert final.status == "failed"


def test_wait_for_pid_returns_pid_after_subprocess_reports_it(runner: SetupCommandRunner, tmp_path: Path) -> None:
    release = threading.Event()

    def _runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        on_pid: Callable[[int], None],
        _shutdown: ReadOnlyEvent,
    ) -> int:
        on_pid(4242)
        release.wait(timeout=5.0)
        return 0

    runner.start("ws", "x", _runner, Event(), tmp_path, MagicMock())
    pid = runner.wait_for_pid("ws", timeout=5.0)
    assert pid == 4242
    release.set()
    _wait_until_terminal(runner, "ws")


def test_wait_for_pid_returns_none_on_unknown_workspace(runner: SetupCommandRunner) -> None:
    assert runner.wait_for_pid("does-not-exist", timeout=0.1) is None


def test_wait_for_pid_returns_none_when_subprocess_never_reports_pid(
    runner: SetupCommandRunner, tmp_path: Path
) -> None:
    def _runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        _on_pid: Callable[[int], None],
        _shutdown: ReadOnlyEvent,
    ) -> int:
        return 1

    runner.start("ws", "x", _runner, Event(), tmp_path, MagicMock())
    _wait_until_terminal(runner, "ws")
    assert runner.wait_for_pid("ws", timeout=1.0) is None


def test_setup_state_changed_carries_pid(runner: SetupCommandRunner, tmp_path: Path) -> None:
    observed: list[SetupStateChanged] = []
    runner.add_state_observer(observed.append)

    def _runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        on_pid: Callable[[int], None],
        _shutdown: ReadOnlyEvent,
    ) -> int:
        on_pid(1234)
        return 0

    runner.start("ws", "x", _runner, Event(), tmp_path, MagicMock())
    _wait_until_terminal(runner, "ws")
    pids_seen = [event.pid for event in observed if event.pid is not None]
    assert 1234 in pids_seen
    # At least one event prior to terminal carried the pid.
    pid_event_indexes = [i for i, e in enumerate(observed) if e.pid == 1234 and e.status == "running"]
    assert pid_event_indexes, f"expected a running-state event with pid=1234, got {observed}"


def test_stop_all_unblocks_waiters(runner: SetupCommandRunner, tmp_path: Path) -> None:
    def _slow_runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        _on_pid: Callable[[int], None],
        shutdown: ReadOnlyEvent,
    ) -> int:
        for _ in range(200):
            if shutdown.is_set():
                return -1
            time.sleep(0.02)
        return 0

    runner.start("ws", "x", _slow_runner, Event(), tmp_path, MagicMock())
    runner.stop_all()
    start = time.monotonic()
    pid = runner.wait_for_pid("ws", timeout=5.0)
    elapsed = time.monotonic() - start
    assert pid is None
    assert elapsed < 5.0
    _wait_until_terminal(runner, "ws")
