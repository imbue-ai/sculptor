"""Integration tests for slash command error messages.

Verifies that:
- TUI-only Claude Code commands (e.g. /memory) show a clear message that
  the command is not available in Sculptor, rather than the misleading
  "Unknown skill" error.
- Truly unknown commands (e.g. /fixbug) show the original "Unknown skill"
  message without a misleading upgrade suggestion.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see a clear message when using a TUI-only Claude Code command")
def test_tui_only_command_shows_not_available_message(sculptor_instance_: SculptorInstance) -> None:
    """A TUI-only command like /memory should tell the user it's not available in Sculptor.

    When Claude Code returns "Unknown skill: memory" for a command that exists
    but requires a TUI, the warning message should explain that the command is
    not available in Sculptor — not suggest upgrading Claude Code.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready."}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Simulate Claude Code returning "Unknown skill: memory" for a TUI-only command
    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:warning `{"message": "Unknown skill: memory"}`',
    )

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    warning_message = chat_panel.get_messages().nth(3)
    expect_message_to_have_role(message=warning_message, role=ElementIDs.ASSISTANT_MESSAGE)
    expect(warning_message).to_contain_text("not available in Sculptor")
    expect(warning_message).not_to_contain_text("upgrade")


@user_story("to see a plain error when using a truly unknown slash command")
def test_unknown_command_shows_plain_unknown_skill_message(sculptor_instance_: SculptorInstance) -> None:
    """A truly unknown command like /fixbug should show 'Unknown skill' without upgrade suggestion.

    The upgrade suggestion is misleading since upgrading Claude Code won't help
    with a genuinely unknown command.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready."}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Simulate Claude Code returning "Unknown skill: fixbug" for a truly unknown command
    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:warning `{"message": "Unknown skill: fixbug"}`',
    )

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    warning_message = chat_panel.get_messages().nth(3)
    expect_message_to_have_role(message=warning_message, role=ElementIDs.ASSISTANT_MESSAGE)
    expect(warning_message).to_contain_text("Unknown skill: fixbug")
    expect(warning_message).not_to_contain_text("upgrade")
