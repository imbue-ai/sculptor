"""Integration tests for the AskUserQuestion feature in the legacy (classic) chat view.

Tests the full flow: agent invokes AskUserQuestion tool, Q&A panel appears,
user selects answers and submits, agent receives the answers and continues.

These tests run on the legacy (classic) chat view to maintain coverage of the
classic rendering path.  The alpha-specific rendering is tested separately in
``test_alpha_ask_user_question.py``.
"""

import os
import re
import subprocess
import sys

import pytest
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import enable_legacy_chat_view
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_away_and_back
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# ========== Fixtures ==========


@pytest.fixture(autouse=True)
def _use_legacy_chat_view(request: pytest.FixtureRequest) -> None:
    """Enable legacy chat view so these tests exercise classic rendering."""
    if "sculptor_instance_" in request.fixturenames:
        instance = request.getfixturevalue("sculptor_instance_")
        enable_legacy_chat_view(instance.page)


# ========== Helper Functions ==========


def get_first_tool_block(page: Page) -> Locator:
    """Get the first AskUserQuestion tool block in the chat."""
    return page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK).first


def click_tool_block_header(tool_block: Locator) -> None:
    """Click the tool block header to toggle expand/collapse.

    The onClick handler for toggling is on the inner header Flex element, not
    the outer Box, so we target the header via its data-testid.
    """
    tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK_HEADER).click()


def expand_tool_block_if_collapsed(tool_block: Locator) -> None:
    """Expand the tool block if it's currently collapsed.

    Uses the data-expanded attribute on the outer Box to detect state,
    avoiding accidental toggling when called on an already-expanded block.
    """
    if tool_block.get_attribute("data-expanded") != "true":
        click_tool_block_header(tool_block)


def verify_tool_block_question_text(tool_block: Locator, expected_question: str) -> None:
    """Verify that the tool block displays the expected question text when expanded."""
    expand_tool_block_if_collapsed(tool_block)
    question_elements = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)
    expect(question_elements.filter(has_text=expected_question).first).to_be_visible()


def verify_tool_block_answer_text(tool_block: Locator, expected_answer: str) -> None:
    """Verify that the tool block displays the expected answer text when expanded."""
    expand_tool_block_if_collapsed(tool_block)
    answer_elements = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_ANSWER_TEXT)
    expect(answer_elements.filter(has_text=expected_answer).first).to_be_visible()


def verify_tool_block_multi_answers(tool_block: Locator, expected_answers: list[str]) -> None:
    """Verify that the tool block displays multiple answers (for multi-select questions)."""
    expand_tool_block_if_collapsed(tool_block)
    answer_elements = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_ANSWER_TEXT)
    for answer in expected_answers:
        expect(answer_elements.filter(has_text=answer).first).to_be_visible()


def verify_tool_block_shows_submitted_state(tool_block: Locator) -> None:
    """Verify that the tool block shows 'Submitted' state (not pending or dismissed)."""
    header_label = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_HEADER_LABEL)
    expect(header_label).to_contain_text("Questions answered")
    status_badge = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_STATUS_BADGE)
    expect(status_badge).to_contain_text("Submitted")


def verify_tool_block_shows_dismissed_state(tool_block: Locator) -> None:
    """Verify that the tool block shows 'Dismissed' state."""
    header_label = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_HEADER_LABEL)
    expect(header_label).to_contain_text("Questions dismissed")
    status_badge = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_STATUS_BADGE)
    expect(status_badge).to_contain_text("Dismissed")


def navigate_to_next_question(page: Page) -> None:
    """Click the Next button to navigate to the next question in multi-question flow."""
    next_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_NEXT_BUTTON)
    next_button.click()


def navigate_to_previous_question(page: Page) -> None:
    """Click the Previous button to navigate to the previous question in multi-question flow."""
    prev_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PREVIOUS_BUTTON)
    prev_button.click()


def select_option_by_text(page: Page, option_text: str) -> None:
    """Select an option in the Q&A panel by clicking on it."""
    if option_text == "Other":
        # "Other" is a special option with its own test ID
        other_option = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OTHER_OPTION)
        other_option.click()
    else:
        # Regular options have the ASK_USER_QUESTION_OPTION test ID
        options = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
        option = options.filter(has_text=option_text)
        option.first.click()


def type_other_text(page: Page, text: str) -> None:
    """Type custom text into the 'Other' input field."""
    other_input = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OTHER_INPUT)
    other_input.fill(text)


def submit_answers(page: Page) -> None:
    """Click the Submit button to submit answers."""
    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)
    submit_button.click()


def dismiss_questions(page: Page) -> None:
    """Click the Dismiss button instead of answering."""
    dismiss_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_DISMISS_BUTTON)
    dismiss_button.click()


# ========== Tests ==========


