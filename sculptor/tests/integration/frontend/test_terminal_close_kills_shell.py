"""End-to-end UI test for the terminal-close kill path.

Drives the real frontend in a real browser via Playwright:

1. Opens a workspace, opens the terminal panel.
2. Runs ``echo "PID:$$"`` in the terminal and reads the shell pid out of
   the xterm buffer.
3. Confirms the shell process is alive on the host via ``os.kill(pid, 0)``.
4. Adds a second terminal tab (so closing the first doesn't trigger the
   "last tab => create a fresh replacement" path, which would mask whether
   close actually killed the original shell).
5. Clicks the X close button on the first tab.
6. Polls ``os.kill(pid, 0)`` on the host until it raises
   ``ProcessLookupError`` (or fails the test on timeout) -- proves the
   shell process was actually killed, not just disconnected.
7. Runs a fresh command in the surviving tab to confirm the terminal panel
   is still healthy after a close.

The shell pid lives on the host (everything is in the same process tree)
so this also implicitly exercises whichever pty implementation
LocalTerminalManager is using (currently SpawnedPtyProcess). No code
changes needed here when the underlying pty class swaps.
"""

import os
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from sculptor.testing.elements.terminal import add_terminal
from sculptor.testing.elements.terminal import get_tab_close_button
from sculptor.testing.elements.terminal import get_terminal_tabs
from sculptor.testing.elements.terminal import get_xterm_buffer_text
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import run_command_in_active_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_buffer_nonempty
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _read_shell_pid_from_active_terminal(page, baseline_pids: set[int]) -> int:
    """Type ``echo "PID:$$"`` into the active terminal, return its shell pid.

    The typed command shows up as the literal string ``PID:$$`` in the
    buffer (the shell expands ``$$`` only when it executes), so the regex
    ``PID:(\\d+)`` only matches the output line.

    ``baseline_pids`` is the set of pids we have already seen on previous
    calls; this lets us ignore stale PID lines that survived a tab switch
    in the shared xterm buffer and only return a freshly emitted one.

    Feeds input via ``xterm.paste(...)`` (which writes directly to the
    terminal's input stream) rather than synthetic keyboard events.
    Keyboard-based typing drops the first 1-2 chars on a freshly mounted
    xterm because the helper textarea's focus race; paste sidesteps that
    entirely. ``window.__xterm`` is the currently active xterm, so this
    works for both the initial tab and any newly added tab.
    """
    run_command_in_active_terminal(page, 'echo "PID:$$"')
    try:
        result = page.wait_for_function(
            """(baselinePids) => {
                const xterm = window.__xterm;
                if (!xterm) return null;
                const buffer = xterm.buffer.active;
                const lines = [];
                for (let i = 0; i <= buffer.baseY + buffer.cursorY; i++) {
                    const line = buffer.getLine(i);
                    if (line) lines.push(line.translateToString(true));
                }
                const text = lines.join('\\n');
                const re = /PID:(\\d+)/g;
                let match;
                while ((match = re.exec(text)) !== null) {
                    const pid = parseInt(match[1]);
                    if (!baselinePids.includes(pid)) return pid;
                }
                return null;
            }""",
            arg=list(baseline_pids),
        )
        return result.json_value()
    except PlaywrightTimeoutError:
        buffer_text = get_xterm_buffer_text(page)
        raise AssertionError(f"never saw fresh PID marker; buffer was:\n{buffer_text!r}")


def _wait_for_dead(page, pid: int, timeout: float = 3.0) -> bool:
    """Return True once ``os.kill(pid, 0)`` raises ProcessLookupError.

    Unlike the HTTP test, this has to wait for the frontend's
    fire-and-forget DELETE to round-trip plus the backend's manager.stop()
    (which can spend up to ~2s sending SIGTERM and waiting before SIGKILL),
    so the overall timeout is wider than for the HTTP path. 50ms ticks
    keep the post-kill detection snappy.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        page.wait_for_timeout(50)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
    return False


@user_story("to close a terminal tab and have the backend kill the shell process, not just disconnect")
def test_close_terminal_tab_kills_shell_process(sculptor_instance_: SculptorInstance) -> None:
    """Clicking X on a terminal tab destroys the shell on the backend.

    Distinguishes the "explicit close" path from the pre-existing
    "WebSocket disconnect preserves the pty" behavior.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    # Read the first tab's shell pid from inside the terminal.
    first_pid = _read_shell_pid_from_active_terminal(page, baseline_pids=set())
    assert first_pid > 0
    # Sanity check: the shell is reachable on the host.
    os.kill(first_pid, 0)

    # Add a second tab. We close the first (non-active) tab so that:
    # 1. The "last tab => create a fresh replacement" branch in
    #    handleCloseTerminal doesn't fire (which would mask the close).
    # 2. After the close, we can run a command in the surviving second
    #    tab to prove the panel is still healthy.
    add_terminal(page)
    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(2)

    # In the section shell only the active panel mounts, so adding the second tab
    # unmounts the first terminal's xterm and mounts a fresh one (now the active
    # window.__xterm). Wait for that new xterm to actually connect and render its
    # shell prompt before typing into it — otherwise the PID echo can be dropped
    # on a not-yet-connected terminal and the read below times out.
    wait_for_xterm_buffer_nonempty(page)

    # The second tab is active by default after add. Capture its pid too
    # so we can prove ONLY the first tab's shell was killed.
    second_pid = _read_shell_pid_from_active_terminal(page, baseline_pids={first_pid})
    assert second_pid > 0 and second_pid != first_pid

    # Close the FIRST tab (index 0) — explicitly not the active one, so
    # we can keep typing in the second tab afterward.
    first_tab = terminal_tabs.first
    close_button = get_tab_close_button(first_tab)
    close_button.click()

    # Only the second tab remains.
    expect(terminal_tabs).to_have_count(1)

    # The first tab's shell pid should be gone within a deadline. The
    # frontend's DELETE call is fire-and-forget; the backend has to
    # receive it, look up the manager, and SIGTERM the shell. 10s is
    # generous.
    assert _wait_for_dead(page, first_pid), (
        f"first tab's shell pid {first_pid} still alive after close. "
        + "DELETE /api/v1/workspaces/.../terminal/0 did not kill the shell."
    )

    # The second tab's shell must NOT be affected -- it should still be
    # alive and responsive.
    os.kill(second_pid, 0)
    # Feed via xterm.paste -- same rationale as _read_shell_pid_from_active_terminal.
    run_command_in_active_terminal(page, 'echo "STILL_ALIVE_xyz"')
    wait_for_xterm_substring(page, "STILL_ALIVE_xyz")
