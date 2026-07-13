"""Integration tests for the mobile AgentSwitcher pill + AgentSheet.

The agent switcher pill (in the floating status row) opens a bottom sheet listing
the workspace's agents, with a "New agent" row and long-press rename/delete on
each row.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.mobile_workspace import enter_mobile_workspace
from sculptor.testing.elements.mobile_workspace import get_delete_confirm_button
from sculptor.testing.elements.mobile_workspace import get_inline_rename_input
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

pytestmark = pytest.mark.mobile


@user_story("to add and switch between agents from the mobile agent sheet")
def test_mobile_agent_sheet_new_and_switch(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    # The pill opens the sheet, which starts with just the one agent.
    sheet = shell.open_agent_sheet()
    expect(sheet.get_rows()).to_have_count(1)

    # "New agent" creates a second agent and navigates to it.
    sheet.get_new_agent_button().click()
    sheet.expect_closed()
    expect(shell.root()).to_be_visible()

    # Reopening the sheet now lists both agents; switching to the other navigates.
    sheet = shell.open_agent_sheet()
    expect(sheet.get_rows()).to_have_count(2)
    url_before = page.url
    sheet.get_other_row().click()
    sheet.expect_closed()
    expect(shell.root()).to_be_visible()
    expect(page).not_to_have_url(url_before)


@user_story("to rename an agent from the mobile agent sheet")
def test_mobile_agent_sheet_rename(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    sheet = shell.open_agent_sheet()
    sheet.long_press_row(sheet.get_current_row())
    sheet.get_rename_action().click()

    rename_input = get_inline_rename_input(page)
    expect(rename_input).to_be_visible()
    rename_input.fill("Renamed Mobile Agent")
    rename_input.press("Enter")

    expect(rename_input).to_have_count(0)
    expect(sheet.get_current_row()).to_contain_text("Renamed Mobile Agent")


@user_story("to delete an agent from the mobile agent sheet")
def test_mobile_agent_sheet_delete(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    # Add a second agent so we can delete the non-current one without navigating away.
    sheet = shell.open_agent_sheet()
    sheet.get_new_agent_button().click()
    sheet.expect_closed()
    expect(shell.root()).to_be_visible()

    sheet = shell.open_agent_sheet()
    expect(sheet.get_rows()).to_have_count(2)
    sheet.long_press_row(sheet.get_other_row())
    sheet.get_delete_action().click()
    get_delete_confirm_button(page).click()

    expect(sheet.get_rows()).to_have_count(1)
