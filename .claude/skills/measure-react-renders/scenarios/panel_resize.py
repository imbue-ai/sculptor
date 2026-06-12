"""Scenario: Panel resize render cascade.

Measures re-renders triggered by resizing the panel divider between the
center content area and the right/left sidebar via keyboard arrow keys.

We open a side panel first via the sidebar keyboard shortcut (Cmd+shift+e for
file browser, or directly clicking a sidebar icon) to ensure a resize handle
is present, then resize 5 left and 5 right.
"""

import time

DESCRIPTION = "Panel resize render cascade"

TARGET_COMPONENTS = [
    "WorkspacePageContent",
    "DockingLayout",
    "LeftSidebar",
    "LeftSidebarInner",
    "RightSidebar",
    "RightSidebarInner",
    "ZoneContent",
    "ZoneContentInner",
    "DiffSplitContainer",
    "DiffSplitContainerInner",
    "AlphaChatInterface",
    "AlphaChatInterfaceInner",
    "ChatInput",
    "WorkspaceBanner",
    "DiffSummary",
    "FileBrowserPanel",
]


def _open_side_panel(page):
    """Ensure at least one side panel is open so a resize handle exists."""
    # Check if any resize handle already exists
    handles = page.locator('[role="separator"]').all()
    if handles:
        return

    # Try clicking the first sidebar icon to open a panel
    # Look for sidebar icon buttons (panel icons in LeftSidebar / RightSidebar)
    sidebar_icons = page.locator('[data-panel-icon]').all()
    if sidebar_icons:
        sidebar_icons[0].click()
        time.sleep(0.5)
        return

    # Fallback: try keyboard shortcut for file browser (Cmd+Shift+E on mac)
    page.keyboard.press("Meta+Shift+e")
    time.sleep(0.5)


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    _open_side_panel(page)
    # Wait for panel to mount
    time.sleep(0.5)


def action(page):
    handles = page.locator('[role="separator"]').all()
    if not handles:
        # Try opening a panel at action time if setup didn't work
        _open_side_panel(page)
        time.sleep(0.5)
        handles = page.locator('[role="separator"]').all()

    if not handles:
        raise RuntimeError(
            "No resize handles found. Ensure a side panel is visible."
        )

    # Use the last separator (typically the outer left/center divider)
    handle = handles[-1]
    handle.focus()
    time.sleep(0.3)
    for _ in range(5):
        page.keyboard.press("ArrowLeft")
        time.sleep(0.15)
    for _ in range(5):
        page.keyboard.press("ArrowRight")
        time.sleep(0.15)
