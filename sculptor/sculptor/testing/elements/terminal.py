"""Terminal panel helpers for integration tests.

Encapsulates xterm.js-specific selectors and JavaScript evaluation that cannot
be replaced with ``data-testid`` attributes because xterm renders its own DOM.

NOTE: These functions use ``page.locator()`` with CSS selectors and
``page.evaluate()``, which are exceptions to our integration test rules.
xterm.js is a third-party library whose internal DOM is not controllable via
``data-testid`` attributes, and reading the xterm buffer requires direct
JavaScript access to the ``window.__xterm`` handle.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from sculptor.constants import ElementIDs


def get_terminal_textarea(page: Page) -> Locator:
    """Return the xterm hidden textarea used for keyboard input.

    xterm.js creates a hidden ``<textarea>`` with class ``xterm-helper-textarea``
    to capture keyboard events.  This element is the correct target for
    ``type()``, ``press()``, and ``focus()`` calls in terminal tests.
    """
    return page.locator(".xterm-helper-textarea")


def run_command_in_active_terminal(page: Page, command: str) -> None:
    """Type ``command`` into the currently-active xterm and press Enter.

    Focuses the active tab's helper textarea, gives Playwright a brief
    moment to settle focus, then types via ``page.keyboard.type`` (which
    targets the focused element directly -- no locator click race).
    Finally fires Enter on the same textarea.

    ``.last`` on the role locator picks the most recently mounted xterm,
    which is the active tab whether there's one tab or many.

    Leading ``no_op`` padding: xterm.js's helper-textarea focus handling
    is racy with synthetic keyboard events on a freshly mounted terminal,
    and the first ~2-10 typed characters can be dropped. Prepending a
    string of no-op shell commands (``: ; : ; ...``) absorbs the loss --
    even if the first dozen+ chars never reach the shell, the rest still
    parses as `<dropped> ; <real command>` and runs.
    """
    no_op = ": ; " * 8  # 32 chars of "no-op then sep" -- absorbs heavy drops
    textarea = page.get_by_label("Terminal input").last
    textarea.focus()
    page.wait_for_timeout(200)
    page.keyboard.type(no_op + command, delay=30)
    textarea.press("Enter")


def type_with_global_keyboard(page: Page, text: str, *, delay_ms: int = 30) -> None:
    """Type ``text`` via the global keyboard, which routes to whatever element
    currently holds focus (``document.activeElement``).

    Unlike ``locator.press_sequentially`` / ``type_with_delay`` (which dispatch
    keystrokes straight to a target element regardless of focus), this exercises
    real focus routing -- so a caller can prove which element actually receives
    keyboard input.
    """
    page.keyboard.type(text, delay=delay_ms)


def get_xterm_active_line(page: Page) -> str:
    """Read the current input line from the xterm buffer (the line the cursor is on)."""
    return page.evaluate(
        """() => {
        const xterm = window.__xterm;
        if (!xterm) return '';
        const buffer = xterm.buffer.active;
        const line = buffer.getLine(buffer.cursorY + buffer.baseY);
        return line ? line.translateToString(true) : '';
    }"""
    )


def get_xterm_buffer_text(page: Page) -> str:
    """Read all non-empty lines from the xterm scrollback + visible buffer as a single string."""
    return page.evaluate(
        """() => {
        const xterm = window.__xterm;
        if (!xterm) return '';
        const buffer = xterm.buffer.active;
        const lines = [];
        for (let i = 0; i <= buffer.baseY + buffer.cursorY; i++) {
            const line = buffer.getLine(i);
            if (line) {
                lines.push(line.translateToString(true));
            }
        }
        return lines.join('\\n');
    }"""
    )


def wait_for_xterm_substring(page: Page, substring: str) -> None:
    """Wait until the xterm scrollback buffer contains ``substring``.

    Polls ``window.__xterm``'s scrollback via ``page.wait_for_function`` so
    the test observes shell output landing in the buffer instead of guessing
    with ``page.wait_for_timeout(N)``. On timeout, raises ``AssertionError``
    carrying the full buffer text for diagnostics.

    This is the right primitive for "did the shell write X to the terminal?"
    assertions -- ``expect()`` cannot target the xterm buffer (it is read via
    a JS handle, not a DOM locator), so this helper bridges the gap.
    """
    try:
        page.wait_for_function(
            """needle => {
                const xterm = window.__xterm;
                if (!xterm) return false;
                const buffer = xterm.buffer.active;
                for (let i = 0; i <= buffer.baseY + buffer.cursorY; i++) {
                    const line = buffer.getLine(i);
                    if (line && line.translateToString(true).includes(needle)) return true;
                }
                return false;
            }""",
            arg=substring,
        )
    except PlaywrightTimeoutError as e:
        buffer_text = get_xterm_buffer_text(page)
        raise AssertionError(
            f"Expected xterm buffer to contain {substring!r}, but timed out. Buffer:\n{buffer_text}"
        ) from e


def wait_for_xterm_buffer_nonempty(page: Page) -> None:
    """Wait until the xterm buffer has rendered some shell output.

    A non-empty buffer means the WebSocket connected and the shell delivered its
    prompt -- i.e. the terminal mount/connect cycle has settled. Use this as a
    condition-based alternative to a fixed ``wait_for_timeout`` after opening the
    panel: it adapts to however long the connection actually takes, instead of
    guessing a window that is simultaneously too long on fast machines and too
    short under CI load.
    """
    try:
        page.wait_for_function(
            """() => {
                const xterm = window.__xterm;
                if (!xterm) return false;
                const buffer = xterm.buffer.active;
                for (let i = 0; i <= buffer.baseY + buffer.cursorY; i++) {
                    const line = buffer.getLine(i);
                    if (line && line.translateToString(true).trim().length > 0) return true;
                }
                return false;
            }"""
        )
    except PlaywrightTimeoutError as e:
        raise AssertionError("xterm buffer never rendered any shell output (terminal failed to connect).") from e


def get_xterm_cursor_row(page: Page) -> int:
    """Return the absolute cursor row (cursorY + baseY) from the xterm buffer."""
    return page.evaluate(
        """() => {
        const xterm = window.__xterm;
        if (!xterm) return -1;
        const buffer = xterm.buffer.active;
        return buffer.cursorY + buffer.baseY;
    }"""
    )


def ensure_terminal_panel_open(page: Page) -> None:
    """Ensure the terminal panel zone is open, clicking the icon only if needed.

    The sidebar icon is a toggle: clicking it when the zone is already visible
    will CLOSE the zone.  Between tests, ``_targeted_cleanup_ui`` does not clear
    localStorage, so ``zoneVisibilityAtom`` (key ``sculptor-zone-visibility``)
    may still have ``"bottom": true`` from a previous test.  If we blindly
    click, we close the panel instead of opening it.

    This helper checks whether the terminal panel content is already showing
    before deciding whether to click.
    """
    add_button = page.get_by_test_id(ElementIDs.ADD_TERMINAL_BUTTON)
    starting_text = page.get_by_test_id(ElementIDs.TERMINAL_STARTING_TEXT)
    panel_content = add_button.or_(starting_text)

    if not panel_content.is_visible():
        terminal_icon = page.get_by_test_id(ElementIDs.PANEL_ICON_TERMINAL)
        expect(terminal_icon).to_be_visible()
        terminal_icon.click()

    # Two-phase wait: the panel shows "Starting terminal..." while waiting for
    # the workspace ID to be available, then switches to the tab bar once the
    # terminal component mounts.
    expect(panel_content).to_be_visible(timeout=10_000)
    expect(add_button).to_be_visible(timeout=60_000)


def open_terminal_and_wait(page: Page) -> None:
    """Open the terminal panel and wait for xterm to be ready for input."""
    ensure_terminal_panel_open(page)

    # Wait for xterm's hidden textarea (the keyboard input target) to be attached.
    expect(get_terminal_textarea(page)).to_be_attached()

    # Wait for the shell prompt to render and the WebSocket to be connected.
    page.wait_for_timeout(3000)


def get_active_element_focus_info(page: Page) -> tuple[bool, list[str], str | None]:
    """Return ``(is_terminal_focused, class_list, data_testid)`` for ``document.activeElement``.

    Used by focus-stealing regression tests where we need to confirm the
    terminal's hidden xterm-helper-textarea is the active element after some
    UI event, and emit a useful diagnostic if it isn't.
    """
    return page.evaluate(
        """() => {
        const el = document.activeElement;
        if (!el) return [false, [], null];
        const classes = Array.from(el.classList);
        return [classes.includes('xterm-helper-textarea'), classes, el.getAttribute('data-testid')];
    }"""
    )


def get_xterm_theme_background(page: Page) -> str:
    """Return the current xterm background color from the terminal options."""
    return page.evaluate(
        """() => {
        const xterm = window.__xterm;
        if (!xterm || !xterm.options.theme) return '';
        return xterm.options.theme.background || '';
    }"""
    )


def get_terminal_tabs(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.TERMINAL_TAB)


def get_add_terminal_button(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.ADD_TERMINAL_BUTTON)


def get_terminal_panel_icon(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.PANEL_ICON_TERMINAL)


def get_terminal_starting_text(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.TERMINAL_STARTING_TEXT)


def get_tab_close_button(tab: Locator) -> Locator:
    return tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)


def get_tab_context_menu_close_others(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_OTHERS)


def get_tab_context_menu_rename(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)


def get_inline_rename_input(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)


def get_terminal_heading(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.TERMINAL_HEADING)


def get_xterm_theme_foreground(page: Page) -> str:
    """Return the current xterm foreground color from the terminal options."""
    return page.evaluate(
        """() => {
        const xterm = window.__xterm;
        if (!xterm || !xterm.options.theme) return '';
        return xterm.options.theme.foreground || '';
    }"""
    )


def wait_for_xterm_theme_ready(page: Page) -> None:
    """Wait until the xterm theme has non-empty background and foreground colors."""
    try:
        page.wait_for_function(
            """() => {
                const xterm = window.__xterm;
                return !!(xterm && xterm.options.theme
                    && xterm.options.theme.background
                    && xterm.options.theme.foreground);
            }"""
        )
    except PlaywrightTimeoutError as e:
        bg = get_xterm_theme_background(page)
        fg = get_xterm_theme_foreground(page)
        raise AssertionError(f"xterm theme not ready. bg: {bg!r}, fg: {fg!r}") from e


def wait_for_xterm_theme_change(page: Page, old_bg: str, old_fg: str) -> None:
    """Wait until the xterm theme colors differ from the given values."""
    try:
        page.wait_for_function(
            """([oldBg, oldFg]) => {
                const xterm = window.__xterm;
                if (!xterm || !xterm.options.theme) return false;
                const bg = xterm.options.theme.background || '';
                const fg = xterm.options.theme.foreground || '';
                return bg !== oldBg && fg !== oldFg;
            }""",
            arg=[old_bg, old_fg],
        )
    except PlaywrightTimeoutError as e:
        new_bg = get_xterm_theme_background(page)
        new_fg = get_xterm_theme_foreground(page)
        raise AssertionError(
            f"Terminal theme did not change. bg: {old_bg!r} → {new_bg!r}, fg: {old_fg!r} → {new_fg!r}"
        ) from e
