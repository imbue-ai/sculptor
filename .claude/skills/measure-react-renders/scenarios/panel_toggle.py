"""Scenario: Panel visibility toggle render cascade.

Measures re-renders triggered when the user opens and closes side panels
via the sidebar icon buttons. Toggling panel visibility changes
zoneVisibilityAtom which DockingLayout subscribes to — this should NOT
cause chat content, message list, or terminal to re-render.
"""

import time

DESCRIPTION = "Panel visibility toggle (open/close side panel)"

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
    "AgentTabs",
    "SidebarIcon",
    "PanelModal",
]


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    # Ensure the right panel is closed to start from a consistent state.
    # Click a sidebar icon to open the right panel if it's not already visible.
    right_panel_area = page.locator('[data-testid="panel-right-area"]')
    if right_panel_area.count() > 0 and right_panel_area.is_visible():
        # Close it first so we measure a clean open+close cycle
        icons = page.locator('[data-sidebar="right"] [data-panel-icon]').all()
        if icons:
            icons[0].click()
            time.sleep(0.5)


def action(page):
    # Find sidebar icons in the right sidebar and click the first one to toggle
    # the right panel open and closed twice. We use aria-label or data attributes
    # that the sidebar icons expose.
    right_icons = page.locator('[data-sidebar="right"] [data-panel-icon]').all()
    if not right_icons:
        # Fall back: look for any panel icon buttons
        right_icons = page.locator('[data-panel-icon]').all()

    if not right_icons:
        raise RuntimeError("No sidebar panel icons found")

    icon = right_icons[0]

    # Open the panel
    icon.click()
    time.sleep(0.3)

    # Close the panel
    icon.click()
    time.sleep(0.3)

    # Open again
    icon.click()
    time.sleep(0.3)
