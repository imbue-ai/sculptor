"""Regression tests for prompt input placeholder behavior.

The TipTap Placeholder extension must only show "Enter a prompt..." when the
editor is logically empty.  These tests cover two known regressions:

1. **ZWSP leak after message send** — CustomParagraph serializes empty
   paragraphs as \\u200B (zero-width space).  Without normalization in the
   ``onUpdate`` callback, this value leaks into the prompt-draft atom in
   localStorage and can cause placeholder/suggestion failures on reload.

2. **Placeholder on empty paragraph within content** — With
   ``showOnlyCurrent: false``, the Placeholder extension renders on *every*
   empty paragraph, including empty lines within multi-paragraph content.
   Pressing Enter at the start of text creates an empty first paragraph that
   incorrectly shows the placeholder even though the editor has content.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.base import get_tiptap_placeholder_paragraphs
from sculptor.testing.elements.base import type_paragraphs_into_tiptap
from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Zero-width space character — what CustomParagraph serializes empty paragraphs as.
ZWS = "\u200b"

PLACEHOLDER_TEXT = "Enter a prompt..."


def _get_agent_id_from_url(url: str) -> str:
    match = re.search(r"/agent/([^/?#]+)", url)
    assert match, f"Could not extract agent ID from URL: {url}"
    return match.group(1)


@user_story("to see the placeholder and slash suggestions after reloading a workspace")
def test_placeholder_and_slash_suggestions_survive_reload(sculptor_instance_: SculptorInstance) -> None:
    """Placeholder and / suggestions must work after sending a message and reloading.

    Verifies that the zero-width space emitted by CustomParagraph's markdown
    serializer does not leak into localStorage and cause issues on page reload.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a follow-up to trigger clearContent -> onUpdate -> getMarkdown()
    send_chat_message(chat_panel, "follow-up message")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Verify \u200B did NOT leak into localStorage after the debounced write
    agent_id = _get_agent_id_from_url(page.url)
    draft_key = f"sculptor-prompt-draft-{agent_id}"
    page.wait_for_function(
        """([key, zws]) => {
            const val = window.localStorage.getItem(key);
            return val !== zws;
        }""",
        arg=[draft_key, ZWS],
    )

    # Reload the page to recreate the editor from localStorage
    soft_reload_page(page)
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # Editor should be empty (no visible text content)
    expect(chat_input).to_have_text("")

    # "/" must open the skill-suggestion popover
    type_trigger_char(chat_input, "/")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()


@user_story("to not see the placeholder when the editor has content")
def test_placeholder_hidden_when_editor_has_content(sculptor_instance_: SculptorInstance) -> None:
    """Placeholder must not appear on empty paragraphs within non-empty content.

    When the user types text, moves the cursor to the beginning, and presses
    Enter, TipTap creates an empty first paragraph above the text.  The
    placeholder should NOT show on that empty paragraph because the editor
    still has content.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()

    # Build the regressed document: an empty first paragraph above real content —
    # the state a user reaches by pressing Enter at the start of their text.
    #
    # We assemble it with editor commands rather than a literal
    # ``page.keyboard.press("Enter")``. The integration harness binds
    # ``send_message`` to Enter, so a raw Enter keystroke here submits the draft
    # and clears the editor instead of splitting the paragraph. An empty editor
    # then renders the placeholder (``editor.isEmpty`` is true), which is exactly
    # the false failure this test used to hit. ``type_paragraphs_into_tiptap``
    # drives ``editor.commands.enter()``, which bypasses the send keybinding.
    type_paragraphs_into_tiptap(chat_input, ["", "hello world"])
    expect(chat_input).to_contain_text("hello world")

    # The placeholder text must NOT appear on the empty first paragraph: the
    # editor has content, so ``editor.isEmpty`` is false and the Placeholder
    # extension emits ``data-placeholder=""`` there instead of the prompt text.
    placeholder_paragraphs = get_tiptap_placeholder_paragraphs(chat_input, PLACEHOLDER_TEXT)
    expect(placeholder_paragraphs).to_have_count(0)
