"""Tests for error resilience when the Claude CLI misbehaves.

Covers five failure modes:
1. Non-JSON / non-UTF8 output (broken Anthropic API)
2. Non-responsive process (hangs forever, no output)
3. Stdin backpressure (process ignores stdin, pipe buffer fills)
4. Process leak after error response (process not terminated after error)
5. Successful response + slow-to-exit process causes spurious error
"""

import os
import signal
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stop_agent(chat_panel: PlaywrightChatPanelElement) -> None:
    """Click the stop button and wait for the agent to stop."""
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible()
    stop_button.click()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()


# ---------------------------------------------------------------------------
# 1. Non-JSON output
# ---------------------------------------------------------------------------


@user_story("to see the agent recover gracefully when the Anthropic API returns garbage")
def test_garbage_output_does_not_crash_ui(sculptor_instance_: SculptorInstance) -> None:
    """When the CLI emits non-JSON output, the agent should skip the bad line,
    show a warning, and remain usable — not crash into an error state."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:emit_garbage `{"text": "Before the garbage"}`',
    )
    chat_panel = task_page.get_chat_panel()

    # The agent turn should finish (not hang).
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # The valid text that was emitted before the garbage should be visible.
    expect(chat_panel.get_messages().last).to_contain_text("Before the garbage")

    # There should be NO error block — the agent should not crash.
    error_block = chat_panel.get_error_block()
    expect(error_block).to_have_count(0)

    # The agent should still be usable — send a follow-up message.
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Recovery after garbage"}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_messages().last).to_contain_text("Recovery after garbage")


# ---------------------------------------------------------------------------
# 2. Hung / non-responsive process
# ---------------------------------------------------------------------------


@user_story("to stop a non-responsive agent via the Stop button")
def test_stop_kills_hung_process(sculptor_instance_: SculptorInstance) -> None:
    """When the CLI hangs and produces no output, the Stop button should
    terminate the process and the UI should recover cleanly."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:hang `{"seconds": 3600}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The thinking indicator should be visible while the agent is hung.
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Click Stop — this sends a stdin interrupt first, then escalates to SIGTERM.
    _stop_agent(chat_panel)

    # The thinking indicator should disappear after stop.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # The UI should be in a usable state — verify we can send a follow-up.
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Recovery after hang"}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # Verify the follow-up message appears.
    messages = chat_panel.get_messages()
    expect(messages.last).to_contain_text("Recovery after hang")


# ---------------------------------------------------------------------------
# 3. Stdin backpressure
# ---------------------------------------------------------------------------


@user_story("to stop an agent that ignores stdin without the UI freezing")
def test_stdin_backpressure_does_not_block_stop(sculptor_instance_: SculptorInstance) -> None:
    """When the CLI never reads stdin, writing a follow-up message or interrupt
    could fill the pipe buffer and block.  The queue-based stdin writer should
    prevent this from freezing the event loop, and Stop should still work."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:ignore_stdin `{"text": "I will ignore stdin", "seconds": 60}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the response text to appear (ignore_stdin emits a response
    # immediately, then blocks without reading stdin).
    expect(chat_panel.get_messages().last).to_contain_text("I will ignore stdin")

    # The thinking indicator should still be visible because the process
    # hasn't exited yet (it's sleeping, ignoring stdin).
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Click Stop — this should work even though the process isn't reading stdin.
    # The queue-based writer handles the write without blocking, and the
    # interrupt escalates to SIGTERM.
    _stop_agent(chat_panel)

    # Verify we can send a follow-up (UI is not frozen).
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Recovery after backpressure"}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_messages().last).to_contain_text("Recovery after backpressure")


# ---------------------------------------------------------------------------
# 4. Process leak after error response
# ---------------------------------------------------------------------------


def _read_pid_file(pid_path: Path, page: Page, timeout: float = 10.0) -> int:
    """Wait for the PID file to appear and return the PID.

    The FakeClaude ``error_then_hang`` handler writes its PID to a file so the
    test can verify whether the process was terminated.  The file may not exist
    immediately after ``start_task_and_wait_for_ready`` returns, so we poll
    using Playwright's wait_for_timeout to avoid the time.sleep ratchet.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pid_path.exists():
            text = pid_path.read_text().strip()
            if text:
                return int(text)
        page.wait_for_timeout(200)
    raise FileNotFoundError(f"PID file {pid_path} was not created within {timeout}s")


def _is_process_alive(pid: int) -> bool:
    """Check whether a process is still running (signal 0 probe)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_process(pid: int) -> None:
    """Best-effort kill of a leaked process."""
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


@user_story("to have the CLI process terminated after the agent reports an error")
def test_error_response_terminates_process(sculptor_instance_: SculptorInstance) -> None:
    """When the CLI emits an error end message (is_error=True), the process
    manager should still terminate the underlying process. Verifies that the
    process is dead after the error turn completes."""
    # Use a temp file for the PID because the FakeClaude process runs in
    # a cloned workspace directory, not the project_path visible to the test.
    pid_path = Path(tempfile.mktemp(prefix="error_then_hang_", suffix=".pid"))
    leaked_pid: int | None = None

    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=sculptor_instance_.page,
            prompt=f'fake_claude:error_then_hang `{{"seconds": 300, "pid_file": "{pid_path}"}}`',
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        # The error end message surfaces as an error in the UI.
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

        leaked_pid = _read_pid_file(pid_path, sculptor_instance_.page)

        # Wait for the process manager to run cleanup. Alpha's STATUS_PILL_STOP
        # disappears as soon as the agent goes "not cancellable", which can fire
        # while the subprocess is still in cleanup — so poll for actual process
        # termination rather than relying on a fixed sleep. The polled state is
        # an OS process, not the browser DOM, so use ``time.sleep`` instead of
        # ``page.wait_for_timeout``.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and _is_process_alive(leaked_pid):
            time.sleep(0.2)

        assert not _is_process_alive(leaked_pid), (
            f"FakeClaude process (PID {leaked_pid}) is still alive after the turn ended with an error — process was not terminated."
        )
    finally:
        if leaked_pid is not None:
            _kill_process(leaked_pid)
        pid_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 5. Successful response + slow-to-exit process
# ---------------------------------------------------------------------------


@user_story("to see a successful response even when the CLI process is slow to exit")
def test_slow_exit_after_success_does_not_show_error(sculptor_instance_: SculptorInstance) -> None:
    """When the CLI emits a complete, successful response but the process is
    slow to exit (e.g. a backgrounded child keeps it alive), the response
    should still appear normally with no error, and follow-up turns should work."""
    pid_path = Path(tempfile.mktemp(prefix="succeed_then_hang_", suffix=".pid"))
    hung_pid: int | None = None

    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=sculptor_instance_.page,
            prompt=(
                f'fake_claude:succeed_then_hang `{{"text": "All done!", "seconds": 300, "pid_file": "{pid_path}"}}`'
            ),
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

        hung_pid = _read_pid_file(pid_path, sculptor_instance_.page)

        # The successful response text should be visible.
        expect(chat_panel.get_messages().last).to_contain_text("All done!")

        # No error block should appear — the non-zero exit code from
        # force-terminating the slow process is not a real failure.
        error_block = chat_panel.get_error_block()
        expect(error_block).to_have_count(0)

        # The agent should still be usable for follow-up turns.
        send_chat_message(chat_panel, 'fake_claude:text `{"text": "Follow-up works"}`')
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
        expect(chat_panel.get_messages().last).to_contain_text("Follow-up works")
    finally:
        if hung_pid is not None:
            _kill_process(hung_pid)
        pid_path.unlink(missing_ok=True)
