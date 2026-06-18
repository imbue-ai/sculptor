"""Regression test: terminal text must stay legible in light mode.

In light mode, terminal output that uses the ANSI "white" / "bright white"
palette entries — e.g. the *context* (unmodified) lines in a Claude Code
file-write update block — rendered white-on-white and was impossible to read.
The cause: ``buildTerminalTheme`` set only ``foreground``/``background``/etc.
and never overrode the 16 ANSI palette colors, so xterm.js fell back to its
built-in palette, which is tuned for a dark background (``white`` ≈ #d3d7cf,
``brightWhite`` ≈ #eeeeec). Against the light-mode panel background those two
entries have almost no contrast.

This asserts the light-mode theme defines an ANSI palette whose white-family
entries have real contrast against the background. It reads the xterm theme
*config object* (``xterm.options.theme.white`` etc.), the same behavioural
signal the sibling ``test_regression_terminal_theme_toggle.py`` reads for the
background color — not a rendered/computed style.

Distinct from ``test_regression_terminal_theme_toggle.py`` (which covers the
terminal *background* updating on theme toggle); both live in the same xterm
theme/palette code.
"""

from sculptor.testing.elements.terminal import get_xterm_theme_background
from sculptor.testing.elements.terminal import get_xterm_theme_color
from sculptor.testing.elements.terminal import get_xterm_theme_foreground
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import wait_for_xterm_theme_change
from sculptor.testing.elements.terminal import wait_for_xterm_theme_ready
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# WCAG AA contrast ratio for normal-size text. The bug rendered white-on-white
# (ratio ≈ 1.0:1); a correct light-mode palette clears this comfortably.
_MIN_CONTRAST_RATIO = 4.5


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a ``#rrggbb`` color."""
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colors (1.0 .. 21.0)."""
    lighter = max(_relative_luminance(foreground), _relative_luminance(background))
    darker = min(_relative_luminance(foreground), _relative_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _switch_to_light_mode(page, task_page: PlaywrightTaskPage) -> None:
    """Ensure the terminal theme is in light mode, toggling if needed.

    The app defaults to dark mode, so one toggle normally suffices, but we
    detect by background luminance rather than assuming the starting mode.
    """
    if _relative_luminance(get_xterm_theme_background(page)) <= 0.5:
        old_bg = get_xterm_theme_background(page)
        old_fg = get_xterm_theme_foreground(page)
        task_page.toggle_theme()
        wait_for_xterm_theme_change(page, old_bg, old_fg)
    assert _relative_luminance(get_xterm_theme_background(page)) > 0.5, (
        f"expected a light terminal background after switching to light mode, got {get_xterm_theme_background(page)!r}"
    )


@user_story("to read terminal output in light mode without it being white-on-white")
def test_terminal_text_is_legible_in_light_mode(sculptor_instance_: SculptorInstance) -> None:
    """The light-mode terminal theme must give ANSI white-family text real contrast."""
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)
    wait_for_xterm_theme_ready(page)

    _switch_to_light_mode(page, task_page)

    background = get_xterm_theme_background(page)
    # ANSI "white" (index 7) and "brightWhite" (index 15) are what programs use
    # for light-on-dark "default" / context text; these are the entries that
    # rendered white-on-white before the fix.
    for entry in ("white", "brightWhite"):
        color = get_xterm_theme_color(page, entry)
        assert color, (
            f"light-mode theme.{entry} is not set — it falls back to xterm.js's "
            f"dark-tuned default, which is white-on-white against {background!r}"
        )
        ratio = _contrast_ratio(color, background)
        assert ratio >= _MIN_CONTRAST_RATIO, (
            f"light-mode theme.{entry} ({color}) has contrast {ratio:.2f}:1 against "
            f"background {background} — below the {_MIN_CONTRAST_RATIO}:1 legibility floor"
        )