@user_story("to answer questions asked by the agent")
def test_ask_user_question_full_flow(sculptor_instance_: SculptorInstance) -> None:
    """Test the full AskUserQuestion flow: agent asks a question, user answers, agent continues.

    This test verifies:
    - Q&A panel appears with the correct question
    - User can select an answer and submit
    - Tool block displays the question and answer correctly
    - No duplicate tool blocks appear
    """
    page = sculptor_instance_.page

    # Create a workspace with a FakeClaude command that triggers AskUserQuestion.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the Q&A panel to appear. On cold start, the agent subprocess may
    # take several seconds to spawn, so we use a generous timeout. We do NOT check
    # the thinking indicator first because it's a transient state that can appear
    # and disappear before the assertion runs (especially on warm repeated runs).
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # While the question is pending, there should be exactly one AskUserQuestion tool block
    # in the chat (no duplicates from streaming persistence).
    ask_tool_blocks = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)
    expect(ask_tool_blocks).to_have_count(1)

    # Verify the question is displayed in the panel
    question_text = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)
    expect(question_text).to_contain_text("programming language")

    # Verify at least one option is rendered
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    expect(options.first).to_be_visible()

    # The submit button should be disabled before an answer is selected
    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)
    expect(submit_button).to_be_disabled()

    # Select the first option (likely Python)
    options.first.click()

    # The submit button should now be enabled
    expect(submit_button).to_be_enabled()

    # Submit the answer
    submit_button.click()

    # After submission, the Q&A panel should disappear
    expect(ask_panel).not_to_be_visible(timeout=30_000)

    # The chat input should reappear (back to normal mode)
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible(timeout=10_000)

    # The agent should continue processing after receiving the answer.
    # Wait for the agent to finish streaming.
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()

    # After the agent finishes, we should have completed messages:
    # - Message 0: initial user message
    # - Message 1: assistant response (with AskUserQuestion tool call)
    # - Message 2: assistant response (the follow-up after receiving the answer)
    # Note: UserQuestionAnswerMessage does not create a visible user message in the chat.
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # After answering and completing, there should still be exactly one AskUserQuestion
    # tool block — no duplicates should appear from persistence or page state.
    expect(ask_tool_blocks).to_have_count(1)

    # Verify the tool block shows the submitted state with the question and answer
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_question_text(tool_block, "programming language")
    # The answer should be one of the options (Python, JavaScript, or Rust)
    # We know the first option was selected, which is likely Python
    verify_tool_block_answer_text(tool_block, "Python")


@user_story("to answer multiple questions in one prompt")
def test_ask_user_question_multiple_questions(sculptor_instance_: SculptorInstance) -> None:
    """Test AskUserQuestion with multiple questions (2-4 questions).

    This test verifies:
    - Navigation between questions works (Next/Previous buttons)
    - Submit button only enabled when all questions are answered
    - All questions and answers are displayed in the tool block
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What is your preferred programming language?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    },
    {
      "question": "What is your experience level?",
      "header": "Experience",
      "options": [
        {"label": "Beginner", "description": "Just starting"},
        {"label": "Intermediate", "description": "Some experience"},
        {"label": "Advanced", "description": "Expert level"}
      ],
      "multiSelect": false
    },
    {
      "question": "What type of project are you working on?",
      "header": "Project",
      "options": [
        {"label": "Web App", "description": "Web application"},
        {"label": "CLI Tool", "description": "Command line tool"},
        {"label": "Data Science", "description": "Data analysis"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Verify we're on question 1
    question_text = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)
    expect(question_text).to_contain_text("programming language")

    # Button should say "Next" (haven't answered all questions yet)
    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)
    expect(submit_button).to_have_text("Next")

    # Select an answer for question 1
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()

    # Navigate to question 2
    navigate_to_next_question(page)

    # Verify we're on question 2
    expect(question_text).to_contain_text("experience level")

    # Button should still say "Next"
    expect(submit_button).to_have_text("Next")

    # Select an answer for question 2
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()

    # Navigate to question 3
    navigate_to_next_question(page)

    # Verify we're on question 3
    expect(question_text).to_contain_text("type of project")

    # Q3 is the only unanswered question, so button says "Submit" (disabled)
    expect(submit_button).to_have_text("Submit")
    expect(submit_button).to_be_disabled()

    # Test backward navigation
    navigate_to_previous_question(page)
    expect(question_text).to_contain_text("experience level")

    # Go back to question 3
    navigate_to_next_question(page)
    expect(question_text).to_contain_text("type of project")

    # Select an answer for question 3
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()

    # Now all questions are answered, button should say "Submit"
    expect(submit_button).to_have_text("Submit")

    # Submit the answers
    submit_button.click()

    # Wait for the agent to finish
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify the tool block shows all three questions and answers
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_question_text(tool_block, "programming language")
    verify_tool_block_question_text(tool_block, "experience level")
    verify_tool_block_question_text(tool_block, "type of project")


@user_story("to select multiple answers for a question")
def test_ask_user_question_multiselect(sculptor_instance_: SculptorInstance) -> None:
    """Test AskUserQuestion with multiSelect enabled.

    This test verifies:
    - Can select multiple predefined options
    - Answers are displayed as separate badges in the tool block
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which programming languages are you familiar with?",
      "header": "Languages",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"},
        {"label": "Go", "description": "For cloud infrastructure"},
        {"label": "TypeScript", "description": "Typed JavaScript"}
      ],
      "multiSelect": true
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Select multiple options
    select_option_by_text(page, "Python")
    select_option_by_text(page, "JavaScript")
    select_option_by_text(page, "Rust")

    # Submit
    submit_answers(page)

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify the tool block shows all selected answers
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_multi_answers(tool_block, ["Python", "JavaScript", "Rust"])


