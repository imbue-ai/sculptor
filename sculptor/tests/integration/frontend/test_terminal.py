"""Integration tests for the terminal panel.

Tests cover:
- WebSocket connection management (no duplicate connections)
- Modifier key combinations (Opt+Left for word navigation, Ctrl+C for interrupt)
- Multi-terminal tabs (add, switch, close)
- DECRQM escape sequence handling (xterm.js write buffer survives mode queries)
- Shell exit handling (Ctrl+D / exit command shows exit message)
- Cursor position report (CPR) filtering on tab switch
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import type_with_delay
from sculptor.testing.elements.terminal import get_add_terminal_button
from sculptor.testing.elements.terminal import get_terminal_panel_icon
from sculptor.testing.elements.terminal import get_terminal_starting_text
from sculptor.testing.elements.terminal import get_terminal_tabs
from sculptor.testing.elements.terminal import get_terminal_textarea
from sculptor.testing.elements.terminal import get_xterm_active_line
from sculptor.testing.elements.terminal import get_xterm_buffer_text
from sculptor.testing.elements.terminal import get_xterm_cursor_row
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import wait_for_xterm_buffer_nonempty
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to use the terminal without duplicated input/output")
def test_terminal_panel_creates_single_websocket_connection(sculptor_instance_: SculptorInstance) -> None:
    """Opening the terminal panel should create exactly one WebSocket connection.

    Steps:
    1. Create a workspace and wait for it to be ready (terminal available)
    2. Set up a WebSocket connection counter for terminal endpoints
    3. Open the terminal panel via its sidebar icon
    4. Wait for connections to stabilize
    5. Assert exactly one WebSocket connection was made to the terminal endpoint
    """
    page = sculptor_instance_.page

    # Create a workspace and wait for it to be ready
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Wait for the workspace page to load — the terminal sidebar icon only
    # exists on the workspace page (not the add workspace page).
    terminal_icon = get_terminal_panel_icon(page)
    expect(terminal_icon).to_be_visible()

    # If the terminal panel is already open (from a previous test's localStorage
    # state), close it first so we can track WebSocket connections from scratch.
    add_button = get_add_terminal_button(page)
    starting_text = get_terminal_starting_text(page)
    panel_content = add_button.or_(starting_text)

    if panel_content.is_visible():
        terminal_icon.click()
        expect(panel_content).not_to_be_visible()
        # Allow time for the terminal component to unmount and close its WebSocket.
        page.wait_for_timeout(1000)

    # Track WebSocket connections to the terminal endpoint.
    # Register AFTER navigation but BEFORE opening the terminal panel so we
    # capture the connections that fire when the panel mounts.
    terminal_ws_connections: list[str] = []

    def on_websocket(ws):
        if "/terminal/" in ws.url and ws.url.endswith("/ws"):
            terminal_ws_connections.append(ws.url)

    page.on("websocket", on_websocket)

    # Open the terminal panel by clicking its sidebar icon.
    terminal_icon.click()

    # Wait for the add-terminal button to appear — this confirms the panel is
    # mounted and the tab bar is rendered.  First confirm the panel zone
    # opened (shows either "Starting terminal..." or the tab bar), then wait
    # for the add button specifically (terminal component mounted).
    expect(panel_content).to_be_visible(timeout=10_000)
    expect(add_button).to_be_visible(timeout=60_000)

    # Wait for the shell prompt to render in the (single) connection's buffer.
    # A rendered prompt means the WebSocket connected and the mount/connect cycle
    # settled -- the bug's duplicate connection fires during that same cycle (the
    # async useEffect-cleanup race opens a second socket "shortly after the
    # first"), so by the time output lands, any duplicate would already have been
    # registered by the listener above. This replaces a blind fixed wait with a
    # signal tied to the connection actually coming up.
    wait_for_xterm_buffer_nonempty(page)

    assert len(terminal_ws_connections) == 1, (
        "Expected exactly 1 terminal WebSocket connection, but got"
        + f" {len(terminal_ws_connections)}."
        + f" URLs: {terminal_ws_connections}."
        + " Multiple connections cause duplicated input/output in the terminal."
    )


@user_story("to use keyboard shortcuts like Opt+Left to navigate by word in the terminal")
def test_opt_left_moves_cursor_back_by_word(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Opt+Left after typing two words should move the cursor back, not type ';3D'.

    Steps:
    1. Create a workspace and wait for the terminal to be available
    2. Open the terminal panel
    3. Type "hello world" (without pressing Enter)
    4. Press Alt+Left to move the cursor back one word
    5. Assert that ";3D" does NOT appear in the current line (the escape sequence
       should be interpreted as cursor movement, not echoed as literal text)
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    terminal_textarea = get_terminal_textarea(page)
    terminal_textarea.focus()

    # Type two words without pressing Enter.
    type_with_delay(terminal_textarea, "hello world", 50)
    wait_for_xterm_substring(page, "hello world")

    # Record cursor column before Opt+Left so we can wait for it to move.
    cursor_x_before = page.evaluate("() => window.__xterm?.buffer.active.cursorX ?? -1")

    # Press Opt+Left (Alt+Left) to move the cursor back by one word.
    terminal_textarea.press("Alt+ArrowLeft")

    # Wait for the cursor to move back (the keystroke has been processed).
    page.wait_for_function(
        "(beforeX) => { const x = window.__xterm; return x && x.buffer.active.cursorX < beforeX; }",
        arg=cursor_x_before,
    )

    # Read the current line from the xterm buffer. If the bug is present, it will
    # contain ";3D" (the tail of the CSI escape sequence \x1b[1;3D that leaked as
    # literal text). If Opt+Left worked correctly, the line still says "hello world"
    # with the cursor repositioned — no extra characters.
    active_line = get_xterm_active_line(page)

    assert ";3D" not in active_line, (
        "Opt+Left typed literal escape sequence characters instead of moving the cursor."
        + f" Terminal line content: {active_line!r}"
    )


@user_story("to use Ctrl+C to cancel the current terminal input")
def test_ctrl_c_cancels_input(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Ctrl+C after typing should cancel the input and move to a new prompt line.

    Steps:
    1. Create a workspace and wait for the terminal to be available
    2. Open the terminal panel
    3. Type "some partial input" (without pressing Enter)
    4. Press Ctrl+C to cancel
    5. Assert the cursor moved to a new line (cursorY advanced) — this confirms the
       shell received the SIGINT / ETX (0x03) and printed a fresh prompt rather than
       the Ctrl modifier being swallowed
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    terminal_textarea = get_terminal_textarea(page)
    terminal_textarea.focus()

    # Type some text without pressing Enter.
    type_with_delay(terminal_textarea, "some partial input", 50)
    wait_for_xterm_substring(page, "some partial input")

    # Record the cursor row before Ctrl+C.
    cursor_y_before = get_xterm_cursor_row(page)

    # Press Ctrl+C to cancel.
    terminal_textarea.press("Control+c")

    # Wait for the shell to print "^C" and advance to a new prompt line.
    page.wait_for_function(
        "(beforeY) => { const x = window.__xterm; return x && (x.buffer.active.cursorY + x.buffer.active.baseY) > beforeY; }",
        arg=cursor_y_before,
    )

    # The shell should have printed "^C" and moved to a new prompt line, so the
    # cursor row should be greater than before.
    cursor_y_after = get_xterm_cursor_row(page)

    assert cursor_y_after > cursor_y_before, (
        f"Ctrl+C did not produce a new prompt line. Cursor row stayed at {cursor_y_before}"
        + " (expected it to advance). The Ctrl modifier may have been swallowed."
    )


@user_story("to open multiple terminal sessions simultaneously")
def test_add_terminal_tab_creates_new_session(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the '+' button should create a second terminal tab with its own PTY.

    Steps:
    1. Create a workspace and open the terminal panel
    2. Verify exactly one terminal tab is present
    3. Click the '+' button to add a new terminal tab
    4. Verify two tabs exist and the second one is active
    5. Verify a new WebSocket connection was opened for the second terminal
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    # Verify initial state: one terminal tab.
    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(1)
    expect(terminal_tabs.first).to_have_text("Terminal 1")
    expect(terminal_tabs.first).to_have_attribute("aria-selected", "true")

    # Track new WebSocket connections to the terminal endpoint.
    new_terminal_ws_connections: list[str] = []

    def on_websocket(ws):
        if "/terminal/" in ws.url and ws.url.endswith("/ws"):
            new_terminal_ws_connections.append(ws.url)

    page.on("websocket", on_websocket)

    # Click the '+' button to add a second terminal tab.
    add_button = get_add_terminal_button(page)
    add_button.click()

    # Verify two tabs exist, with the second one now active.
    expect(terminal_tabs).to_have_count(2)
    expect(terminal_tabs.nth(1)).to_have_text("Terminal 2")
    expect(terminal_tabs.nth(1)).to_have_attribute("aria-selected", "true")

    # Wait for the new terminal's WebSocket to connect.
    page.wait_for_timeout(3000)

    assert len(new_terminal_ws_connections) == 1, (
        "Expected exactly 1 new WebSocket connection for the second terminal tab,"
        + f" but got {len(new_terminal_ws_connections)}."
        + f" URLs: {new_terminal_ws_connections}"
    )


@user_story("to close a terminal tab and have the UI switch to the nearest remaining tab")
def test_close_terminal_tab_switches_to_neighbor(sculptor_instance_: SculptorInstance) -> None:
    """Closing the active terminal tab should switch to the nearest remaining tab.

    Steps:
    1. Create a workspace and open the terminal panel
    2. Add a second terminal tab (becomes active)
    3. Close the active second tab
    4. Verify only the first tab remains and is active
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    # Add a second terminal tab.
    add_button = get_add_terminal_button(page)
    add_button.click()

    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(2)

    # Close the active second tab by clicking its close button.
    second_tab = terminal_tabs.nth(1)
    expect(second_tab).to_have_attribute("aria-selected", "true")
    close_button = second_tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()

    # Verify only the first tab remains and is active.
    expect(terminal_tabs).to_have_count(1)
    expect(terminal_tabs.first).to_have_text("Terminal 1")
    expect(terminal_tabs.first).to_have_attribute("aria-selected", "true")


