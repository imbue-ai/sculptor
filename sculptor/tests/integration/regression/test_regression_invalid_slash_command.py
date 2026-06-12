"""Regression test: Invalid slash commands should surface an error message to the user.

Bug: When a user sends an invalid slash command like "/fixbug" (instead of the valid
"/fix-bug"), Claude Code CLI recognizes it as a slash command attempt, fails to find
the matching skill, and returns a result message with "Unknown skill: fixbug". However,
Claude Code sets is_error=false in the result, and there are zero assistant messages.

Result: The user sees "thinking..." briefly (from RequestStartedAgentMessage), then
it disappears with no visible response because no ResponseBlockAgentMessage or
WarningAgentMessage is ever emitted. The result text "Unknown skill: fixbug" is silently
discarded in _parse_stream_end_response.

Root cause: ClaudeOutputProcessor._parse_stream_end_response only checks is_error to
decide whether to surface the result message. When is_error=false, the result text is
ignored even when there are no assistant messages in the turn.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see a warning when sending an invalid slash command")
def test_invalid_slash_command_surfaces_warning_to_user(sculptor_instance_: SculptorInstance) -> None:
    """Sending an invalid slash command should show a visible warning message.

    Uses the FakeClaude 'warning' command to simulate what happens when Claude Code
    receives an invalid slash command: no assistant message is emitted, only a result
    text that gets surfaced as a WarningAgentMessage.

    Steps:
    1. Create a task with FakeClaude and a simple prompt
    2. Wait for the initial exchange to complete
    3. Send a FakeClaude warning command simulating an invalid slash command
    4. Wait for the response
    5. Assert that a warning message containing "Unknown skill" is visible
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Hello, I am ready."}`',
    )

    # Wait for the initial exchange (user + assistant = 2 messages)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a follow-up that simulates an invalid slash command warning
    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:warning `{"message": "Unknown skill: fixbug"}`',
    )

    # Wait for the warning response: user message + assistant warning = 2 more messages = 4 total
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The last message should be an assistant message containing the warning
    messages = chat_panel.get_messages()
    warning_message = messages.nth(3)
    expect_message_to_have_role(message=warning_message, role=ElementIDs.ASSISTANT_MESSAGE)
    expect(warning_message).to_contain_text("Unknown skill")
