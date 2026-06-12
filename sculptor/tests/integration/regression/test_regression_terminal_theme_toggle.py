"""Regression test: terminal theme must update when the app theme is toggled.

Pressing Cmd+Shift+D (Meta+Shift+D) toggles the UI between dark and light mode.
The terminal (xterm.js) theme should also update to match.  A previous bug caused
the terminal to keep its old colors because the background color was read from the
DOM via getComputedStyle, which could return stale CSS variable values when the
Radix theme transition was still in progress.
"""

from sculptor.testing.elements.terminal import get_xterm_theme_background
from sculptor.testing.elements.terminal import get_xterm_theme_foreground
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to have the terminal colors update when I toggle the UI theme")
def test_terminal_theme_updates_on_toggle(sculptor_instance_: SculptorInstance) -> None:
    """Toggling the app theme via Cmd+Shift+D must also update the terminal theme.

    Steps:
    1. Create a workspace and open the terminal panel
    2. Record the initial xterm background and foreground colors
    3. Press Meta+Shift+D to toggle the theme
    4. Wait for the theme transition to complete
    5. Record the new xterm background and foreground colors
    6. Assert both colors changed — the terminal adopted the new theme
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    # Record the initial terminal theme colors (default is dark).
    initial_bg = get_xterm_theme_background(page)
    initial_fg = get_xterm_theme_foreground(page)

    assert initial_bg, "xterm theme background should be set after terminal opens"
    assert initial_fg, "xterm theme foreground should be set after terminal opens"

    # Toggle the theme (Cmd+Shift+D on macOS, Ctrl+Shift+D on Linux).
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+Shift+d")

    # Wait for the theme transition and React effects to complete.
    page.wait_for_timeout(2000)

    # Read the terminal theme colors after the toggle.
    new_bg = get_xterm_theme_background(page)
    new_fg = get_xterm_theme_foreground(page)

    assert new_bg != initial_bg, (
        f"Terminal background color did not change after toggling the app theme. Before: {initial_bg!r}, After: {new_bg!r}."
    )
    assert new_fg != initial_fg, (
        f"Terminal foreground color did not change after toggling the app theme. Before: {initial_fg!r}, After: {new_fg!r}."
    )
