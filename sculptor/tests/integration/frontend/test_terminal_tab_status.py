"""Integration tests for the terminal tab connection-state indicator.

These exercise the real frontend chain — a terminal WebSocket closing drives
``useTerminal``'s status, which surfaces as a dot on the terminal tab — by
capturing and closing the live socket via the ``terminal_socket_capture``
fixture (Playwright cannot otherwise drop an established loopback socket).
"""

from playwright.sync_api import expect

from sculptor.testing.elements.terminal import get_terminal_tab_status_indicator
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import run_command_in_active_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.terminal_socket_mock import TerminalSocketCapture
from sculptor.testing.terminal_socket_mock import terminal_socket_capture as terminal_socket_capture  # noqa: F401
from sculptor.testing.user_stories import user_story

# Application close codes (3000-4999) used to drive the reconnect logic. 4500 is
# a recoverable drop (retried); 4401 mirrors the backend's rejected-session-token
# close, which is not retried.
_RECOVERABLE_CLOSE_CODE = 4500
_UNAUTHORIZED_CLOSE_CODE = 4401


@user_story("to see when a terminal is reconnecting and have it recover on its own")
def test_terminal_tab_shows_reconnecting_then_recovers(
    sculptor_instance_: SculptorInstance,
    terminal_socket_capture: TerminalSocketCapture,  # noqa: F811
) -> None:
    """A recoverable drop flags the tab as reconnecting, then clears once it recovers.

    Steps:
    1. Open a terminal and confirm it works.
    2. Close the live socket with a recoverable code.
    3. Assert the tab shows the "reconnecting" indicator.
    4. Assert the indicator clears and the terminal runs a fresh command.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)
    terminal_socket_capture.wait_for_connection()

    # The marker is assembled from a shell variable so the contiguous token
    # appears only in the command's OUTPUT, never in the echoed command line.
    run_command_in_active_terminal(page, 'm=TABSTAT; echo "${m}_BEFORE_OK"')
    wait_for_xterm_substring(page, "TABSTAT_BEFORE_OK")

    # Drop the live socket: the tab must flag "reconnecting". The status is set
    # immediately and held for the 2s retry delay, so it is reliably observable.
    terminal_socket_capture.drop_latest(code=_RECOVERABLE_CLOSE_CODE)

    indicator = get_terminal_tab_status_indicator(page)
    expect(indicator).to_have_attribute("data-status", "reconnecting")

    # The backend keeps the PTY alive and replays its buffer on reconnect, so the
    # indicator clears (status back to connected) and the terminal is usable again.
    # Allow the harness's standard 30s — reconnect + replay can run long under CI load.
    expect(indicator).to_have_count(0, timeout=30_000)
    run_command_in_active_terminal(page, 'm=TABSTAT; echo "${m}_AFTER_OK"')
    wait_for_xterm_substring(page, "TABSTAT_AFTER_OK")


@user_story("to see when a terminal's connection has failed and won't recover")
def test_terminal_tab_shows_disconnected_on_unrecoverable_close(
    sculptor_instance_: SculptorInstance,
    terminal_socket_capture: TerminalSocketCapture,  # noqa: F811
) -> None:
    """An unrecoverable close (rejected token) flags the tab as disconnected, not reconnecting."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)
    terminal_socket_capture.wait_for_connection()

    # A 4401 close is not retried, so the tab shows the stable "disconnected"
    # state rather than spinning on reconnect.
    terminal_socket_capture.drop_latest(code=_UNAUTHORIZED_CLOSE_CODE)

    indicator = get_terminal_tab_status_indicator(page)
    expect(indicator).to_have_attribute("data-status", "disconnected")
