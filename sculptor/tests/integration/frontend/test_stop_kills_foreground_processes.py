"""Test that Stop kills foreground subprocesses spawned by the agent.

When the user clicks Stop, any subprocess the agent spawned in the
foreground (e.g. a long-running Bash tool call) must be terminated, not
left running as an orphan.

See SCU-211 (kill foreground processes on stop).
"""

import os
import signal
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _click_stop(chat_panel: PlaywrightChatPanelElement) -> None:
    """Click Stop. Does NOT wait for the thinking indicator to clear — the bug
    under test is that the indicator may settle (agent CLI is killed) while a
    leaked subprocess keeps running."""
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible()
    stop_button.click()


def _read_pid_file(pid_path: Path, page: Page, timeout: float = 15.0) -> int:
    """Wait for the PID file to appear and return the PID.

    Polls via ``page.wait_for_timeout`` (rather than ``time.sleep``) since the
    integration-test time.sleep ratchet reserves the latter for OS-process
    state polling.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pid_path.exists():
            text = pid_path.read_text().strip()
            if text:
                return int(text)
        page.wait_for_timeout(100)
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


@user_story("to have foreground subprocesses killed when I click Stop")
def test_stop_kills_foreground_subprocess(sculptor_instance_: SculptorInstance) -> None:
    """Clicking Stop while the agent is blocked on a foreground subprocess
    must kill the subprocess, not just the agent CLI.

    Uses ``fake_claude:spawn_subprocess_and_hang`` to model the realistic
    leak: the agent spawns a subprocess via ``Popen`` (no auto-cleanup) and
    then hangs. When Sculptor sends SIGTERM/SIGKILL to the agent CLI alone,
    the subprocess is orphaned and survives indefinitely.

    The fix is process-group isolation (``start_new_session=True`` at spawn,
    ``os.killpg`` on shutdown) so the kill cascades to all descendants.
    """
    pid_path = Path(tempfile.mktemp(prefix="scu211_foreground_", suffix=".pid"))
    leaked_pid: int | None = None

    try:
        args_json = f'{{"pid_file": "{pid_path}", "child_seconds": 300, "hang_seconds": 60}}'
        prompt = f"fake_claude:spawn_subprocess_and_hang `{args_json}`"

        task_page = start_task_and_wait_for_ready(
            sculptor_page=sculptor_instance_.page,
            prompt=prompt,
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=10_000)

        leaked_pid = _read_pid_file(pid_path, sculptor_instance_.page)
        assert _is_process_alive(leaked_pid), (
            f"Subprocess (PID {leaked_pid}) should be alive immediately after writing its PID"
        )

        _click_stop(chat_panel)

        # The subprocess must die within 20s of Stop. Without the fix, the
        # agent CLI dies (via SIGTERM/SIGKILL on its PID) but the orphaned
        # subprocess keeps running until its own sleep finishes (300s).
        # Polled state is an OS process, not the browser DOM, so use
        # ``time.sleep`` instead of ``page.wait_for_timeout``.
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and _is_process_alive(leaked_pid):
            time.sleep(0.2)

        assert not _is_process_alive(leaked_pid), (
            f"Foreground subprocess (PID {leaked_pid}) is still alive 20s after Stop — the agent CLI was killed but its child subprocess was orphaned. See SCU-211."
        )
    finally:
        if leaked_pid is not None:
            _kill_process(leaked_pid)
        pid_path.unlink(missing_ok=True)
