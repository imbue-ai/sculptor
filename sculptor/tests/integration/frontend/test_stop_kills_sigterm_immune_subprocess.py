"""Test that Stop kills a SIGTERM-ignoring foreground subprocess without crashing.

SCU-1340: when the agent CLI is blocked on a foreground subprocess that traps /
ignores SIGTERM (e.g. a Bash tool that spawned a GUI child), clicking Stop must
escalate SIGTERM → SIGKILL on the whole process group and reap the subprocess —
and must NOT crash the agent runner. Before the fix, ``interrupt_current_message``
raised out of the SIGTERM fallback (the worker thread stayed wedged inside the
subprocess wrapper's 30s shutdown wait), the task transitioned to FAILED, and the
SIGTERM-ignoring child was never killed.

See SCU-1340.
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
    """Click Stop without waiting for the indicator to clear — the bug under
    test is that Stop crashes / the subprocess survives."""
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


@user_story("to have a SIGTERM-ignoring subprocess killed by Stop without crashing the agent")
def test_stop_kills_sigterm_immune_subprocess_without_crashing(sculptor_instance_: SculptorInstance) -> None:
    """Clicking Stop while the agent is blocked on a SIGTERM-ignoring foreground
    subprocess must (a) reap that subprocess via SIGKILL on the process group and
    (b) NOT crash the agent runner.

    ``fake_claude:spawn_sigterm_immune_subprocess_and_hang`` makes both the fake
    agent CLI and its foreground child ignore SIGTERM, so Stop's SIGTERM phase is
    a no-op and only the SIGKILL escalation can reap them — exactly the SCU-1340
    path. Before the fix, Stop raised TimeoutError out of
    ``interrupt_current_message`` (task → FAILED, error block shown) and the child
    was orphaned.
    """
    pid_path = Path(tempfile.mktemp(prefix="scu1340_immune_", suffix=".pid"))
    leaked_pid: int | None = None

    try:
        args_json = f'{{"pid_file": "{pid_path}", "hang_seconds": 60}}'
        prompt = f"fake_claude:spawn_sigterm_immune_subprocess_and_hang `{args_json}`"

        task_page = start_task_and_wait_for_ready(
            sculptor_page=sculptor_instance_.page,
            prompt=prompt,
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        expect(chat_panel.get_thinking_indicator()).to_be_visible()

        leaked_pid = _read_pid_file(pid_path, sculptor_instance_.page)
        assert _is_process_alive(leaked_pid), (
            f"Subprocess (PID {leaked_pid}) should be alive immediately after writing its PID"
        )

        _click_stop(chat_panel)

        # The subprocess must die within 15s of Stop. The phased escalation
        # SIGKILLs the process group ~9s after the stdin interrupt fails. Without
        # the fix, Stop crashed before any SIGKILL reached the child, so it
        # survived until its own loop was externally killed. Polled state is an
        # OS process, not the browser DOM, so use ``time.sleep``.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and _is_process_alive(leaked_pid):
            time.sleep(0.2)

        assert not _is_process_alive(leaked_pid), (
            f"SIGTERM-ignoring subprocess (PID {leaked_pid}) is still alive 15s after Stop — the SIGKILL escalation to the process group did not reach it. See SCU-1340."
        )

        # Stop is user-initiated and must never crash the agent runner: no error
        # block, and the agent settles out of its busy state. Uses the harness's
        # default 30s expect() timeout (the agent settles ~9s after Stop).
        expect(chat_panel.get_error_block()).not_to_be_visible()
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    finally:
        if leaked_pid is not None:
            _kill_process(leaked_pid)
        pid_path.unlink(missing_ok=True)
