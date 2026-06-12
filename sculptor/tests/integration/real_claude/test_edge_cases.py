"""Real Claude integration tests: edge cases.

Verifies edge cases for the stdin JSON protocol: large prompts, special
characters, and transitions between interrupt mechanisms (stdin vs SIGTERM).
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import interrupt_agent
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait
from tests.integration.real_claude.helpers import send_no_wait
from tests.integration.real_claude.helpers import wait_for_any_assistant_text


@real_claude
@pytest.mark.timeout(300)
def test_very_long_prompt_via_stdin(sculptor_instance_: SculptorInstance) -> None:
    """Verify the stdin JSON protocol handles large prompts correctly.

    The old approach used a file redirect (< instructions_file); the new one
    sends the prompt inline as a JSON message on stdin. This tests that large
    payloads don't get truncated or cause pipe buffer issues.
    """
    # Build a ~10,000 character prompt with 500 items
    items = "\n".join(f"Item {i}: ALPHA-{i:03d}" for i in range(1, 501))
    prompt = f"I am going to give you a long list of items. At the end, I will ask a question.\n{items}\nWhat is Item 250? Reply in the format: ITEM-250-IS: <value>"
    task_page = create_workspace_and_send(sculptor_instance_, prompt)
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "ALPHA-250")
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_special_characters_in_prompt(sculptor_instance_: SculptorInstance) -> None:
    """Verify JSON encoding handles special characters in prompts.

    The stdin protocol sends prompts as JSON strings, so characters like
    quotes and backslashes must be properly escaped.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Reply with exactly this text (preserving the special characters):\nSPECIAL-CHARS: <angle> & \"double-quotes\" 'single-quotes'"
        ),
    )
    chat_panel = task_page.get_chat_panel()
    # Check for key special characters (Claude may reformat slightly)
    assert_last_message_contains(chat_panel, "SPECIAL-CHARS")
    assert_last_message_contains(chat_panel, "<angle>")
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_follow_up_after_interrupt(sculptor_instance_: SculptorInstance) -> None:
    """Verify simple follow-up works after interrupt."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Write a long essay about birds. Start with: BIRD-ESSAY:",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    wait_for_any_assistant_text(chat_panel)
    interrupt_agent(chat_panel)

    send_and_wait(chat_panel, "Reply with exactly: EMPTY-EDGE-OK-91823")
    assert_last_message_contains(chat_panel, "EMPTY-EDGE-OK-91823")


@real_claude
@pytest.mark.timeout(600)
def test_interrupt_then_ask_user_question(sculptor_instance_: SculptorInstance) -> None:
    """Verify SIGTERM-based tool interception works after a stdin interrupt.

    This tests the transition between the two interrupt mechanisms within one
    session: first a user-initiated stop (stdin interrupt), then an AskUserQuestion
    (SIGTERM-based tool intercept).
    """
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Write a 2000-word essay about the ocean.",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    wait_for_any_assistant_text(chat_panel)
    interrupt_agent(chat_panel)

    # Now trigger AskUserQuestion (uses SIGTERM-based tool intercept)
    send_no_wait(
        chat_panel,
        ("Ask me a question using AskUserQuestion: 'Continue with ocean essay?' with options ['Yes', 'No']."),
    )

    # Wait for the question panel
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Answer and verify agent continues
    ask_panel.select_option_by_text("Yes")
    ask_panel.submit()

    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(600)
def test_interrupt_then_plan_mode(sculptor_instance_: SculptorInstance) -> None:
    """Verify plan mode works correctly after an interrupt."""
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Write a 2000-word essay about trees.",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    wait_for_any_assistant_text(chat_panel)
    interrupt_agent(chat_panel)

    # Now enter plan mode
    send_no_wait(
        chat_panel,
        ("Enter plan mode. Present a plan with 3 steps to create a simple Python script. Then ask for approval."),
    )

    # Wait for approval prompt
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Approve
    ask_panel.select_option_by_text("Approve")
    ask_panel.submit()

    # Agent should execute
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)
