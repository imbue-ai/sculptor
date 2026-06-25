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
from sculptor.testing.elements.add_panel_dropdown import create_terminal_panel
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection

# The default workspace layout seeds terminal panels into the (collapsed) bottom
# section. A terminal renders as a dynamic panel tab whose id is
# ``terminal:<wsId>:<index>`` and whose xterm content carries no testid of its own,
# so the terminal panel is reached through the bottom section's tab strip / xterm I/O.
_TERMINAL_SECTION = "bottom"


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


def get_agent_terminal_panel(page: Page) -> Locator:
    """The terminal-agent main panel (it replaces the chat panel for terminal agents)."""
    return page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)


def expect_terminal_panel_replaces_chat(page: Page) -> None:
    """Assert the main panel is the terminal, not the chat.

    Both halves of the panel switch for terminal agents: the agent terminal
    panel is visible AND no chat input is mounted anywhere on the page
    (page-level check — the chat-panel POM is scoped to a panel that does
    not exist here).
    """
    expect(get_agent_terminal_panel(page)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_have_count(0)


def expect_chat_replaces_terminal_panel(page: Page) -> None:
    """Assert the main panel is the chat, not the terminal (the inverse switch)."""
    expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_be_visible()
    expect(get_agent_terminal_panel(page)).to_have_count(0)


def get_agent_terminal_textarea(page: Page) -> Locator:
    """The agent terminal panel's xterm input textarea.

    Scoped to ``AGENT_TERMINAL_PANEL`` because the workspace bottom terminal
    panel can also be mounted (hidden), making the bare
    ``.xterm-helper-textarea`` selector ambiguous.
    """
    return page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL).get_by_label("Terminal input")


def type_into_agent_terminal(page: Page, text: str, press_enter: bool = True) -> None:
    """Type ``text`` into the agent terminal's xterm without shell padding.

    For TUIs (e.g. Claude Code) whose input box is not a shell prompt — the
    ``run_command_in_agent_terminal`` no-op padding would pollute the prompt.
    """
    textarea = get_agent_terminal_textarea(page)
    textarea.focus()
    page.wait_for_timeout(300)
    page.keyboard.type(text, delay=20)
    if press_enter:
        page.keyboard.press("Enter")


def run_command_in_agent_terminal(page: Page, command: str) -> None:
    """Type ``command`` into a terminal agent's xterm and press Enter.

    Mirrors ``run_command_in_active_terminal`` (including the no-op padding
    that absorbs xterm.js's freshly-mounted-terminal keystroke drops) but
    scoped to the agent terminal panel.
    """
    no_op = ": ; " * 8  # 32 chars of "no-op then sep" -- absorbs heavy drops
    textarea = get_agent_terminal_textarea(page)
    textarea.focus()
    page.wait_for_timeout(200)
    page.keyboard.type(no_op + command, delay=30)
    textarea.press("Enter")


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
    """Reveal a terminal panel by expanding the (seeded) bottom section.

    The default layout seeds one terminal (Terminal 1) in the collapsed bottom
    section; expanding it reveals the terminal panel content. ``expand_section``
    is idempotent (a no-op when the bottom section is already showing).

    The terminal panel content (``TerminalPanelView``) is a bare xterm wrapper with
    no testid of its own, so readiness is keyed off the seeded terminal's panel tab
    plus its xterm "Terminal input" textarea becoming attached in the bottom section.
    """
    section = PlaywrightWorkspaceSection(page, _TERMINAL_SECTION)
    section.expand_section()
    # At least one terminal panel tab must be present in the bottom section's strip.
    expect(get_terminal_tabs(page).first).to_be_visible(timeout=60_000)
    # The active terminal's xterm textarea (the mount signal) is rendered inside it.
    expect(get_terminal_textarea(page).first).to_be_attached(timeout=60_000)


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
    """Every terminal panel tab in the bottom section's header.

    Terminals render as dynamic panel tabs whose id is ``terminal:<wsId>:<index>``
    (``PANEL_TAB-terminal:...``); they are matched by a ``data-testid`` prefix
    selector scoped under the bottom section's header. The CSS selector stays inside
    the POM to honour the integration-test css-locator ratchet.
    """
    header = PlaywrightWorkspaceSection(page, _TERMINAL_SECTION).get_header()
    return header.locator(f'[data-testid^="{ElementIDs.PANEL_TAB}-terminal:"]')


def add_terminal(page: Page, section: str = _TERMINAL_SECTION) -> None:
    """Create a new terminal panel in ``section`` via the section `+` add-panel dropdown.

    Replaces the old single "+" add-terminal button: in the section shell a terminal
    is created from the section header `+` dropdown's "New terminal" item (the section
    is expanded first when collapsed). Delegates to the shared ``create_terminal_panel``.
    """
    create_terminal_panel(page, section)


def get_tab_close_button(tab: Locator) -> Locator:
    """A terminal panel tab's always-visible close (X) button.

    The close button is rendered inside the tab body with id
    ``PANEL_TAB_CLOSE-<panelId>``; since the panel id is dynamic it is matched by a
    ``data-testid`` prefix selector scoped to the given tab locator. Closing a
    terminal tab opens the close-confirmation dialog (use ``confirm_close_terminal``).
    """
    return tab.locator(f'[data-testid^="{ElementIDs.PANEL_TAB_CLOSE}-"]')


def confirm_close_terminal(page: Page) -> None:
    """Confirm the terminal close-confirmation dialog.

    Closing a terminal tab opens a "Close terminal?" confirmation; clicking its
    confirm button kills the backend shell and drops the tab.
    """
    confirm_button = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
    expect(confirm_button).to_be_visible()
    confirm_button.click()


def get_tab_context_menu_close_others(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_OTHERS)


def get_tab_context_menu_rename(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)


def get_inline_rename_input(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)


def get_xterm_theme_foreground(page: Page) -> str:
    """Return the current xterm foreground color from the terminal options."""
    return page.evaluate(
        """() => {
        const xterm = window.__xterm;
        if (!xterm || !xterm.options.theme) return '';
        return xterm.options.theme.foreground || '';
    }"""
    )


def get_xterm_theme_color(page: Page, key: str) -> str:
    """Return an arbitrary color from the xterm theme options by key.

    Reads ``xterm.options.theme[key]`` (e.g. ``"white"``, ``"brightWhite"``,
    one of the 16 ANSI palette entries) — the theme *config object* our code
    builds, not a rendered/computed style. Returns ``""`` when the entry is
    unset, which is exactly the buggy state for the ANSI palette in light mode
    (an unset entry falls back to xterm.js's dark-tuned default).
    """
    return page.evaluate(
        """(key) => {
        const xterm = window.__xterm;
        if (!xterm || !xterm.options.theme) return '';
        return xterm.options.theme[key] || '';
    }""",
        key,
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
