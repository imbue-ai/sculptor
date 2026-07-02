"""Integration tests for Task Page - Chatting functionality."""

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_2_MODEL_NAME
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("the contents of the prompt to survive page reloads and navigation")
def test_prompt_draft_persists_from_task_page(sculptor_instance_: SculptorInstance) -> None:
    """Test that the prompt draft persists when reloading the task page."""
    task_text = "Hello, this is a test message!"
    follow_up_text = "This is a follow-up message."

    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, prompt=task_text)

    task_page.get_chat_panel().get_chat_input().fill(follow_up_text)

    soft_reload_page(task_page)
    expect(task_page.get_chat_panel().get_chat_input()).to_have_text(follow_up_text)


@user_story("the contents of the prompt to survive page reloads and navigation")
def test_prompt_drafts_persist_on_multiple_tasks_and_home_page(sculptor_instance_: SculptorInstance) -> None:
    """Test that prompt drafts persist when navigating between workspace tabs."""
    page = sculptor_instance_.page
    follow_up_text = "This is a follow-up message draft."

    task_page = start_task_and_wait_for_ready(page, prompt="Hello, this is a test message!")
    chat_panel = task_page.get_chat_panel()

    # Type a follow-up message draft in chat input (don't send it)
    chat_panel.get_chat_input().fill(follow_up_text)

    # The sidebar's new-workspace button direct-creates from the last-used
    # settings; use the add-workspace surface opener, which deterministically
    # brings up the create form (and its create button) for this navigate-away
    # step. The point of this step is to leave workspace 1 and come back to it.
    navigate_to_add_workspace_page(page)
    add_workspace_page = PlaywrightAddWorkspacePage(page=page)
    expect(add_workspace_page.get_submit_button()).to_be_visible()

    navigate_to_workspace(page)
    expect(task_page.get_chat_panel()).to_be_visible()

    task_page = PlaywrightTaskPage(page=page)
    expect(task_page.get_chat_panel().get_chat_input()).to_have_text(follow_up_text)


@user_story("to have a multi-turn conversation with the agent")
def test_starting_text(sculptor_instance_: SculptorInstance) -> None:
    """Test that the text for a task appears in the chat after it is started."""
    task_text = "Say hello to me!"

    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, prompt=task_text)
    chat_panel = task_page.get_chat_panel()

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    messages = chat_panel.get_messages()
    expect_message_to_have_role(message=messages.nth(0), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(0)).to_contain_text(task_text)


@user_story("to have a multi-turn conversation with the agent")
def test_send_message_after_task_start(sculptor_instance_: SculptorInstance) -> None:
    """Test that users can send messages after task starts, and the assistant responds."""

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="Hello, this is a test message! Please respond briefly!",
    )
    chat_panel = task_page.get_chat_panel()

    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_have_text("")

    send_chat_message(chat_panel=chat_panel, message="This is a second test message! Please respond briefly!")

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    messages = chat_panel.get_messages()

    expect_message_to_have_role(message=messages.nth(0), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(0)).to_contain_text("Hello, this is a test message! Please respond briefly!")

    expect_message_to_have_role(message=messages.nth(2), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(2)).to_contain_text("This is a second test message! Please respond briefly!")


@user_story("to have a multi-turn conversation with the agent")
def test_send_multiple_messages(sculptor_instance_: SculptorInstance) -> None:
    """Test sending multiple messages in a conversation."""

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="Hello this is test message one of three! Please respond briefly!",
    )
    chat_panel = task_page.get_chat_panel()

    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_have_text("")

    send_chat_message(
        chat_panel=chat_panel, message="Hello this is test message two of three! Please respond briefly!"
    )

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    send_chat_message(
        chat_panel=chat_panel, message="Hello this is test message three of three! Please respond briefly!"
    )

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6)

    messages = chat_panel.get_messages()
    expect_message_to_have_role(message=messages.nth(0), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(0)).to_contain_text("Hello this is test message one of three! Please respond briefly!")

    expect_message_to_have_role(message=messages.nth(2), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(2)).to_contain_text("Hello this is test message two of three! Please respond briefly!")

    expect_message_to_have_role(message=messages.nth(4), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(4)).to_contain_text("Hello this is test message three of three! Please respond briefly!")


