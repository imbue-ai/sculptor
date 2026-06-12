"""Regression test: Simple follow-up messages should not produce spurious warning blocks.

Bug: When a user sends a simple follow-up message like "hello" during streaming mode
(the default), the agent responds normally but a "Warning" block also appears in the
response. This happens because ClaudeOutputProcessor._parse_stream_end_response checks
self.last_assistant_message to decide whether to surface the result text as a warning
(for cases like unrecognized slash commands). However, self.last_assistant_message is
only set in the non-streaming code path (_parse_assistant_response), so in streaming
mode it's always None — causing every non-empty ParsedEndResponse.result to be emitted
as a spurious WarningAgentMessage.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to send a simple follow-up message without seeing a spurious warning")
def test_simple_followup_does_not_produce_warning_block(sculptor_instance_: SculptorInstance) -> None:
    """Sending a simple follow-up message should produce a normal response with no warning.

    Steps:
    1. Create a task with a simple prompt
    2. Wait for the initial exchange to complete
    3. Send "hello" as a follow-up message
    4. Wait for the response
    5. Assert that exactly 4 messages are present (no extra warning message)
    6. Assert that the follow-up assistant response does not contain a warning block
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="Say hello briefly",
    )

    # Wait for initial exchange (user + assistant = 2 messages)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a simple follow-up message
    send_chat_message(chat_panel=chat_panel, message="hello")

    # Wait for the follow-up response: user + assistant = 2 more messages = 4 total
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The follow-up assistant response should be a normal assistant message
    messages = chat_panel.get_messages()
    followup_response = messages.nth(3)
    expect_message_to_have_role(message=followup_response, role=ElementIDs.ASSISTANT_MESSAGE)

    # The response should NOT contain a "Warning" badge/block.
    # The SystemWarningBlock renders a Badge with "Warning" text, so checking for
    # absence of that text in the response confirms no warning block was added.
    expect(followup_response).not_to_contain_text("Warning")