@user_story("to provide custom text for 'Other' option")
def test_ask_user_question_other_option(sculptor_instance_: SculptorInstance) -> None:
    """Test selecting 'Other' option with custom text input.

    This test verifies:
    - Can select 'Other' option
    - Text input appears and is focused
    - Custom text is submitted as the answer
    - Custom text appears in the tool block
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Select 'Other' option
    select_option_by_text(page, "Other")

    # Verify text input appears and is focused
    other_input = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OTHER_INPUT)
    expect(other_input).to_be_visible()
    expect(other_input).to_be_focused()

    # Submit should be disabled without text
    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)
    expect(submit_button).to_be_disabled()

    # Type custom text
    type_other_text(page, "Haskell")

    # Now submit should be enabled
    expect(submit_button).to_be_enabled()

    # Submit
    submit_button.click()

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify the tool block shows the custom answer
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_answer_text(tool_block, "Haskell")


@user_story("to select multiple options including 'Other'")
def test_ask_user_question_multiselect_with_other(sculptor_instance_: SculptorInstance) -> None:
    """Test multiSelect with predefined options + Other custom text.

    This test verifies:
    - Can select multiple predefined options AND Other
    - Custom text is included in the comma-separated answers
    - All answers (predefined + custom) appear in the tool block
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which programming languages do you know?",
      "header": "Languages",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": true
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Select some predefined options
    select_option_by_text(page, "Python")
    select_option_by_text(page, "JavaScript")

    # Select Other and type custom text
    select_option_by_text(page, "Other")
    type_other_text(page, "Elixir")

    # Submit
    submit_answers(page)

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify the tool block shows all answers including custom text
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_multi_answers(tool_block, ["Python", "JavaScript", "Elixir"])


