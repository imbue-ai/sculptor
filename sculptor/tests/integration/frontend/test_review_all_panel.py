"""Integration tests for the Review All panel's open behavior and scope picker.

Review All is a single-instance registered panel with no default section
placement (a fresh workspace never seeds it). These tests verify that it opens
through a section's add-panel ``+`` dropdown, that only one instance can be open
at a time, and that its combined-diff scope picker defaults to All.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""


@user_story("to see the scope picker default to All in the Review All panel")
def test_scope_picker_defaults_to_all(sculptor_instance_: SculptorInstance) -> None:
    """Opening Review All should default its combined-diff scope to All."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel()
    task_page.click_review_all()

    # The combined diff lives in the Review All panel (the Changes panel renders
    # its own scope picker too), so go through the Review All panel POM to avoid
    # matching two pickers.
    review_all_panel = task_page.get_review_all_panel()
    scope_picker = review_all_panel.get_scope_picker()
    expect(scope_picker).to_be_visible()
    # Assert the "All" segment is the CHECKED one — the picker always renders the
    # word "All", so a contains-text assertion cannot catch a wrong default.
    expect(review_all_panel.get_scope_all()).to_have_attribute("data-state", "on")


@user_story("to open Review All from a section's add-panel dropdown as a single-instance panel")
def test_review_all_single_instance_opened_via_add_panel_dropdown(sculptor_instance_: SculptorInstance) -> None:
    """Review All has no default placement, opens via the section ``+`` dropdown,
    and is single-instance (an open panel is not offered for re-adding).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt="Say hello")

    # No default section placement: a fresh workspace does not seed Review All —
    # no panel is mounted and its home-review section (left) has no tab for it.
    left_section = PlaywrightWorkspaceSection(page, "left")
    left_section.expand_section()
    expect(task_page.get_review_all_panel()).to_have_count(0)
    expect(left_section.get_panel_tab("review-all")).to_have_count(0)

    # Review All is offered by — and opens through — the section's `+` dropdown.
    left_dropdown = PlaywrightAddPanelDropdownElement(page, "left")
    left_dropdown.open()
    expect(left_dropdown.get_panel_option("review-all")).to_be_visible()
    left_dropdown.select_panel("review-all")
    expect(left_section.get_panel_tab("review-all")).to_be_visible()
    expect(task_page.get_review_all_panel()).to_have_count(1)

    # Single-instance: while open, no section's dropdown offers it again — the
    # one already-open panel stays the only instance.
    left_dropdown.open()
    expect(left_dropdown.get_panel_option("review-all")).to_have_count(0)
    page.keyboard.press("Escape")

    center_dropdown = PlaywrightAddPanelDropdownElement(page, "center")
    center_dropdown.open()
    expect(center_dropdown.get_panel_option("review-all")).to_have_count(0)
    page.keyboard.press("Escape")

    expect(task_page.get_review_all_panel()).to_have_count(1)
