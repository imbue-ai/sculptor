"""Scenario: TipTap editor typing render cascade.

Measures re-renders triggered when the user types in the TipTap chat input.
Only ChatInput should re-render (it subscribes to usePromptDraft which updates
a per-task Jotai atom on every keystroke).  All components outside the chat
input — the workspace sidebar, the section grid, AlphaChatInterface — should
remain stable.
"""

import time


DESCRIPTION = "TipTap editor typing render cascade"

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


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    # Wait for the initial agent response to finish streaming.
    time.sleep(15)
    # Click into the TipTap editor to focus it before measuring.
    editor = page.locator('[contenteditable="true"]').first
    editor.click()
    time.sleep(0.3)


def action(page):
    # Type a realistic-length message, one character at a time, to trigger
    # per-keystroke usePromptDraft atom updates.
    page.keyboard.type("Testing render isolation for the TipTap editor input", delay=50)
    # Allow trailing React commits to flush.
    time.sleep(0.5)
