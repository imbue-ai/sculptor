"""Integration test for the terminal reconnecting after its WebSocket drops.

Drives the real reconnect path by capturing and closing the live terminal
socket via the ``terminal_socket_capture`` fixture (Playwright cannot otherwise
drop an established loopback socket). A literal sleep-induced 1006 close is
covered by the unit test; here we exercise the end-to-end recovery against the
real backend, which keeps the PTY alive across the disconnect and replays its
buffer on reconnect.
"""

from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import run_command_in_active_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.terminal_socket_mock import TerminalSocketCapture
from sculptor.testing.terminal_socket_mock import terminal_socket_capture as terminal_socket_capture  # noqa: F401
from sculptor.testing.user_stories import user_story

# A recoverable application close code (3000-4999) that is not one of the
# non-retryable codes (1000 normal / 4401 unauthorized), so the terminal retries.
_RECOVERABLE_CLOSE_CODE = 4500


@user_story("to keep using a terminal after its connection drops and reconnects")
def test_terminal_reconnects_after_socket_drop(
    sculptor_instance_: SculptorInstance,
    terminal_socket_capture: TerminalSocketCapture,  # noqa: F811
) -> None:
    """A dropped terminal socket reconnects on its own and the terminal stays usable.

    Steps:
    1. Open a terminal and confirm it works.
    2. Close the live socket with a recoverable code (as a sleep/restart would).
    3. Assert the terminal reconnects (a new socket) and runs a fresh command.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)
    terminal_socket_capture.wait_for_connection()

    # The marker is assembled from a shell variable so the contiguous token
    # appears only in the command's OUTPUT, never in the echoed command line.
    run_command_in_active_terminal(page, 'm=RECON; echo "${m}_BEFORE_OK"')
    wait_for_xterm_substring(page, "RECON_BEFORE_OK")

    sockets_before = terminal_socket_capture.socket_count()

    # Drop the live socket the way a machine sleep / backend restart does.
    terminal_socket_capture.drop_latest(code=_RECOVERABLE_CLOSE_CODE)

    # The frontend reconnects after a short delay; wait for a fresh socket and for
    # it to finish opening (keystrokes sent before OPEN are dropped, not resent),
    # then confirm the reconnected terminal runs a new command (the backend
    # replayed the buffered session, so the shell is live again).
    terminal_socket_capture.wait_for_additional_connection(since=sockets_before)
    terminal_socket_capture.wait_for_latest_open()

    run_command_in_active_terminal(page, 'm=RECON; echo "${m}_AFTER_OK"')
    wait_for_xterm_substring(page, "RECON_AFTER_OK")
