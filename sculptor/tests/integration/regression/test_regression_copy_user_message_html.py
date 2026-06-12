"""Regression test: Copy user message with mention copies raw HTML instead of plain text.

Bug: When a user message contains TipTap Mention nodes (file references like @README.md),
clicking the copy button on the user message copies the raw HTML markup
(<span data-type="mention" class="..." data-id="...">) instead of the visible plain text.

Root cause: The handleCopy function in UserMessage directly copies block.text (which
contains TipTap's HTML-serialized mention nodes) without stripping the HTML tags.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _send_message_with_mention(chat_panel) -> None:
    """Type @ to trigger the file mention suggestion UI, select a file, and send.

    Exercises the real TipTap suggestion flow: typing @ opens the file suggestion
    popup, clicking a suggestion inserts a Mention node. When getMarkdown()
    serializes this on submit, it produces HTML <span> tags for the mention —
    exactly the scenario that triggers the copy bug.
    """
    chat_input = chat_panel.get_chat_input()
    type_trigger_char(chat_input, "@")
    suggestion = chat_panel.get_mention_items().filter(has_text="README.md")
    expect(suggestion).to_be_visible()
    suggestion.click()
    chat_panel.get_send_button().click()
    expect(chat_input).to_have_text("")


@user_story("to copy a user message with a mention and get plain text, not HTML")
def test_copy_user_message_with_mention_copies_plain_text(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking copy on a user message with a mention should copy plain text, not HTML.

    Steps:
    1. Create a workspace with a FakeClaude response
    2. Send a follow-up message containing a TipTap Mention node (via @ suggestion)
    3. Install a clipboard interceptor
    4. Click the copy button on the user message
    5. Assert the clipboard contains plain text without HTML tags or attributes
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Initial response"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a follow-up message containing a Mention node.
    _send_message_with_mention(chat_panel=chat_panel)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Install a clipboard interceptor so we can read what was written.
    install_clipboard_interceptor(page)

    # Locate the second user message (index 2: user0, assistant0, user1, assistant1).
    messages = chat_panel.get_messages()
    expect(messages).to_have_count(4)
    user_message = messages.nth(2)

    # Click the copy button on the user message.
    copy_button = chat_panel.get_message_copy_button(user_message)
    expect(copy_button).to_be_visible()
    copy_button.click()

    # Verify the clipboard contains plain text, not raw HTML.
    clipboard_value = read_intercepted_clipboard(page)
    assert clipboard_value is not None, "Clipboard should contain a value after clicking copy"
    assert "<span" not in clipboard_value, f"Clipboard contains raw HTML markup: {clipboard_value}"
    assert "data-type" not in clipboard_value, f"Clipboard contains HTML data attributes: {clipboard_value}"
    assert "README.md" in clipboard_value, f"Expected mention text 'README.md' in clipboard: {clipboard_value}"
