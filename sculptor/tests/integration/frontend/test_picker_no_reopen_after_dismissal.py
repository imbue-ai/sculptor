"""Integration tests for picker re-open suppression after explicit dismissal.

The ``SuggestionDismissalPlugin`` (unit-tested in
``SuggestionDismissalPlugin.test.ts``) records the position of any trigger
character the user has explicitly dismissed and prevents the suggestion plugin
from popping a fresh popover at that same position. Without it, the popover
would reopen as soon as the user typed the next character or moved the cursor
back into the trigger range — undoing the dismissal the user just performed.

The unit tests cover the plugin's state-machine in isolation. These tests
exercise the same contract through the real chat input editor so that a
regression in the plugin's wiring (suggestion config not honoring the
dismissal predicate, doc-change pruning racing the new keystroke) is caught
end-to-end.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


@user_story("to keep the @-picker closed after dismissing it, even when typing more characters at the same trigger")
def test_at_picker_stays_closed_when_typing_more_after_escape(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After Esc dismisses the @-picker, typing more letters of the query
    must NOT reopen the popover at the same trigger position.

    Without ``SuggestionDismissalPlugin``, the suggestion plugin would notice
    that the cursor is again in the range of an active trigger and pop the
    popover open on the next keystroke — defeating the user's explicit
    dismissal.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    picker = chat_panel.get_mention_list()

    chat_input.press_sequentially("@src")
    expect(picker).to_be_visible()

    chat_input.press("Escape")
    expect(picker).not_to_be_visible()

    # Type more letters. The cursor is still within the @ trigger range, so
    # without the dismissal plugin the suggestion plugin would pop the
    # popover open on every keystroke.
    chat_input.press_sequentially("abc")
    expect(picker).not_to_be_visible()


@user_story("to reopen the picker at a fresh trigger position after dismissing an earlier one")
def test_at_picker_reopens_at_fresh_trigger_position(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Dismissing one ``@`` does not block a different ``@`` later in the line.

    The dismissal is positional: only the exact position the user dismissed is
    suppressed. Typing a new ``@`` somewhere else creates a brand-new trigger
    that has no dismissal record and must open as normal.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    picker = chat_panel.get_mention_list()

    # First trigger — open and dismiss.
    chat_input.press_sequentially("@src")
    expect(picker).to_be_visible()
    chat_input.press("Escape")
    expect(picker).not_to_be_visible()

    # Type some intervening text and a fresh ``@`` at a new position. The new
    # trigger must open the picker because its position has no dismissal.
    chat_input.press_sequentially(" hello @")
    expect(picker).to_be_visible()


@user_story("to keep the +-picker closed after dismissing it, even when typing more characters at the same trigger")
def test_plus_picker_stays_closed_when_typing_more_after_escape(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The dismissal contract is identical for the ``+`` prefilter picker.

    The ``+`` picker drives the entity sub-picker, so a regression in
    dismissal handling here would cascade into the entity-mention flow as
    well.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    picker = chat_panel.get_mention_list()

    chat_input.press_sequentially("+wor")
    expect(picker).to_be_visible()

    chat_input.press("Escape")
    expect(picker).not_to_be_visible()

    chat_input.press_sequentially("kspace")
    expect(picker).not_to_be_visible()


@user_story("to keep the /-picker closed after dismissing it, even when typing more characters at the same trigger")
def test_slash_picker_stays_closed_when_typing_more_after_escape(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Symmetric guard for the ``/`` skill picker."""
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    picker = chat_panel.get_mention_list()

    chat_input.press_sequentially("/skill")
    expect(picker).to_be_visible()

    chat_input.press("Escape")
    expect(picker).not_to_be_visible()

    chat_input.press_sequentially("more")
    expect(picker).not_to_be_visible()
