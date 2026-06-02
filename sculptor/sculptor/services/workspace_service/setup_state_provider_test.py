"""Unit tests for the SetupStateProvider implementation."""

import threading
import time
from pathlib import Path
from threading import Event
from typing import Callable
from unittest.mock import MagicMock

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.services.workspace_service.setup_command_runner import DefaultSetupStateProvider
from sculptor.services.workspace_service.setup_command_runner import FailedSetup
from sculptor.services.workspace_service.setup_command_runner import LOG_FILENAME
from sculptor.services.workspace_service.setup_command_runner import RunnerSlot
from sculptor.services.workspace_service.setup_command_runner import RunningSetup
from sculptor.services.workspace_service.setup_command_runner import SetupCommandRunner
from sculptor.services.workspace_service.setup_command_runner import SetupStateChanged

_WAIT_TIMEOUT = 5.0


@pytest.fixture
def runner(test_root_concurrency_group: ConcurrencyGroup) -> SetupCommandRunner:
    return SetupCommandRunner(test_root_concurrency_group)


def _terminal_event(runner: SetupCommandRunner, workspace_id: str) -> Event:
    """Return an Event that fires when ``workspace_id`` reaches a terminal status.

    Subscribes a state observer so we can replace polling with a wait().
    """
    fired = Event()

    def _observe(event: SetupStateChanged) -> None:
        if event.workspace_id == workspace_id and event.status not in ("running", "pending"):
            fired.set()

    runner.add_state_observer(_observe)
    return fired


def _wait_for_terminal(runner: SetupCommandRunner, workspace_id: str, event: Event) -> None:
    if runner.get_state(workspace_id) is not None and event.is_set():
        return
    assert event.wait(timeout=_WAIT_TIMEOUT), f"setup did not reach terminal state for {workspace_id}"


def test_provider_returns_none_when_no_slot(runner: SetupCommandRunner) -> None:
    provider = DefaultSetupStateProvider(runner, "missing")
    assert provider.get_reminder_state() is None


def test_provider_returns_none_on_succeeded(runner: SetupCommandRunner, tmp_path: Path) -> None:
    def _runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        on_pid: Callable[[int], None],
        _shutdown: ReadOnlyEvent,
    ) -> int:
        on_pid(123)
        return 0

    terminal = _terminal_event(runner, "ws")
    runner.start("ws", "echo ok", _runner, Event(), tmp_path, MagicMock())
    _wait_for_terminal(runner, "ws", terminal)
    provider = DefaultSetupStateProvider(runner, "ws")
    assert provider.get_reminder_state() is None


def test_provider_returns_failed_on_failed_status(runner: SetupCommandRunner, tmp_path: Path) -> None:
    def _runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        on_pid: Callable[[int], None],
        _shutdown: ReadOnlyEvent,
    ) -> int:
        on_pid(456)
        return 2

    terminal = _terminal_event(runner, "ws")
    runner.start("ws", "do-broken-thing", _runner, Event(), tmp_path, MagicMock())
    _wait_for_terminal(runner, "ws", terminal)
    provider = DefaultSetupStateProvider(runner, "ws")
    result = provider.get_reminder_state()
    assert isinstance(result, FailedSetup)
    assert result.command == "do-broken-thing"
    assert result.exit_code == 2
    assert result.log_path == str(tmp_path / LOG_FILENAME)


def test_provider_blocks_until_pid_recorded(runner: SetupCommandRunner, tmp_path: Path) -> None:
    # The worker waits on ``release`` before it reports its PID, and again on
    # ``finish`` after reporting it. The test uses these explicit gates so we
    # never have to time.sleep() to give the provider a chance to observe state.
    release = Event()
    finish = Event()
    inside = Event()

    def _runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        on_pid: Callable[[int], None],
        _shutdown: ReadOnlyEvent,
    ) -> int:
        inside.set()
        assert release.wait(timeout=_WAIT_TIMEOUT)
        on_pid(789)
        assert finish.wait(timeout=_WAIT_TIMEOUT)
        return 0

    terminal = _terminal_event(runner, "ws")
    runner.start("ws", "long-command", _runner, Event(), tmp_path, MagicMock())
    assert inside.wait(timeout=_WAIT_TIMEOUT)
    provider = DefaultSetupStateProvider(runner, "ws")

    result_holder: list[object] = []
    provider_done = Event()

    def _call_provider() -> None:
        try:
            result_holder.append(provider.get_reminder_state())
        finally:
            provider_done.set()

    thread = threading.Thread(target=_call_provider, daemon=True)
    thread.start()
    # The provider must still be blocked on wait_for_pid because we have not
    # released the worker to call on_pid yet.
    assert not provider_done.is_set()

    release.set()
    assert provider_done.wait(timeout=_WAIT_TIMEOUT)
    thread.join(timeout=_WAIT_TIMEOUT)
    assert not thread.is_alive()
    assert len(result_holder) == 1
    result = result_holder[0]
    assert isinstance(result, RunningSetup)
    assert result.command == "long-command"
    assert result.pid == 789
    assert result.log_path == str(tmp_path / LOG_FILENAME)

    finish.set()
    _wait_for_terminal(runner, "ws", terminal)


def test_provider_returns_none_when_running_slot_is_stuck(
    runner: SetupCommandRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hand-craft a slot stuck in ``running`` with no worker thread to release
    ``pid_ready``. The provider must give up after the configured timeout and
    return ``None`` instead of blocking the agent's first message indefinitely.
    """
    monkeypatch.setattr(
        "sculptor.services.workspace_service.setup_command_runner.PROVIDER_WAIT_FOR_PID_TIMEOUT_SECONDS",
        0.1,
    )
    slot = RunnerSlot("ws")
    slot.command = "stuck-command"
    slot.status = "running"
    slot.state_dir = tmp_path
    # pid_ready intentionally not set; no worker thread will ever set it.
    runner._slots["ws"] = slot

    provider = DefaultSetupStateProvider(runner, "ws")
    start = time.monotonic()
    result = provider.get_reminder_state()
    elapsed = time.monotonic() - start
    assert result is None
    assert elapsed < 5.0, f"provider blocked for {elapsed:.2f}s; expected timely fallback"


def test_provider_recovers_when_setup_completes_during_wait(runner: SetupCommandRunner, tmp_path: Path) -> None:
    # subprocess_runner never calls on_pid and returns non-zero immediately.
    def _runner(
        _command: str,
        _on_chunk: Callable[[bytes], None],
        _on_pid: Callable[[int], None],
        _shutdown: ReadOnlyEvent,
    ) -> int:
        return 3

    terminal = _terminal_event(runner, "ws")
    runner.start("ws", "instant-fail", _runner, Event(), tmp_path, MagicMock())
    _wait_for_terminal(runner, "ws", terminal)
    provider = DefaultSetupStateProvider(runner, "ws")
    result = provider.get_reminder_state()
    assert isinstance(result, FailedSetup)
    assert result.command == "instant-fail"
    assert result.exit_code == 3
