"""Scenario: Chat message arrival render cascade.

Measures re-renders triggered when a user sends a chat message and the agent
responds with a streaming response. Components outside the chat area should
not re-render.
"""

import time


DESCRIPTION = "Chat message arrival render cascade"

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
    "ChangesPanel",
    "AlphaChatInterface",
    "ChatPanelContent",
    "ChatInput",
]


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    # Wait for the initial "Say hello" agent response to finish streaming
    time.sleep(15)


def action(page):
    # Type a message in the chat input and send it
    editor = page.locator('[contenteditable="true"]').first
    editor.click()
    time.sleep(0.3)
    editor.type("What is 2+2?")
    time.sleep(0.3)
    page.keyboard.press("Enter")
    # Wait for the agent to stream its response
    time.sleep(15)
