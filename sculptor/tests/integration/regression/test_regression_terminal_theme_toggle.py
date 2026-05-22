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
from sculptor.testing.elements.terminal import wait_for_xterm_theme_change
from sculptor.testing.elements.terminal import wait_for_xterm_theme_ready
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


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
    task_page = PlaywrightTaskPage(page=page)

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    # Wait for xterm theme to be fully initialized, then record initial colors.
    wait_for_xterm_theme_ready(page)
    initial_bg = get_xterm_theme_background(page)
    initial_fg = get_xterm_theme_foreground(page)

    # Toggle the theme (Cmd+Shift+D on macOS, Ctrl+Shift+D on Linux).
    task_page.toggle_theme()

    # Wait for the terminal theme colors to actually change (polls via JS).
    wait_for_xterm_theme_change(page, initial_bg, initial_fg)
