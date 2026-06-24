"""Integration tests for the universal picker-dismissal contract.

The chat input hosts four mention pickers — ``@`` (files), ``/`` (skills),
``+`` (prefilter), and the entity sub-picker drilled in from ``+`` — that
all share dismissal semantics:

  1. Pressing Escape closes the popover.
  2. Erasing the trigger character (Backspace right after typing it) closes
     the popover.
  3. Clicking outside the chat input closes the popover.

This file fills coverage gaps that the per-trigger test files don't cover:
``test_at_mention_completion.py`` only asserts the Escape path for ``@``;
``test_skill_autocomplete.py`` doesn't assert any dismissal path; and the
click-outside path is not exercised anywhere else.

These behaviors live behind ``SuggestionDismissalPlugin`` (which prevents
re-opens at dismissed positions, see ``SuggestionDismissalPlugin.test.ts``)
and the suggestion plugin's keystroke handlers, so a regression here would
silently keep the popover stuck open or pop it back up after the user has
explicitly closed it.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


@user_story("to dismiss the @-mention picker by erasing the trigger character")
def test_at_backspace_at_trigger_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    chat_input.press_sequentially("@")
    expect(chat_panel.get_mention_list()).to_be_visible()

    chat_input.press("Backspace")

    expect(chat_panel.get_mention_list()).not_to_be_visible()


@user_story("to dismiss the /-skill picker by pressing Escape")
def test_slash_escape_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    chat_input.press_sequentially("/")
    expect(chat_panel.get_mention_list()).to_be_visible()

    chat_input.press("Escape")

    expect(chat_panel.get_mention_list()).not_to_be_visible()


@user_story("to dismiss the /-skill picker by erasing the trigger character")
def test_slash_backspace_at_trigger_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    chat_input.press_sequentially("/")
    expect(chat_panel.get_mention_list()).to_be_visible()

    chat_input.press("Backspace")

    expect(chat_panel.get_mention_list()).not_to_be_visible()


def _click_outside_chat_input(task_page: PlaywrightTaskPage) -> None:
    """Click a stable element at the top of the task page that lives outside
    the chat input's DOM. The picker's document-level pointerdown listener
    (capture phase) will see the event and tear the popover down.

    Uses the active workspace row as the click target — it sits at the top of
    the window and is reliably present in any task-page test. Clicking the
    already-active row is a navigation no-op, so the only side effect is the
    pointerdown the picker is listening for."""
    navigate_to_workspace(task_page)


@user_story("to dismiss the @-mention picker by clicking outside the editor")
def test_at_click_outside_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    chat_input.press_sequentially("@")
    expect(chat_panel.get_mention_list()).to_be_visible()

    _click_outside_chat_input(task_page)

    expect(chat_panel.get_mention_list()).not_to_be_visible()


@user_story("to dismiss the /-skill picker by clicking outside the editor")
def test_slash_click_outside_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    chat_input.press_sequentially("/")
    expect(chat_panel.get_mention_list()).to_be_visible()

    _click_outside_chat_input(task_page)

    expect(chat_panel.get_mention_list()).not_to_be_visible()


@user_story("to dismiss the + prefilter picker by clicking outside the editor")
def test_plus_click_outside_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    chat_input.press_sequentially("+")
    expect(chat_panel.get_mention_list()).to_be_visible()

    _click_outside_chat_input(task_page)

    expect(chat_panel.get_mention_list()).not_to_be_visible()
