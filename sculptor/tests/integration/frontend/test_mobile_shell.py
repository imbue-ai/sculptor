"""Integration tests for the mobile Workspace shell swapping in for the desktop layout.

The mobile shell activates purely on viewport width: ``useLayoutMode`` reports
mobile below 768px in a browser (never in Electron) and mirrors the verdict onto
``<html class="mobileUx">``. These tests exercise both directions of that seam —
a narrow browser gets the shell; a narrow Electron window does not.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.mobile_workspace import MOBILE_VIEWPORT
from sculptor.testing.elements.mobile_workspace import enter_mobile_workspace
from sculptor.testing.elements.mobile_workspace import expect_desktop_layout
from sculptor.testing.elements.mobile_workspace import expect_mobile_layout
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Every test in this module drives the narrow-viewport mobile web UI.
pytestmark = pytest.mark.mobile


@user_story("to get a mobile-optimized workspace on a phone-sized screen")
def test_mobile_shell_replaces_desktop_layout(sculptor_instance_: SculptorInstance) -> None:
    """A narrow browser viewport swaps the desktop layout for the mobile shell."""
    page = sculptor_instance_.page

    # Create the workspace/agent at the default desktop viewport.
    start_task_and_wait_for_ready(sculptor_page=page)
    expect_desktop_layout(page)

    # Narrowing below the 768px breakpoint replaces the whole desktop layout with
    # the single-column mobile shell (header + chat + input).
    shell = enter_mobile_workspace(page, viewport=MOBILE_VIEWPORT)
    expect(shell.root()).to_be_visible()
    expect(shell.get_header()).to_be_visible()
    expect(shell.get_agent_switcher_pill()).to_be_visible()
    expect_mobile_layout(page)


@pytest.mark.electron
@user_story("to keep the full desktop layout in the desktop app no matter how narrow the window")
def test_narrow_electron_window_stays_desktop(sculptor_instance_: SculptorInstance) -> None:
    """The Electron renderer never flips to the mobile shell, even when narrowed.

    ``useLayoutMode`` short-circuits to desktop in the Electron renderer (decided
    once at module load, and the media-query listener is never wired), so shrinking
    the window below the mobile breakpoint must not swap in the mobile shell.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page)
    expect_desktop_layout(page)

    # Narrow the emulated window well below the 768px breakpoint — a browser would
    # flip to mobile here; Electron must not.
    page.set_viewport_size(MOBILE_VIEWPORT)
    expect_desktop_layout(page)
