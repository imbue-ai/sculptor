"""Scenario: Section resize render cascade.

Measures re-renders triggered by resizing the divider between the center
section and a side section via keyboard arrow keys.

We expand the right section first via its workspace-header toggle to ensure a
section resize handle is present, then resize 5 left and 5 right.
"""

import time

DESCRIPTION = "Section resize render cascade"

# Memo-wrapped exports (e.g. SplittableSection) are recorded under their inner
# function names ("SplittableSectionComponent").
TARGET_COMPONENTS = [
    "WorkspacePageContent",
    "WorkspaceLayoutShell",
    "WorkspaceSidebar",
    "WorkspaceHeaderComponent",
    "SectionGrid",
    "SplittableSectionComponent",
    "PanelSectionComponent",
    "SectionHeaderComponent",
    "SectionBodyComponent",
    "ResizeHandle",
    "AlphaChatInterface",
    "ChatPanelContent",
    "ChatInput",
    "DiffSummary",
    "FilesPanel",
]

# Section dividers carry SECTION_RESIZE_HANDLE-{left,right,bottom} test ids;
# the bare [role="separator"] also matches the sidebar's edge-overlay handle,
# so scope the locator to section handles.
SECTION_RESIZE_HANDLES = '[data-testid^="SECTION_RESIZE_HANDLE"]'


def _expand_right_section(page):
    """Ensure at least one side section is expanded so a resize handle exists."""
    if page.locator(SECTION_RESIZE_HANDLES).count() > 0:
        return

    # Expand the right section via its toggle in the workspace header.
    toggle = page.locator('[data-testid="HEADER_SECTION_TOGGLE_RIGHT"]')
    if toggle.count() > 0:
        toggle.click()
        time.sleep(0.5)


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    _expand_right_section(page)
    # Wait for the section to mount
    time.sleep(0.5)


def action(page):
    handles = page.locator(SECTION_RESIZE_HANDLES).all()
    if not handles:
        # Try expanding a section at action time if setup didn't work
        _expand_right_section(page)
        time.sleep(0.5)
        handles = page.locator(SECTION_RESIZE_HANDLES).all()

    if not handles:
        raise RuntimeError(
            "No section resize handles found. Ensure a side section is expanded."
        )

    # Prefer a horizontal divider — ArrowLeft/ArrowRight only resizes x-axis
    # handles (the bottom divider listens to ArrowUp/ArrowDown instead).
    x_handles = page.locator(
        '[data-testid="SECTION_RESIZE_HANDLE-left"], [data-testid="SECTION_RESIZE_HANDLE-right"]'
    ).all()
    handle = x_handles[-1] if x_handles else handles[-1]
    handle.focus()
    time.sleep(0.3)
    for _ in range(5):
        page.keyboard.press("ArrowLeft")
        time.sleep(0.15)
    for _ in range(5):
        page.keyboard.press("ArrowRight")
        time.sleep(0.15)