@user_story("to dismiss questions without answering")
def test_ask_user_question_dismiss(sculptor_instance_: SculptorInstance) -> None:
    """Test dismiss functionality for questions.

    This test verifies:
    - Can click Dismiss button instead of answering
    - Q&A panel disappears
    - Tool block shows 'Dismissed' state
    - Agent receives [Dismissed] answers and continues
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Click Dismiss instead of answering
    dismiss_questions(page)

    # Q&A panel should disappear
    expect(ask_panel).not_to_be_visible(timeout=30_000)

    # Wait for agent to finish (agent should continue despite dismissal)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify the tool block shows dismissed state
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_dismissed_state(tool_block)

    # Verify the question text is still visible when expanded
    verify_tool_block_question_text(tool_block, "programming language")


@user_story("to answer multiple sequential questions from the agent")
def test_ask_user_question_sequential_calls(sculptor_instance_: SculptorInstance) -> None:
    """Test agent asking multiple questions in sequence (not in one call).

    This test verifies:
    - Agent can ask question 1, get answer, then ask question 2
    - Two separate tool blocks appear in chat
    - No state pollution between questions
    - Each question's answers tracked separately by tool_use_id
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Answer first question
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text("programming language")

    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    expect(ask_panel).not_to_be_visible(timeout=30_000)

    # Wait for FakeClaude's default response after Q1 answer
    expect(chat_panel.get_thinking_indicator(), "agent to finish after Q1").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Send a follow-up message that triggers a second AskUserQuestion
    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What framework do you prefer?",
      "header": "Framework",
      "options": [
        {"label": "Django", "description": "Python web framework"},
        {"label": "Flask", "description": "Lightweight Python framework"},
        {"label": "FastAPI", "description": "Modern async framework"}
      ],
      "multiSelect": false
    }
  ]
}`""",
    )

    # Second question should appear
    expect(ask_panel).to_be_visible(timeout=30_000)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text("framework")

    # Answer second question
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    expect(ask_panel).not_to_be_visible(timeout=30_000)

    # Wait for agent to finish
    expect(chat_panel.get_thinking_indicator(), "agent to finish after Q2").not_to_be_visible()

    # Messages: user Q1, assistant Q1, assistant default, user Q2, assistant Q2, assistant default
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6)

    # Verify two separate tool blocks exist
    ask_tool_blocks = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)
    expect(ask_tool_blocks).to_have_count(2)

    # Verify each tool block shows its respective question
    first_block = ask_tool_blocks.nth(0)
    verify_tool_block_shows_submitted_state(first_block)
    verify_tool_block_question_text(first_block, "programming language")

    second_block = ask_tool_blocks.nth(1)
    verify_tool_block_shows_submitted_state(second_block)
    verify_tool_block_question_text(second_block, "framework")


@user_story("to reload page while question is pending")
def test_ask_user_question_reload_while_pending(sculptor_instance_: SculptorInstance) -> None:
    """Test page reload/navigation while a question is still pending.

    This test verifies:
    - Question persists after navigating away and back
    - Can still answer and submit after navigating back
    - Tests the persistence reconstruction logic
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )

    # Wait for Q&A panel to appear
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text("programming language")

    # Navigate away from the workspace and back using workspace tabs.
    # Click the "+" button to open the new-workspace modal, close it,
    # then click the workspace tab to navigate back. The overlay would
    # otherwise intercept the workspace-tab click.
    add_ws_button = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_BUTTON)
    add_ws_button.click()
    expect(page.get_by_test_id(ElementIDs.START_TASK_BUTTON)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_test_id(ElementIDs.START_TASK_BUTTON)).to_be_hidden()
    workspace_tab = page.get_by_test_id(ElementIDs.WORKSPACE_TAB).first
    workspace_tab.click()

    # Question should still be pending and visible
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=10_000)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text("programming language")

    # Should be able to answer normally
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(page.get_by_test_id(ElementIDs.THINKING_INDICATOR), "agent to finish").not_to_be_visible()


@user_story("to see answered questions after page reload")
def test_ask_user_question_reload_after_answered(sculptor_instance_: SculptorInstance) -> None:
    """Test page reload after questions have been answered and task completed.

    This test verifies:
    - Tool block shows 'Answered' state (not pending)
    - Submitted answers are displayed in tool block
    - Q&A panel does NOT reappear
    - Tests submittedQuestionAnswers persistence
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Answer and complete
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Soft-reload to refresh state (direct reload causes ERR_INSUFFICIENT_RESOURCES on CI)
    soft_reload_page(page)
    page.wait_for_timeout(2000)

    # Q&A panel should NOT reappear
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).not_to_be_visible()

    # Tool block should show submitted state with answers
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_question_text(tool_block, "programming language")
    verify_tool_block_answer_text(tool_block, "Python")


@user_story("to navigate through questions and answer out of order")
def test_ask_user_question_navigation_state(sculptor_instance_: SculptorInstance) -> None:
    """Test navigation through multiple questions, answering out of order.

    This test verifies:
    - Can navigate forward through all questions without answering
    - Can navigate backward
    - Can answer questions out of order (Q3, then Q1, then Q2)
    - Answers are preserved during navigation
    - Can only submit when all questions are answered
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What is your programming language preference?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "Versatile"},
        {"label": "JavaScript", "description": "Web"}
      ],
      "multiSelect": false
    },
    {
      "question": "What is your experience level?",
      "header": "Experience",
      "options": [
        {"label": "Beginner", "description": "New"},
        {"label": "Advanced", "description": "Expert"}
      ],
      "multiSelect": false
    },
    {
      "question": "What is your project type?",
      "header": "Project",
      "options": [
        {"label": "Web App", "description": "Website"},
        {"label": "CLI", "description": "Command line"}
      ],
      "multiSelect": false
    },
    {
      "question": "What is your team size?",
      "header": "Team",
      "options": [
        {"label": "Solo", "description": "Just me"},
        {"label": "Small", "description": "2-5 people"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)

    # Navigate forward without answering
    navigate_to_next_question(page)  # Q1 -> Q2
    navigate_to_next_question(page)  # Q2 -> Q3
    navigate_to_next_question(page)  # Q3 -> Q4

    # Answer Q4
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    expect(submit_button).to_have_text("Next")  # Still need Q1, Q2, Q3

    # Navigate back to Q1
    navigate_to_previous_question(page)  # Q4 -> Q3
    navigate_to_previous_question(page)  # Q3 -> Q2
    navigate_to_previous_question(page)  # Q2 -> Q1

    # Answer Q1
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    expect(submit_button).to_have_text("Next")  # Still need Q2, Q3

    # Navigate to Q3 (skipping Q2)
    navigate_to_next_question(page)  # Q1 -> Q2
    navigate_to_next_question(page)  # Q2 -> Q3

    # Answer Q3
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    expect(submit_button).to_have_text("Next")  # Still need Q2

    # Go back to Q2
    navigate_to_previous_question(page)  # Q3 -> Q2

    # Answer Q2
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()

    # Now all questions are answered, button should say "Submit"
    expect(submit_button).to_have_text("Submit")

    # Submit
    submit_button.click()

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()


@user_story("to see a Next button that navigates to the next unanswered question")
def test_ask_user_question_next_button(sculptor_instance_: SculptorInstance) -> None:
    """Test the Next/Submit button behavior with multiple questions.

    This test verifies:
    - Button says "Next" when unanswered questions exist elsewhere
    - Clicking "Next" navigates to the next unanswered question
    - Button says "Submit" (disabled) when current question is the only unanswered one
    - Button says "Submit" (enabled) when all questions are answered
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Pick a color",
      "header": "Color",
      "options": [
        {"label": "Red", "description": ""},
        {"label": "Blue", "description": ""}
      ],
      "multiSelect": false
    },
    {
      "question": "Pick a size",
      "header": "Size",
      "options": [
        {"label": "Small", "description": ""},
        {"label": "Large", "description": ""}
      ],
      "multiSelect": false
    },
    {
      "question": "Pick a shape",
      "header": "Shape",
      "options": [
        {"label": "Circle", "description": ""},
        {"label": "Square", "description": ""}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    question_text = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)
    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)

    # On Q1 with nothing answered: button says "Next"
    expect(question_text).to_contain_text("Pick a color")
    expect(submit_button).to_have_text("Next")

    # Answer Q1, then click Next — should go to Q2 (next unanswered)
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    expect(submit_button).to_have_text("Next")
    submit_button.click()
    expect(question_text).to_contain_text("Pick a size")

    # Answer Q2, then click Next — should go to Q3 (only remaining unanswered)
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    expect(submit_button).to_have_text("Next")
    submit_button.click()
    expect(question_text).to_contain_text("Pick a shape")

    # On Q3 which is the only unanswered question: button says "Submit" (disabled)
    expect(submit_button).to_have_text("Submit")
    expect(submit_button).to_be_disabled()

    # Answer Q3 — button becomes enabled
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    expect(submit_button).to_have_text("Submit")
    expect(submit_button).to_be_enabled()

    # Submit
    submit_button.click()

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify tool block
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_answer_text(tool_block, "Red")
    verify_tool_block_answer_text(tool_block, "Small")
    verify_tool_block_answer_text(tool_block, "Circle")


@user_story("to handle questions with very long text")
def test_ask_user_question_long_text(sculptor_instance_: SculptorInstance) -> None:
    """Test questions with very long text (200+ characters).

    This test verifies:
    - UI doesn't break with long text
    - Text wraps correctly
    - Can still interact and submit
    - Long text appears correctly in tool block
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What is your preferred programming language for building large-scale, distributed, highly-concurrent web applications that need to handle millions of requests per second while maintaining low latency and high availability across multiple data centers?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile general-purpose programming language known for its readability and extensive ecosystem of libraries"},
        {"label": "JavaScript", "description": "The language of the web, running both client-side and server-side with Node.js for full-stack development"},
        {"label": "Rust", "description": "A systems programming language focused on safety, speed, and concurrency without a garbage collector"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Question should appear despite long text
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Verify the long question text is visible (at least part of it)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text(
        "preferred programming language"
    )

    # Should be able to interact normally
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    expect(options.first).to_be_visible()
    options.first.click()

    submit_answers(page)

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify tool block shows the question (at least partially)
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_question_text(tool_block, "preferred programming language")


@user_story("to handle questions with special characters")
def test_ask_user_question_special_characters(sculptor_instance_: SculptorInstance) -> None:
    """Test special characters, emojis, and unicode in questions and answers.

    This test verifies:
    - Special characters are correctly encoded/decoded
    - No XSS issues or display corruption
    - Special characters appear correctly in tool block
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What is your favorite programming language? \\ud83d\\ude80",
      "header": "Language",
      "options": [
        {"label": "C++", "description": "Systems programming with classes"},
        {"label": "C#", "description": "Microsoft .NET language"},
        {"label": "F#", "description": "Functional .NET language"},
        {"label": "Objective-C", "description": "Apple legacy language"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Verify special characters appear correctly
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text(
        "favorite programming language"
    )

    # Select an option with special characters (e.g., C++)
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()

    submit_answers(page)

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify tool block shows the question and answer with special characters
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    verify_tool_block_question_text(tool_block, "favorite programming language")


@user_story("to see no duplicate tool blocks after Sculptor restart")
def test_ask_user_question_no_duplicates_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Test that after restarting Sculptor, AskUserQuestion doesn't show duplicate tool blocks.

    This test verifies:
    - After answering questions and restarting, only ONE tool block is shown
    - The tool block shows "Questions answered", not "Called Tools" with duplicates
    - No ToolResultBlock is rendered alongside the ToolUseBlock
    """
    # First Sculptor instance: create workspace, answer question, wait for completion
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        enable_legacy_chat_view(page)

        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        # Answer the question
        ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
        expect(ask_panel).to_be_visible(timeout=30_000)

        options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
        options.first.click()
        submit_answers(page)

        expect(ask_panel).not_to_be_visible(timeout=30_000)
        expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

        # Before restart: verify only one tool block exists
        ask_tool_blocks = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)
        expect(ask_tool_blocks).to_have_count(1)

        # Verify it shows "Questions answered" (not grouped under "Called Tools")
        tool_block = get_first_tool_block(page)
        verify_tool_block_shows_submitted_state(tool_block)

    # Second Sculptor instance: restart and verify state persisted correctly
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        enable_legacy_chat_view(page)

        # The workspace still exists after restart.
        # Wait for the workspace tab to be visible, then click it.
        workspace_tab = page.get_by_test_id(ElementIDs.WORKSPACE_TAB).first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()

        # Wait for messages to fully load from persistence before checking tool blocks.
        # Previously we only waited for the chat panel to be visible, which doesn't
        # guarantee messages have finished loading from the backend.  Waiting for the
        # expected message count (3 from Phase 1) ensures the chat is fully populated.
        task_page_after = PlaywrightTaskPage(page=page)
        chat_panel_after = task_page_after.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel_after, expected_message_count=3)

        # After messages are loaded, verify only one tool block exists
        ask_tool_blocks_after_restart = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)
        expect(ask_tool_blocks_after_restart).to_have_count(1, timeout=10_000)

        # CRITICAL: Check for the bug symptom - fail fast if "Called Tools" grouping appears.
        # Bug symptom: tools are grouped with 2 children instead of a single "Questions answered" block.
        # The TOOL_CALL elements should have data-is-grouped absent (not grouped).
        tool_calls = page.get_by_test_id(ElementIDs.TOOL_CALL)
        for tool_call in tool_calls.all():
            assert tool_call.get_attribute("data-is-grouped") != "true", (
                "Found grouped tool section — AskUserQuestion tool block should not be grouped"
            )

        # Verify it still shows "Questions answered" (not grouped)
        tool_block_after = get_first_tool_block(page)
        verify_tool_block_shows_submitted_state(tool_block_after)


@user_story("to see Thinking indicator while agent processes a question answer")
def test_task_status_running_while_processing_answer(sculptor_instance_: SculptorInstance) -> None:
    """Test that task status is RUNNING while the agent processes a UserQuestionAnswerMessage.

    Regression: UserQuestionAnswerMessage was not included in the
    CodingAgentTaskView.status computation, so task.status stayed READY while
    the agent was actively processing the answer. This caused the
    ThinkingIndicator to disappear after answering a question or approving a plan.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the Q&A panel to appear
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Select an answer and submit
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    # After submission, the Q&A panel should disappear
    expect(ask_panel).not_to_be_visible(timeout=30_000)

    # REGRESSION: After answering, the task status must transition to RUNNING while
    # the agent processes the UserQuestionAnswerMessage. The ThinkingIndicator
    # should be visible while the agent processes the answer.
    expect(chat_panel.get_thinking_indicator(), "task should be RUNNING while processing answer").to_be_visible(
        timeout=10_000
    )

    # Wait for the agent to finish processing the answer
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)


@user_story("to see answered questions auto-expanded so the answer is readable")
def test_ask_user_question_auto_expands_after_answer(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: the tool block should auto-expand after the user submits an answer.

    When the user answers a question, the AskUserQuestionToolBlock should
    automatically expand to show the question and answer, so the user can read
    their own answer without an extra click.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the Q&A panel to appear
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Answer and submit
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # The tool block should be auto-expanded (data-expanded="true")
    tool_block = get_first_tool_block(page)
    expect(tool_block).to_have_attribute("data-expanded", "true")

    # The answer text should be visible without needing to click anything
    answer_text = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_ANSWER_TEXT)
    expect(answer_text.first).to_be_visible()


@user_story("to preserve in-progress answers when navigating away and back")
def test_ask_user_question_preserves_selection_after_navigation(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: selections and typed text survive navigating away and back.

    When the user selects an option or types text in the "Provide an alternative"
    box, then navigates to the Open Workspace page and returns, the selections
    and text must be preserved.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel to appear
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Select the "Provide an alternative" option and type custom text
    select_option_by_text(page, "Other")
    type_other_text(page, "Haskell is my favorite")

    # The submit button should be enabled (answer provided)
    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)
    expect(submit_button).to_be_enabled()

    # Navigate away to the Add Workspace page and back
    navigate_away_and_back(page)

    # The Q&A panel should reappear (pendingUserQuestion persists in Jotai)
    expect(ask_panel).to_be_visible(timeout=10_000)

    # The "Other" input should still be visible with the typed text preserved
    other_input = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OTHER_INPUT)
    expect(other_input).to_be_visible()
    expect(other_input).to_have_value("Haskell is my favorite")

    # The submit button should still be enabled
    expect(submit_button).to_be_enabled()


@user_story("to preserve predefined option selection when navigating away and back")
def test_ask_user_question_preserves_predefined_option_after_navigation(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Regression test: a selected predefined option survives navigating away and back.

    When the user selects a predefined option (not "Other"), navigates to the
    Open Workspace page and returns, the option must still be selected and the
    submit button must still be enabled.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which framework do you use?",
      "header": "Framework",
      "options": [
        {"label": "React", "description": "A UI library"},
        {"label": "Vue", "description": "A progressive framework"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel to appear
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Select the first predefined option ("React")
    select_option_by_text(page, "React")

    # The submit button should be enabled
    submit_button = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)
    expect(submit_button).to_be_enabled()

    # Navigate away and back
    navigate_away_and_back(page)

    # The Q&A panel should reappear
    expect(ask_panel).to_be_visible(timeout=10_000)

    # The submit button should still be enabled (option still selected)
    expect(submit_button).to_be_enabled()

    # Verify the selection was preserved by submitting and checking the answer
    submit_answers(page)
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).not_to_be_visible(timeout=30_000)

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    tool_block = get_first_tool_block(page)
    verify_tool_block_answer_text(tool_block, "React")


@user_story("to answer a single question after previously answering a multi-question batch")
def test_ask_user_question_draft_does_not_leak_across_batches(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: draft state from a 2-question batch must not leak into a later 1-question batch.

    When the agent asks 2 questions, the user navigates to Q2 (currentIndex=1),
    answers both, and submits, the draft atom stores currentIndex=1. If the
    agent later asks just 1 question, the stale currentIndex causes
    questions[1] to be undefined, resulting in a TypeError.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"}
      ],
      "multiSelect": false
    },
    {
      "question": "What is your experience level?",
      "header": "Experience",
      "options": [
        {"label": "Beginner", "description": "New to coding"},
        {"label": "Advanced", "description": "Years of experience"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for Q&A panel
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Answer Q1
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()

    # Navigate to Q2 (sets currentIndex=1 in the draft atom)
    navigate_to_next_question(page)

    # Answer Q2
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()

    # Submit both answers
    submit_answers(page)
    expect(ask_panel).not_to_be_visible(timeout=30_000)

    # Wait for agent to finish
    expect(chat_panel.get_thinking_indicator(), "agent to finish after batch 1").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Now send a follow-up that triggers a SINGLE question.
    # Bug: the stale draft has currentIndex=1, so questions[1] is undefined → TypeError.
    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What framework do you prefer?",
      "header": "Framework",
      "options": [
        {"label": "Django", "description": "Python web framework"},
        {"label": "Flask", "description": "Lightweight Python framework"}
      ],
      "multiSelect": false
    }
  ]
}`""",
    )

    # The single-question Q&A panel should appear without a TypeError
    expect(ask_panel).to_be_visible(timeout=30_000)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text("framework")

    # Should be able to answer and submit normally
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish after batch 2").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6)


@user_story("to keep queued messages queued when the agent asks a question")
def test_queued_message_stays_queued_during_ask_user_question(sculptor_instance_: SculptorInstance) -> None:
    """Queued messages must not be sent or promoted while the agent is awaiting a Q&A answer.

    Regression: When the agent calls AskUserQuestion, the Claude Code CLI process
    exits and emits RequestSuccessAgentMessage, which the agent loop treats as the
    turn finishing. Any queued message is then immediately dequeued and sent to the
    agent — before the user has answered the question.

    Expected behavior:
    - The queued message bar is hidden while the Q&A panel is visible.
    - The queued message is NOT promoted into the chat while the question is pending.
    - After the user answers the question and the agent finishes processing the
      answer, the queued message is dequeued and processed normally.
    """
    page = sculptor_instance_.page

    # Use multi_step: sleep first (so we can queue a message), then ask a question.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "sleep", "args": {"seconds": 5}},
    {"command": "ask_user_question", "args": {
      "questions": [
        {
          "question": "What programming language do you prefer?",
          "header": "Language",
          "options": [
            {"label": "Python", "description": "A versatile language"},
            {"label": "JavaScript", "description": "For web development"}
          ],
          "multiSelect": false
        }
      ]
    }}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the agent to be actively processing (sleeping)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Queue a message while the agent is busy
    send_chat_message(chat_panel=chat_panel, message="this should stay queued")

    # The queued message bar should be visible while the agent is sleeping
    queued_bar = chat_panel.get_queued_message_bar()
    expect(queued_bar).to_have_count(1)
    expect(queued_bar).to_contain_text("this should stay queued")

    # Wait for the Q&A panel to appear (after the sleep finishes)
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # REGRESSION CHECK 1: The queued message bar should be hidden while Q&A is visible.
    # The chat input is replaced by the Q&A panel, so the queued bar should also hide.
    expect(queued_bar, "queued bar should be hidden during Q&A").to_have_count(0)

    # REGRESSION CHECK 2: The queued message must NOT appear as a sent message in the chat.
    # Only the initial user message and the assistant response should be in the chat.
    # If the bug is present, the queued message would be promoted and appear as message 2.
    messages = chat_panel.get_messages()
    expect(messages).to_have_count(2)  # user message + assistant response with tool use

    # Answer the question
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    # After submission, the Q&A panel should disappear
    expect(ask_panel).not_to_be_visible(timeout=30_000)

    # Wait for the agent to finish processing the answer AND the queued message.
    # Expected message flow:
    # 0: initial user message (multi_step prompt)
    # 1: assistant response (with AskUserQuestion tool use)
    # 2: assistant response (follow-up after receiving the answer)
    # 3: queued user message ("this should stay queued") — promoted after answer processed
    # 4: assistant response to the queued message ("[FakeClaude] Task completed.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=5)


@user_story("to type long custom text without extra line breaks in the answer display")
def test_ask_user_question_other_long_text_no_extra_linebreaks(sculptor_instance_: SculptorInstance) -> None:
    """Test that long custom text with commas renders as a single answer, not split into parts.

    Regression test: the display code splits answer text by ", " to separate predefined
    options from custom text. If the custom text itself contains ", ", it was incorrectly
    split into multiple elements, each on its own line — appearing as extra line breaks.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Select 'Other' and type a long string that contains ", "
    long_text = "I prefer Go, because it has great concurrency, simple syntax, and fast compilation"
    select_option_by_text(page, "Other")
    type_other_text(page, long_text)
    submit_answers(page)

    # Wait for completion
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Verify the tool block shows the full custom answer as a single element
    tool_block = get_first_tool_block(page)
    verify_tool_block_shows_submitted_state(tool_block)
    expand_tool_block_if_collapsed(tool_block)

    # The answer should render as exactly 1 element, not split at commas
    answer_elements = tool_block.get_by_test_id(ElementIDs.ASK_USER_QUESTION_ANSWER_TEXT)
    expect(answer_elements).to_have_count(1)
    expect(answer_elements.first).to_contain_text(long_text)