@pytest.mark.skip(reason="Flaky: timing issue where 3rd message may be processed before deletion")
@user_story("to have a multi-turn conversation with the agent")
def test_remove_queued_message_and_continue(sculptor_instance_: SculptorInstance) -> None:
    """Test remove queued message and continue."""

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="Hello this is test message one of four! Please respond briefly!",
    )
    chat_panel = task_page.get_chat_panel()

    # Queue a message while assistant is still responding to first message
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_have_text("")
    chat_input.fill("Hello this is test message two of four! Please respond briefly!")
    chat_panel.get_send_button().click()
    expect(chat_panel.get_messages()).to_have_count(3)

    chat_input.fill("Hello this is test message three of four! Please respond briefly!")
    chat_panel.get_send_button().click()

    # Delete the queued message before it's processed; we get the last since it's non-deterministic whether the first message has been sent
    delete_queued_message_button = chat_panel.get_delete_queued_message_button().last
    delete_queued_message_button.click()

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)

    chat_input.fill("Hello this is test message four of four! Please respond briefly!")
    chat_panel.get_send_button().click()

    messages = chat_panel.get_messages()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6)
    expect_message_to_have_role(message=messages.nth(0), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(0)).to_contain_text("Hello this is test message one of four! Please respond briefly!")

    expect_message_to_have_role(message=messages.nth(2), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(2)).to_contain_text("Hello this is test message two of four! Please respond briefly!")

    expect_message_to_have_role(message=messages.nth(4), role=ElementIDs.USER_MESSAGE)
    expect(messages.nth(4)).to_contain_text("Hello this is test message four of four! Please respond briefly!")


@user_story("to control the model used by the agent")
def test_model_selection(sculptor_instance_: SculptorInstance) -> None:
    """Test that models can be selected and used in a conversation.

    Uses the two FakeClaude models to verify the model selector UI works:
    selecting a different model and sending a message uses that model.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Hello from Fake Claude"}`',
        model_name=FAKE_CLAUDE_MODEL_NAME,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    model_selector = chat_panel.get_model_selector()
    expect(model_selector).to_be_visible()

    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_2_MODEL_NAME)

    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:text `{"text": "Hello from Fake Claude 2"}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    expect(model_selector).to_contain_text("Fake Claude 2", ignore_case=True)

    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)

    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:text `{"text": "Hello from Fake Claude again"}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6)

    expect(model_selector).to_contain_text("Fake Claude", ignore_case=True)


@user_story("to preserve the correct model when switching between tasks")
def test_model_selector_updates_when_switching_tasks(sculptor_instance_: SculptorInstance) -> None:
    """Test that the model selector displays the correct model when navigating between workspace tabs."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Task 1 response"}`',
        model_name=FAKE_CLAUDE_MODEL_NAME,
    )

    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Task 2 response"}`',
        model_name=FAKE_CLAUDE_2_MODEL_NAME,
    )

    # We should now be on the second workspace tab; verify its model
    second_task_page = PlaywrightTaskPage(page=page)
    second_chat_panel = second_task_page.get_chat_panel()
    model_selector = second_chat_panel.get_model_selector()
    expect(model_selector).to_be_visible()
    expect(model_selector).to_contain_text("Fake Claude 2", ignore_case=True)

    navigate_to_workspace(page)
    first_task_page = PlaywrightTaskPage(page=page)
    first_chat_panel = first_task_page.get_chat_panel()
    expect(first_chat_panel).to_be_visible()
    model_selector = first_chat_panel.get_model_selector()
    expect(model_selector).to_be_visible()
    expect(model_selector).to_contain_text("Fake Claude", ignore_case=True)


@pytest.mark.skip(reason="Skipped: context indicator redesigned from progress bar to SVG arc")
@user_story("to expect compaction to increase the remaining context left")
def test_compaction(sculptor_instance_: SculptorInstance) -> None:
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="Say 20 random words for testing",
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    compaction_header = task_page.get_compaction_bar()
    _initial_context_remaining = compaction_header.get_context_remaining()
    compaction_header.click()
    compaction_panel = task_page.get_compaction_panel()
    compaction_panel.get_compaction_button().click()

    expect(compaction_header).to_contain_text("Compacting...")
    expect(compaction_header).to_contain_text("Context Remaining")
    expect(chat_panel.get_context_summary_messages()).to_have_count(1)
    _final_context_remaining = compaction_header.get_context_remaining()
