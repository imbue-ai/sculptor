"""Scenario: Section visibility toggle render cascade.

Measures re-renders triggered when the user shows and hides the right section
via its toggle button in the workspace header. Toggling flips the per-section
expanded flag (isSectionExpandedAtom) which SectionGrid subscribes to — this
should NOT cause chat content, the message list, or the terminal to re-render.
"""

import time

DESCRIPTION = "Section visibility toggle (show/hide right section)"

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
    "AlphaChatInterface",
    "ChatPanelContent",
    "ChatInput",
]

RIGHT_SECTION_TOGGLE = '[data-testid="HEADER_SECTION_TOGGLE_RIGHT"]'
RIGHT_SECTION = '[data-testid="SECTION_RIGHT"]'


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    # Ensure the right section starts hidden so we measure a clean
    # show+hide cycle.
    right_section = page.locator(RIGHT_SECTION)
    if right_section.count() > 0 and right_section.is_visible():
        page.locator(RIGHT_SECTION_TOGGLE).click()
        time.sleep(0.5)


def action(page):
    toggle = page.locator(RIGHT_SECTION_TOGGLE)
    if toggle.count() == 0:
        raise RuntimeError("Right-section toggle not found in the workspace header")

    # Show the section
    toggle.click()
    time.sleep(0.3)

    # Hide the section
    toggle.click()
    time.sleep(0.3)

    # Show again
    toggle.click()
    time.sleep(0.3)