@user_story("to switch between agents that both have pending questions")
def test_ask_user_question_draft_does_not_leak_across_agents(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: switching agents must not carry stale AUQ draft state across tabs.

    When agent 1 has a 3-question AUQ and the user is on question 3 (currentIndex=2),
    switching to agent 2 which has a 1-question AUQ must show agent 2's question
    at index 0, not crash from accessing questions[2] on a 1-element array.

    The bug only triggers when BOTH agents have pending AUQs simultaneously, because
    React reuses the AskUserQuestion component instance (no key prop) instead of
    remounting it, so useState doesn't reinitialize the stale currentIndex.
    """
    page = sculptor_instance_.page

    # Start agent 1 with a simple response (not an AUQ yet).
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "hello"}`',
    )
    chat_panel_1 = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_1, expected_message_count=2)

    # Add agent 2 and send it a single-question AUQ.
    add_agent_button = page.get_by_test_id(ElementIDs.ADD_AGENT_BUTTON)
    add_agent_button.click()

    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2)

    task_page_2 = PlaywrightTaskPage(page=page)
    chat_panel_2 = task_page_2.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel_2,
        message="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What framework do you prefer?",
      "header": "Framework",
      "options": [
        {"label": "Django", "description": "Python web framework"},
        {"label": "Flask", "description": "Lightweight Python framework"}
      ],
      "multiSelect": false
    }
  ]
}`""",
    )

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text("framework")

    # Switch to agent 1 (agent 2's AUQ unmounts because agent 1 has no pending AUQ).
    agent_tabs.first.click()

    # Send agent 1 a 3-question AUQ.
    chat_panel_1 = PlaywrightTaskPage(page=page).get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel_1,
        message="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"}
      ],
      "multiSelect": false
    },
    {
      "question": "What is your experience level?",
      "header": "Experience",
      "options": [
        {"label": "Beginner", "description": "New to coding"},
        {"label": "Advanced", "description": "Years of experience"}
      ],
      "multiSelect": false
    },
    {
      "question": "What editor do you use?",
      "header": "Editor",
      "options": [
        {"label": "VS Code", "description": "Popular editor"},
        {"label": "Vim", "description": "Terminal editor"}
      ],
      "multiSelect": false
    }
  ]
}`""",
    )

    expect(ask_panel).to_be_visible(timeout=30_000)

    # Answer Q1 and navigate to Q3 (currentIndex=2).
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    navigate_to_next_question(page)  # now on Q2
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    navigate_to_next_question(page)  # now on Q3 (currentIndex=2)

    # Also type a custom "Other" response on Q3 to populate otherTexts.
    select_option_by_text(page, "Other")
    type_other_text(page, "Emacs")

    # Verify we're on question 3 of 3.
    expect(ask_panel).to_contain_text("Question 3 of 3")

    # Now both agents have pending AUQs. Switch to agent 2.
    # Bug: React reuses AskUserQuestion (both branches render it), so currentIndex=2
    # carries over, but agent 2 only has 1 question → questions[2] is undefined → crash.
    agent_tabs.last.click()
    expect(ask_panel).to_be_visible(timeout=10_000)
    expect(ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)).to_contain_text("framework")

    # Agent 2's AUQ should be answerable normally.
    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)
    expect(ask_panel).not_to_be_visible(timeout=30_000)


def _run_sculpt(instance: SculptorInstance, args: list[str]) -> tuple[int, str, str]:
    """Invoke the sculpt CLI as a subprocess and return (exit_code, stdout, stderr).

    Automatically injects --base-url and sets the SCULPT_PROJECT_ID
    environment variable so the CLI can resolve the project.
    """
    base_url = instance.base_url.rstrip("/")
    response = instance.page.request.get(f"{base_url}/api/v1/projects/active")
    projects = response.json()
    project_id = projects[0]["objectId"] if projects else ""

    env = {**os.environ, "SCULPT_PROJECT_ID": project_id}
    full_args = args + ["--base-url", instance.base_url]
    result = subprocess.run(
        [sys.executable, "-m", "sculpt.main"] + full_args,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


@user_story("to prevent conflicting messages while a question is pending")
def test_send_message_blocked_while_ask_user_question_pending(sculptor_instance_: SculptorInstance) -> None:
    """Sending a message via sculpt CLI while AskUserQuestion is pending must fail.

    When an agent has called AskUserQuestion and the Q&A panel is visible,
    the chat input is hidden. The sculpt CLI's ``agent send`` command must
    detect the 409 Conflict response and exit with a non-zero exit code.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which approach do you prefer?",
      "header": "Approach",
      "options": [
        {"label": "Option A", "description": "First approach"},
        {"label": "Option B", "description": "Second approach"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel to appear, confirming AUQ is pending.
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # Extract workspace and agent IDs from the URL.
    current_url = page.url
    ws_match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", current_url)
    agent_match = re.search(r"/agent/([a-zA-Z0-9_-]+)", current_url)
    assert ws_match and agent_match, f"Could not extract IDs from URL: {current_url}"
    workspace_id = ws_match.group(1)
    agent_id = agent_match.group(1)

    # Use sculpt CLI to send a message — should fail with non-zero exit code.
    exit_code, stdout, stderr = _run_sculpt(
        sculptor_instance_, ["agent", "send", agent_id, "This should be blocked", "-w", workspace_id]
    )
    assert exit_code != 0, f"Expected non-zero exit code but got {exit_code}; stdout: {stdout}"
    assert "Message sent" not in stdout

    # The Q&A panel should still be visible — the state is not corrupted.
    expect(ask_panel).to_be_visible()


@user_story("to see only one rendering of the AUQ block after answering — not also a generic tool-call card")
def test_ask_user_question_does_not_render_generic_tool_call_after_answer(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After answering an AUQ in the classic chat view, only the inline
    ``AskUserQuestionToolBlock`` should render for that question — not also
    a generic ``ToolDisplay`` card for the matching
    ``mcp__sculptor__ask_user_question`` tool_result.

    Regression for the same bug as the alpha view: ``isTopLevelBlock`` in
    ``ToolComponents.tsx`` promoted AUQ tool_result blocks into the
    topLevelBlocks bucket, causing a duplicate generic tool-call card to
    render alongside the special AUQ block (which already shows the answer
    via ``submittedQuestionAnswers``).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).to_be_visible(timeout=30_000)

    options = ask_panel.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)
    options.first.click()
    submit_answers(page)

    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # The AUQ block should be visible — that's the correct rendering.
    auq_block = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)
    expect(auq_block).to_have_count(1)

    # No generic tool-call cards should be rendered. This prompt triggers
    # exactly one tool (the AUQ); FakeClaude's follow-up is text only.
    # The AUQ tool_result must NOT render as a separate ``TOOL_CALL`` —
    # the inline block above already shows the answer.
    tool_calls = page.get_by_test_id(ElementIDs.TOOL_CALL)
    expect(tool_calls).to_have_count(0)
