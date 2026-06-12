"""Real Claude integration tests: AskUserQuestion.

Verifies that the AskUserQuestion tool works end-to-end with the stdin protocol,
including the hook-based tool interception (SIGTERM) that stops the agent when
AskUserQuestion is invoked.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude


@real_claude
@pytest.mark.timeout(300)
def test_ask_user_question_single(sculptor_instance_: SculptorInstance) -> None:
    """Verify AskUserQuestion with a single question and predefined options."""
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Before doing anything, you MUST ask me a question using the AskUserQuestion tool. Ask exactly one question with text 'What is your favorite color?' and options ['Red', 'Blue', 'Green']. Do not do anything else until I answer."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the question panel to appear
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Verify the question text is displayed
    question_text = ask_panel.get_question_text()
    expect(question_text.filter(has_text="favorite color").first).to_be_visible()

    # Select an option and submit
    ask_panel.select_option("Blue")
    ask_panel.submit()

    # Agent should resume and finish
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_ask_user_question_multiple(sculptor_instance_: SculptorInstance) -> None:
    """Verify AskUserQuestion with multiple questions."""
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Ask me exactly TWO questions using the AskUserQuestion tool in a single call:\nQuestion 1: 'Pick a size' with options ['Small', 'Medium', 'Large']\nQuestion 2: 'Pick a color' with options ['Red', 'Blue']\nDo not proceed until I answer both questions."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Answer first question
    question_text = ask_panel.get_question_text()
    expect(question_text.first).to_be_visible()
    ask_panel.select_option("Medium")

    # Navigate to second question
    ask_panel.navigate_next()
    ask_panel.select_option("Blue")

    # Submit
    ask_panel.submit()

    # Agent should resume and finish
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_ask_user_question_free_text(sculptor_instance_: SculptorInstance) -> None:
    """Verify AskUserQuestion with free-text answer (no predefined options)."""
    page = sculptor_instance_.page

    # Phrase the prompt so the agent reliably calls AskUserQuestion with a
    # short, ignorable options list — the "Other" option is always rendered
    # alongside whatever options the tool was called with, so any well-formed
    # tool call gives us a free-text path to exercise. Without explicit
    # options the agent sometimes refuses to call AskUserQuestion (the input
    # schema requires options) or answers inline as text, which makes the
    # panel never appear.
    prompt = "You MUST call the AskUserQuestion tool exactly once, right now, before doing anything else. Use header='Filename', question='What should I name the file?', and options=['default.txt']. Wait for my answer, then create a file at the answered path containing 'FREETEXT-OK'. After creating the file, reply with exactly: FREETEXT-DONE."  # noqa: E501
    task_page = create_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=False)
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # The "Other" option is always present alongside the provided options, so
    # we can exercise the free-text input regardless of what the agent passed.
    ask_panel.select_option("Other")
    ask_panel.type_other_text("my-custom-name.txt")
    ask_panel.submit()

    # Agent should resume, create the file, and finish
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)
