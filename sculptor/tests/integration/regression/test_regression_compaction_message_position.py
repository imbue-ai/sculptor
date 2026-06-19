"""Regression test: Post-compaction message should appear after the context summary.

Bug: When auto-compaction happens mid-turn, the in-progress message is flushed
to completedChatMessages with its first_response_message_id as the ChatMessage
ID. Post-compaction streaming reuses the same ID for the new in-progress
message. At finalization, mergeAndDeduplicateMessages updates the content but
keeps the message at its original (compaction-time) position instead of at the
bottom. The user sees the post-compaction message disappear from the chat.

Root cause: first_response_message_id in output_processor.py is only reset in
_parse_init_response (new CLI session), never after compaction.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see post-compaction messages at the bottom of the chat, not merged into a pre-compaction position")
def test_post_compaction_message_appears_after_context_summary(sculptor_instance_: SculptorInstance) -> None:
    """Post-compaction response text should appear below the context summary, not at the pre-compaction position.

    Steps:
    1. Start a task with auto_compact_mid_stream which emits text, triggers
       compaction, then emits more text — all in a single CLI turn.
    2. Wait for the agent to finish.
    3. Verify the context summary appears.
    4. Verify the post-compaction message appears AFTER the context summary
       as a separate assistant message.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:auto_compact_mid_stream `{"pre_text": "Pre-compaction content.", "post_text": "Post-compaction content.", "delay_seconds": 0.5}`',
    )

    chat_panel = task_page.get_chat_panel()

    # Expected messages (via get_messages which filters for USER/ASSISTANT):
    #   0: user message (the prompt)
    #   1: pre-compaction assistant message
    #   2: context summary (rendered as assistant message)
    #   3: post-compaction assistant message (should be a SEPARATE message)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    context_summary = chat_panel.get_context_summary_messages()
    expect(context_summary.first).to_be_visible()

    messages = chat_panel.get_messages()

    expect_message_to_have_role(message=messages.nth(0), role=ElementIDs.USER_MESSAGE)

    expect_message_to_have_role(message=messages.nth(1), role=ElementIDs.ASSISTANT_MESSAGE)
    expect(messages.nth(1)).to_contain_text("Pre-compaction content")

    # Message 3: post-compaction assistant message (MUST be separate from message 1)
    # (Message 2 is the context summary rendered as an assistant message)
    expect_message_to_have_role(message=messages.nth(3), role=ElementIDs.ASSISTANT_MESSAGE)
    expect(messages.nth(3)).to_contain_text("Post-compaction content")

    # The pre-compaction message must NOT contain post-compaction text
    # (which would happen if they shared the same ChatMessage ID)
    expect(messages.nth(1)).not_to_contain_text("Post-compaction content")
