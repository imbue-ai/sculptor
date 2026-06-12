"""Scenario: Long chat scroll render cascade.

Measures re-renders when the user scrolls through a chat history with many
messages. Components outside the scroll area (sidebars, DockingLayout,
panel content, chat input) should not re-render during scroll.

This scenario requires the agent to have finished generating a response so
there's a meaningful message list to scroll through.
"""

import time

DESCRIPTION = "Long chat scroll (scroll through message history)"

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
    "Message",
    "ToolBlock",
    "MarkdownBlock",
    "ScrollArea",
]


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    # Wait for the agent to finish streaming its initial response
    time.sleep(20)

    # Send a few more messages to build up a longer history
    editor = page.locator('[contenteditable="true"]').first
    if editor.is_visible():
        editor.click()
        time.sleep(0.2)
        editor.type("Please list the first 10 prime numbers.")
        time.sleep(0.2)
        page.keyboard.press("Enter")
        time.sleep(15)  # Wait for response

    # Scroll to the top to set up the scroll-down action
    scroll_area = page.locator('[data-radix-scroll-area-viewport]').first
    if scroll_area.is_visible():
        scroll_area.evaluate("el => el.scrollTop = 0")
    time.sleep(0.5)


def action(page):
    # Scroll down through the message list in several steps
    scroll_area = page.locator('[data-radix-scroll-area-viewport]').first
    if not scroll_area.is_visible():
        # Fall back to scrolling the chat panel area
        chat_panel = page.locator('[data-testid="chat-panel"]').first
        if not chat_panel.is_visible():
            # Just wheel scroll on the page
            page.mouse.wheel(0, 400)
            time.sleep(0.2)
            page.mouse.wheel(0, 400)
            time.sleep(0.2)
            page.mouse.wheel(0, 400)
            time.sleep(0.2)
            page.mouse.wheel(0, -800)
            return

    # Scroll down in increments to simulate user scrolling
    for _ in range(5):
        scroll_area.evaluate("el => el.scrollTop += 300")
        time.sleep(0.1)

    time.sleep(0.3)

    # Scroll back up
    for _ in range(5):
        scroll_area.evaluate("el => el.scrollTop -= 300")
        time.sleep(0.1)