@user_story("to see terminal tabs numbered starting from 1 even after closing earlier tabs")
def test_terminal_tab_reuses_lowest_available_number(sculptor_instance_: SculptorInstance) -> None:
    """Closing a terminal and adding a new one should reuse the lowest available number.

    Steps:
    1. Create a workspace and open the terminal panel ("Terminal 1")
    2. Add a second terminal tab ("Terminal 2")
    3. Close "Terminal 1"
    4. Add a new terminal tab — it should be named "Terminal 1", not "Terminal 3"
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    # Verify initial state: one tab labelled "Terminal 1".
    terminal_tabs = get_terminal_tabs(page)
    expect(terminal_tabs).to_have_count(1)
    expect(terminal_tabs.first).to_have_text("Terminal 1")

    # Add a second terminal tab.
    add_button = get_add_terminal_button(page)
    add_button.click()
    expect(terminal_tabs).to_have_count(2)
    expect(terminal_tabs.nth(1)).to_have_text("Terminal 2")

    # Close the first tab ("Terminal 1").
    first_tab = terminal_tabs.first
    first_tab.click()
    close_button = first_tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()

    # Only "Terminal 2" remains.
    expect(terminal_tabs).to_have_count(1)
    expect(terminal_tabs.first).to_have_text("Terminal 2")

    # Add another terminal — should reuse number 1, not increment to 3.
    add_button.click()
    expect(terminal_tabs).to_have_count(2)
    expect(terminal_tabs.nth(1)).to_have_text("Terminal 1")


@user_story("to use the terminal without SCULPTOR_API_PORT breaking `just start`")
def test_terminal_does_not_expose_sculptor_api_port(sculptor_instance_: SculptorInstance) -> None:
    """The terminal must not set SCULPTOR_API_PORT — it breaks `just start` from the terminal.

    SCULPTOR_API_PORT configures the port that Sculptor itself binds on at startup.
    If it leaks into terminal sessions, running `just start` from the terminal will
    attempt to start a new Sculptor instance on the already-bound port and fail.
    The sculpt CLI uses SCULPT_API_PORT instead, so SCULPTOR_API_PORT should never
    be present in the terminal environment.

    Steps:
    1. Create a workspace and wait for the terminal to be available
    2. Open the terminal panel
    3. Run a command that prints a marker depending on whether SCULPTOR_API_PORT is set
    4. Assert the marker indicates the variable is NOT set
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    terminal_textarea = get_terminal_textarea(page)
    terminal_textarea.focus()

    # Print a deterministic marker. If SCULPTOR_API_PORT is unset (correct),
    # the shell expands ${SCULPTOR_API_PORT:-NOT_SET} to "NOT_SET" and we see
    # "LEAK_CHECK:NOT_SET".  If it is set (the bug), we see e.g. "LEAK_CHECK:5050".
    type_with_delay(terminal_textarea, 'echo "LEAK_CHECK:${SCULPTOR_API_PORT:-NOT_SET}"', 30)
    terminal_textarea.press("Enter")
    wait_for_xterm_substring(page, "LEAK_CHECK:")

    buffer_text = get_xterm_buffer_text(page)

    assert "LEAK_CHECK:NOT_SET" in buffer_text, (
        "SCULPTOR_API_PORT should not be set in the terminal environment — "
        + "it breaks `just start` from the terminal because it controls the port "
        + "Sculptor binds on at startup. The sculpt CLI reads SCULPT_API_PORT instead. "
        + f"Terminal buffer:\n{buffer_text}"
    )


