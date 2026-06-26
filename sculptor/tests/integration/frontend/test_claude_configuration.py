"""Integration tests for the Claude configuration functionality."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.backend_contract import CLAUDE_COMMANDS_DIRECTORY_NAME
from sculptor.testing.backend_contract import CLAUDE_JSON_FILENAME
from sculptor.testing.backend_contract import CLAUDE_LOCAL_SETTINGS_FILENAME
from sculptor.testing.backend_contract import CLAUDE_SESSION_DIRECTORY_NAME
from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

CLAUDE_DIRECTORY = CLAUDE_SESSION_DIRECTORY_NAME
COMMANDS_DIRECTORY = CLAUDE_COMMANDS_DIRECTORY_NAME


@pytest.mark.skip(reason="Moving away from Docker-based task environments")
@user_story("local claude settings are respected in tasks")
def test_claude_settings_propagate_from_users_computer_to_container(sculptor_instance_: SculptorInstance) -> None:
    """Test that modifications of local claude settings get propagated to the container."""
    TEST_FILE_NAME = "test_file.py"
    HELLO_WORLD_CONTENT = 'print("hello world")'
    CREATE_FILE_PROMPT = f"Create a file called {TEST_FILE_NAME} with content '{HELLO_WORLD_CONTENT}'. Do NOT commit."
    LOCAL_SETTINGS_FILENAME = str(Path(CLAUDE_DIRECTORY) / CLAUDE_LOCAL_SETTINGS_FILENAME)

    sculptor_instance_.repo.write_file(".gitignore", ".claude/settings.local.json")
    sculptor_instance_.repo.commit(".gitignore commit", commit_time="2025-01-01T00:00:02")
    sculptor_instance_.repo.write_file(LOCAL_SETTINGS_FILENAME, "{}")

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt=CREATE_FILE_PROMPT,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    task_page.verify_uncommitted_file(file_name=TEST_FILE_NAME, expected_content=HELLO_WORLD_CONTENT)

    # 2. Update the settings to clean uncommited changes after each tool use.
    GIT_CLEAN_HOOK = """
        {
          "hooks": {
            "PreToolUse": [
              {
                "matcher": "*",
                "hooks": [
                  {
                    "type": "command",
                    "command": "git clean -f",
                    "timeout": 8
                  }
                ]
              }
            ]
          }
        }
    """
    sculptor_instance_.repo.write_file(LOCAL_SETTINGS_FILENAME, GIT_CLEAN_HOOK)

    # 3. Trigger tool use and verify that the hook defined in the settings got executed inside the container.
    send_chat_message(
        chat_panel=chat_panel,
        message="What is the number of environment variables in the current process?",
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
    task_page.verify_uncommitted_file_count(0)


@pytest.mark.skip(reason="Re-examine after LocalEnvironment refactor")
@user_story("local claude custom slash commands can be used from the frontend")
def test_claude_custom_slash_commands_can_be_used(sculptor_instance_: SculptorInstance) -> None:
    """Test that custom slash commands defined in a local claude directory can be used from the frontend, including arguments."""
    SLASH_COMMAND_FILENAME = str(Path(CLAUDE_DIRECTORY) / COMMANDS_DIRECTORY / "count.md")
    SLASH_COMMAND_DEFINITION = "What is the number of $1 $2 in the current process?"
    sculptor_instance_.repo.write_file(SLASH_COMMAND_FILENAME, SLASH_COMMAND_DEFINITION)

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="/count environment variables",
    )

    chat_panel = task_page.get_chat_panel()
    messages = chat_panel.get_messages()
    agent_message = messages.nth(1)
    expect_message_to_have_role(message=agent_message, role=ElementIDs.ASSISTANT_MESSAGE)
    expect(agent_message).to_contain_text("current process")


@pytest.mark.skip(reason="Re-examine after LocalEnvironment refactor")
@user_story("unknown slash commands result in a warning")
def test_claude_unknown_slash_commands_result_in_a_warning(sculptor_instance_: SculptorInstance) -> None:
    """Test that custom slash commands defined in a local claude directory can be used from the frontend."""
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="Say hi to me",
    )

    chat_panel = task_page.get_chat_panel()

    send_chat_message(
        chat_panel=chat_panel,
        message="/unknown_command",
    )

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
    messages = chat_panel.get_messages()
    agent_message = messages.nth(3)
    expect_message_to_have_role(message=agent_message, role=ElementIDs.ASSISTANT_MESSAGE)
    expect(agent_message).to_contain_text("Warning")
    expect(agent_message).to_contain_text("Invalid slash command")


@pytest.mark.skip(reason="Re-examine after LocalEnvironment refactor")
@user_story("local claude configuration changes are picked up after restart")
def test_claude_configuration_changes_are_picked_up_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory, tmp_path: Path
) -> None:
    """Test that modifications of local claude settings get propagated to the container after a restart."""

    slash_command_filename = tmp_path / CLAUDE_DIRECTORY / COMMANDS_DIRECTORY / "count.md"
    slash_command_filename.parent.mkdir(parents=True, exist_ok=True)
    slash_command_filename.write_text("What is the number of env vars in the current process?")
    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(
            instance.page,
            prompt="Say hi to me",
        )
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    slash_command_filename = tmp_path / CLAUDE_DIRECTORY / COMMANDS_DIRECTORY / "day_of_the_week.md"
    slash_command_filename.parent.mkdir(parents=True, exist_ok=True)
    slash_command_filename.write_text("What is the current day of the week?")
    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = PlaywrightTaskPage(page=instance.page)
        # Navigate to workspace tab to access the existing task
        workspace_tab = task_page.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible()
        send_chat_message(
            chat_panel=chat_panel,
            # We don't need an actual response from Claude; the purpose is just to wait until the messages are processed.
            message="/non_existing_command",
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
        chat_input = chat_panel.get_chat_input()
        # This actually also tests that the mention component works and shows the new slash command.
        mention_list = chat_panel.get_mention_list()
        expect(mention_list).not_to_be_visible()
        type_trigger_char(chat_input, "/")
        expect(mention_list).to_be_visible()
        expect(mention_list).to_contain_text("day_of_the_week")


@pytest.mark.skip(reason="Moving away from Docker-based task environments")
@user_story("claude mcp server settings from the users machine are respected in tasks")
def test_claude_mcp_server_settings_propagate_from_users_computer_to_container(
    sculptor_instance_: SculptorInstance, tmp_path: Path
) -> None:
    claude_json_path = tmp_path / CLAUDE_JSON_FILENAME
    assert not claude_json_path.exists()
    claude_config = {
        "numStartups": 3,
        "theme": "light",
        "customApiKeyResponses": {
            "approved": [],
            "rejected": [],
        },
        "firstStartTime": "2025-06-10T21:50:05.520Z",
        "projects": {},
        "isQualifiedForDataSharing": False,
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "1.0.17",
        "recommendedSubscription": "",
        "subscriptionNoticeCount": 0,
        "hasAvailableSubscription": False,
        # This is the important part (the rest above is here only because it seems to be required).
        "mcpServers": {
            "dummy": {
                "type": "http",
                "url": "https://example.com",
            }
        },
    }
    claude_json_path.write_text(json.dumps(claude_config))

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        # We don't actually want claude to use the listmcpresources tool because that sends requests to the mcp server.
        prompt="Looking at /root/.claude.json, tell me which mcp servers are currently configured.",
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    messages = chat_panel.get_messages()
    agent_message = messages.nth(1)
    expect(agent_message).to_contain_text("dummy")
