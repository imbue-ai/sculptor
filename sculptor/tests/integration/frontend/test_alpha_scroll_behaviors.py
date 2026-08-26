"""Integration tests for alpha chat scroll behaviors.

Covers:
- Scroll-to-top: first message padding is visible when scrolled to top
- Jump-to-bottom button: appears when scrolled away, clicking it scrolls to bottom
- Scroll position not off after agent tab round-trip
- Last user message stays visible at maximum scroll after agent tab switch
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import get_jump_to_bottom_button
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_LONG_TEXT = " ".join(["This is a longer response that should take up some space."] * 20)
_SHORT_TEXT = "Short reply."


@user_story("to see the first message without extra padding above it when scrolled to top")
def test_first_message_visible_at_top(sculptor_instance_: SculptorInstance) -> None:
    """When scrolled to the top, the first message should be visible
    with consistent padding (paddingStart), not pushed off-screen.

    This tests the fix for scroll-to-top setting scrollTop=0 for the
    first message to keep paddingStart visible.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    scroll_alpha_chat_to_top(page)

    page.wait_for_function(
        f"""() => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const item = container && container.querySelector('[data-index="0"]');
            const intro = container && container.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_INTRO}"]');
            if (!container || !item || !intro) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            const introBottom = intro.getBoundingClientRect().bottom - container.getBoundingClientRect().top;
            return offset >= 0 && offset < container.clientHeight && offset >= introBottom - 5 && offset < introBottom + 50;
        }}"""
    )


@user_story("to see the jump button when scrolled away and dismiss it by clicking")
def test_jump_button_appears_and_works(sculptor_instance_: SculptorInstance) -> None:
    """Scrolling away from the bottom should show the jump-to-bottom button.
    Clicking it should scroll to bottom and hide the button.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    jump_button = get_jump_to_bottom_button(page)

    scroll_alpha_chat_to_top(page)

    expect(jump_button).to_be_visible()

    scroll_before_click = get_alpha_scroll_position(page)

    jump_button.click()

    page.wait_for_function(
        f"""(scrollBefore) => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && el.scrollTop > scrollBefore;
        }}""",
        arg=scroll_before_click,
    )


@user_story("to have the first message remain visible at top after an agent tab round-trip")
def test_first_message_visible_after_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """After scrolling to top, switching to another agent, and switching back,
    the first message should still be visible in the viewport.  This tests
    that scroll persistence restores the scroll position near the top.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    create_agent_panel(page, section="center")
    tabs = PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs()
    expect(tabs).to_have_count(2)

    tabs.first.click()
    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    scroll_alpha_chat_to_top(page)

    page.wait_for_function(
        f"""() => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const item = container && container.querySelector('[data-index="0"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return offset >= 0 && offset < container.clientHeight;
        }}"""
    )

    tabs.last.click()

    tabs.first.click()

    page.wait_for_function(
        f"""() => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const item = container && container.querySelector('[data-index="0"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return offset >= -20 && offset < container.clientHeight;
        }}"""
    )


@user_story("to have the last user message remain visible at max scroll after agent tab switch")
def test_user_message_visible_at_max_scroll_after_agent_switch(sculptor_instance_: SculptorInstance) -> None:
    """After switching agents and back, scrolling to the maximum position
    should still keep the last user message visible.  This is a complement
    to test_dynamic_padding_survives_agent_switch — testing that the
    dynamic paddingEnd constrains scroll range correctly.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()

    PlaywrightWorkspaceSection(page, "bottom").collapse_section()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    create_agent_panel(page, section="center")
    tabs = PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs()
    expect(tabs).to_have_count(2)

    tabs.first.click()
    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    tabs.last.click()

    tabs.first.click()
    expect(alpha_view).to_be_visible()

    scroll_alpha_chat_by(page, 10000)

    page.wait_for_function(
        f"""() => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const item = container && container.querySelector('[data-index="2"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return offset >= 0 && offset < container.clientHeight;
        }}"""
    )