@user_story("to use neovim inside Sculptor's terminal")
def test_decrqm_does_not_kill_xterm_write_buffer(sculptor_instance_: SculptorInstance) -> None:
    """Sending a DECRQM escape sequence must not break subsequent terminal output.

    Regression test for neovim rendering failure.  Neovim sends a DECRQM
    private-mode query (``CSI ? 2026 $ p``) at startup to check for
    synchronized output support.  Without the ``patchXtermConstEnums`` Vite
    plugin, esbuild's minifier breaks xterm.js's ``requestMode()`` handler
    — the function contains a ``const enum`` compiled to
    ``let r; (P => ...)(r ||= {})``, and esbuild removes the ``let r;``
    declaration, causing a ``ReferenceError`` that permanently kills xterm's
    internal write buffer.  All subsequent terminal output is lost.

    Steps:
    1. Open the terminal panel and wait for xterm to be ready
    2. Run ``printf`` to emit the DECRQM escape sequence through the PTY
    3. Wait for the command to finish
    4. Type a separate ``echo`` command with a known marker
    5. Assert the marker appears in the xterm buffer, proving the write
       buffer survived the DECRQM processing

    The ``printf`` and ``echo`` are separate commands so they produce separate
    PTY reads and therefore separate ``xterm.write()`` calls.  If the write
    buffer died from the DECRQM in step 2, the echo output in step 4 will
    never be rendered.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    terminal_textarea = get_terminal_textarea(page)
    terminal_textarea.focus()

    # Run printf to emit DECRQM private-mode query for mode 2026.
    # \033[?2026$p  =  ESC [ ? 2026 $ p  (synchronized output mode query)
    #
    # This is the exact sequence neovim sends at startup that triggers
    # xterm.js's requestMode() handler.  Without the patchXtermConstEnums
    # Vite plugin, requestMode() throws ReferenceError (esbuild's minifier
    # removed the const-enum variable declarations) and permanently kills
    # the write buffer.
    type_with_delay(terminal_textarea, r"printf '\033[?2026$p'", 30)
    terminal_textarea.press("Enter")

    # Wait for the DECRQM command to complete.  The DECRQM response
    # (``ESC [ ? 2026 ; 2 $ y``) is a terminal-to-host reply that xterm.js
    # writes back to the PTY as input.  This means the response characters
    # (e.g. ``2026;2$y``) appear on bash's command line as if the user
    # typed them.  We must clear this stale input before typing the echo.
    page.wait_for_timeout(5000)

    # Press Ctrl+C to discard any DECRQM response characters that appeared
    # on the command line, then wait for a fresh prompt.
    terminal_textarea.press("Control+c")
    page.wait_for_timeout(1000)

    # Type a *separate* echo command.  This produces new PTY output that
    # arrives as a distinct xterm.write() call — if the write buffer is dead,
    # this output will never render.
    type_with_delay(terminal_textarea, "echo XTERM_WRITE_BUFFER_OK", 30)
    terminal_textarea.press("Enter")

    wait_for_xterm_substring(page, "XTERM_WRITE_BUFFER_OK")


@user_story("to see that the shell exited instead of getting a frozen terminal")
def test_ctrl_d_shows_process_exited_message(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Ctrl+D at an empty prompt should show a process-exited message, not freeze.

    Steps:
    1. Create a workspace and wait for the terminal to be available
    2. Open the terminal panel
    3. Press Ctrl+D to send EOF to the shell
    4. Assert that a "[Process exited]" message appears in the terminal buffer,
       confirming the exit was detected and communicated to the user
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    terminal_textarea = get_terminal_textarea(page)
    terminal_textarea.focus()

    # Press Ctrl+D to send EOF to the shell.
    terminal_textarea.press("Control+d")

    # Wait for the shell to exit and the exit message to appear.
    wait_for_xterm_substring(page, "[Process exited]")


@user_story("to run interactive CLIs like `gh auth login` that query the terminal")
def test_solicited_cursor_position_report_reaches_program(sculptor_instance_: SculptorInstance) -> None:
    """A program that queries the cursor and blocks reading the reply must receive it.

    This is the root cause of SCU-1249 (`gh auth login` hangs): gh (via the
    survey library) writes a DSR cursor-position query (ESC[6n) and then blocks
    reading stdin for the CPR response (ESC[row;colR).  xterm.js generates the
    response, but the frontend's query-response filter used to drop *every*
    response — including solicited ones — so gh never received the reply and
    hung, ignoring keystrokes and Ctrl+C (it was stuck in its low-level CPR read
    loop, not its normal key handler).

    We reproduce the mechanism without gh: a short Python program puts the
    terminal in raw mode, emits ESC[6n, and blocks reading the first bytes of
    the reply, then prints a success marker.  With the bug the read never
    returns (the marker never appears); with the fix the reply is forwarded and
    the marker prints.

    The success marker is *assembled at runtime* (``'CPR'+'GOTREPLY'+...``) so
    that the contiguous string ``CPRGOTREPLY`` can only appear in the program's
    real output — never in the echoed command line, where it is split across
    string-concatenation operators.  (Asserting on a literal marker would pass
    spuriously: the echoed command contains the literal.)

    Steps:
    1. Create a workspace and open the terminal panel
    2. Type a Python one-liner that emits a DSR query and blocks reading the CPR
    3. Assert the runtime-assembled marker (CPRGOTREPLY) appears in the buffer
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    terminal_textarea = get_terminal_textarea(page)
    terminal_textarea.focus()

    # Python (always present) avoids depending on the login shell being bash vs
    # zsh for a `read -d`-style char read.  tty.setraw() is required because the
    # CPR reply has no newline and would otherwise sit unread in the canonical-
    # mode line buffer forever.  read(4) blocks until the first 4 bytes of the
    # reply arrive (the shortest CPR, ESC[1;1R, is 6 bytes), so it returns iff
    # the response was forwarded to the PTY.  Markers are built at runtime via
    # string concatenation so they cannot be matched in the echoed command.
    repro = (
        'python3 -c "import sys,termios,tty; '
        + "sys.stdout.write(chr(10)+'CPR'+'PROBE_START'+chr(10)); sys.stdout.flush(); "
        + "fd=sys.stdin.fileno(); old=termios.tcgetattr(fd); tty.setraw(fd); "
        + "sys.stdout.write('\\x1b[6n'); sys.stdout.flush(); "
        + "d=sys.stdin.buffer.read(4); "
        + "termios.tcsetattr(fd,termios.TCSADRAIN,old); "
        + "sys.stdout.write(chr(10)+'CPR'+'GOTREPLY'+str(len(d))+chr(10))"
        + '"'
    )
    type_with_delay(terminal_textarea, repro, 10)
    terminal_textarea.press("Enter")

    # Wait for the runtime-assembled success marker.  With the bug the program
    # blocks in read() and CPRGOTREPLY never appears, so this times out and
    # raises with the full buffer (whether CPRPROBE_START is present tells you
    # if the program even started -- if it is missing too, python3 may be
    # unavailable in the terminal). This is the same hang that freezes
    # `gh auth login`.
    wait_for_xterm_substring(page, "CPRGOTREPLY")
