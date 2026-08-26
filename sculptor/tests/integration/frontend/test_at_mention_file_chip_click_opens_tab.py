"""Tests that clicking a rendered file @-mention chip opens the file in the viewer.

When a user sends a message with a file mention and later clicks the rendered
chip, the single embedded diff viewer must open showing that file's content.
This exercises the full pipeline: MentionChip click → openFileViewTabAtom →
diffPanelStateAtom.activeTabPath → the host panel's embedded DiffViewer.

Counterpart to ``test_folder_chip_click_reveals_folder_in_file_browser`` in
``test_alpha_chat_chip_rendering.py`` (folder chips reveal in the file
browser) — this covers the *file* branch of the same component.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )


@user_story("to open a file in the diff panel by clicking its @-mention chip")
def test_file_chip_click_opens_file_view(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()

    # Insert a file @-mention for stuff.txt (exists at repo root in the test
    # fixture).  Using Enter on a file commits the chip.
    chat_input.press_sequentially("@stuff")
    expect(mention_list).to_be_visible()
    # Wait for at least one item to render before pressing Enter, otherwise
    # the keypress no-ops against an empty items list.
    expect(chat_panel.get_mention_items().first).to_be_visible()
    page.keyboard.press("Enter")
    expect(mention_list).not_to_be_visible()

    # Sanity: the chip is in the editor before we send.
    editor_chip = chat_panel.get_mention_spans()
    expect(editor_chip).to_be_visible()
    expect(editor_chip).to_contain_text("stuff")

    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    latest_user_message = alpha_view.get_user_messages().last
    rendered_chip = latest_user_message.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(rendered_chip).to_be_visible()
    expect(rendered_chip).to_contain_text("stuff")

    # Clicking the rendered file chip in history must open the diff panel
    # showing stuff.txt in the single embedded viewer.
    rendered_chip.click()

    # The viewer header shows the basename and the read-only preview renders
    # the file content.
    task_page.get_diff_panel().expect_shows_file("stuff.txt")


@user_story("to open the correct file even when the chip is inside a nested folder path")
def test_nested_file_chip_click_opens_correct_file(sculptor_instance_: SculptorInstance) -> None:
    """A deeply-nested file chip opens the viewer on just the basename.

    ``src/app.py`` is a file nested one level down in the test fixture.  The
    chip shows ``app.py`` (the basename), and the viewer header breadcrumb
    also shows ``app.py`` — both refer to the same path.
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()

    chat_input.press_sequentially("@app.py")
    expect(mention_list).to_be_visible()
    # Wait for the exact file to surface. Other py files in the fixture also
    # match "app.py" fuzzy, but app.py itself should rank first.
    expect(mention_list).to_contain_text("app.py")
    expect(chat_panel.get_mention_items().first).to_be_visible()
    page.keyboard.press("Enter")
    expect(mention_list).not_to_be_visible()

    editor_chip = chat_panel.get_mention_spans()
    expect(editor_chip).to_be_visible()
    expect(editor_chip).to_contain_text("app.py")

    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    latest_user_message = alpha_view.get_user_messages().last
    rendered_chip = latest_user_message.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(rendered_chip).to_be_visible()
    rendered_chip.click()

    task_page.get_diff_panel().expect_shows_file("app.py")
