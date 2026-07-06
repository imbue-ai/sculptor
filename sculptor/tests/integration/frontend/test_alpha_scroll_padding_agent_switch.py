"""Integration test for dynamic bottom padding surviving agent tab switches.

When a user sends a message and the agent responds with a short reply, the
dynamic paddingEnd ensures the last user message can be scrolled to the top
of the viewport.  This padding must survive switching to a different agent
tab and back.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.alpha_chat_view import wait_for_alpha_scroll_settled
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_SHORT_TEXT = "Hello, this is a short reply."


@user_story("to have dynamic bottom padding survive agent tab switches")
def test_dynamic_padding_survives_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """Dynamic paddingEnd should persist after switching to another agent and back.

    Steps:
    1. Create agent 1 with a short conversation (user + assistant + user + assistant)
    2. Add agent 2 to the workspace
    3. Navigate to agent 1 and verify dynamic padding constrains scroll
    4. Navigate to agent 2
    5. Navigate back to agent 1
    6. Verify dynamic padding still constrains scroll (user message visible)
    """
    page = sculptor_instance_.page

    # --- Setup: create agent 1 with two exchanges in classic view ---
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Close the bottom panel to maximize chat height for scroll tests.
    # Must be done after workspace creation since the terminal only exists in workspaces.
    PlaywrightWorkspaceSection(page, "bottom").collapse_section()

    # Send a follow-up so we have a "last user message" at data-index=2
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # --- Add agent 2 to the same workspace ---
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(2)

    # Navigate to agent 1 to verify baseline padding.
    panel_tabs.get_panel_tabs().first.click()
    expect(get_alpha_chat_view(page)).to_be_visible()

    # Baseline check: scroll down maximally — user message at index 2 should
    # remain visible thanks to dynamic paddingEnd.
    scroll_alpha_chat_by(page, 10000)

    page.wait_for_function(
        f"""(idx) => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const item = container && container.querySelector('[data-index="' + idx + '"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return offset >= 0 && offset < container.clientHeight;
        }}""",
        arg=2,
    )

    # --- Switch to agent 2 ---
    panel_tabs.get_panel_tabs().last.click()

    # --- Switch back to agent 1 ---
    panel_tabs.get_panel_tabs().first.click()
    expect(chat_panel.get_messages()).to_have_count(4)

    # Scroll down maximally — user message at index 2 should STILL be visible.
    # This is the crux of the bug: without the fix, dynamic paddingEnd resets
    # to the static fallback (64px), allowing the user message to scroll off.
    scroll_alpha_chat_by(page, 10000)

    page.wait_for_function(
        f"""(idx) => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const item = container && container.querySelector('[data-index="' + idx + '"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return offset >= 0 && offset < container.clientHeight;
        }}""",
        arg=2,
    )


@user_story("to have stable scroll height after switching agent tabs")
def test_scroll_height_settles_after_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """After switching agent tabs and back, the scrollHeight should settle to the
    same value it had before the switch.  This verifies that dynamic padding
    recalculation doesn't permanently change the virtual layout.
    """
    page = sculptor_instance_.page

    # --- Setup: create agent 1 with two exchanges in classic view ---
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # --- Add agent 2 ---
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(2)

    panel_tabs.get_panel_tabs().first.click()
    expect(get_alpha_chat_view(page)).to_be_visible()

    # Record the scrollHeight BEFORE switching, once the layout has settled so we
    # capture the stable value rather than a mid-settle one.
    wait_for_alpha_scroll_settled(page)
    handle = page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && el.scrollHeight > 0 ? el.scrollHeight : null;
        }}"""
    )
    before_scroll_height = handle.json_value()

    # --- Switch to agent 2 ---
    panel_tabs.get_panel_tabs().last.click()

    # --- Switch back to agent 1 ---
    panel_tabs.get_panel_tabs().first.click()
    expect(chat_panel.get_messages()).to_have_count(4)

    # Once the scroll machine reports settled, the scrollHeight should match the
    # value from before the switch (dynamic padding recalculation is stable).
    wait_for_alpha_scroll_settled(page)
    page.wait_for_function(
        f"""(expected) => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && el.scrollHeight === expected;
        }}""",
        arg=before_scroll_height,
    )
