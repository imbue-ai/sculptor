"""Real Claude integration tests: plan mode.

Verifies the full plan mode lifecycle with the stdin protocol: enter plan mode,
present a plan, approve/revise, and execute.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_claude.helpers import assert_interrupted
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import interrupt_agent
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait
from tests.integration.real_claude.helpers import wait_for_streaming_text


@real_claude
@pytest.mark.timeout(300)
def test_plan_mode_enter_and_approve(sculptor_instance_: SculptorInstance) -> None:
    """Verify the full plan mode lifecycle with stdin protocol."""
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Enter plan mode. Then present a plan with exactly these 3 steps:\n- Step 1: Create a hello.txt file\n- Step 2: Write 'hello world' into it\n- Step 3: Verify the file exists\nThen exit plan mode and ask me to approve."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    auq_panel = get_ask_user_question_panel(page)

    # Wait for the approval prompt
    expect(auq_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Approve the plan
    auq_panel.select_option("Approve")
    auq_panel.submit()

    # Agent should execute the plan
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(600)
def test_plan_mode_with_revision(sculptor_instance_: SculptorInstance) -> None:
    """Verify the user can revise a plan and the agent re-plans."""
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Enter plan mode. Present a plan to create a file called 'original.txt' with the content 'original content'. Then ask for approval."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    auq_panel = get_ask_user_question_panel(page)

    # Wait for approval prompt
    expect(auq_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Revise the plan — select "Other" and type the revision
    auq_panel.select_option("Other")
    auq_panel.type_other_text("Change the filename to 'revised.txt' instead of 'original.txt'.")
    auq_panel.submit()

    # Wait for the revision panel to disappear, then for the new approval prompt.
    expect(auq_panel).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(auq_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Approve the revised plan
    auq_panel.select_option("Approve")
    auq_panel.submit()

    # Agent should execute the revised plan
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(600)
def test_ask_user_question_during_plan_mode(sculptor_instance_: SculptorInstance) -> None:
    """Verify AskUserQuestion works while the agent is in plan mode."""
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Enter plan mode. Before presenting your plan, ask me using AskUserQuestion: 'Which language?' with options ['Python', 'JavaScript']. Then create a plan based on my choice. Then ask for approval."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    auq_panel = get_ask_user_question_panel(page)

    # Wait for the AskUserQuestion panel
    expect(auq_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Answer the question
    auq_panel.select_option("Python")
    auq_panel.submit()

    # Wait for the AUQ panel to disappear (answer is processed via SSE),
    # then wait for the ExitPlanMode approval prompt to appear.
    expect(auq_panel).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(auq_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Approve
    auq_panel.select_option("Approve")
    auq_panel.submit()

    # Agent executes
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_during_plan_mode(sculptor_instance_: SculptorInstance) -> None:
    """Verify interrupting during plan mode is clean and preserves context."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Enter plan mode. Write a very detailed 20-step plan for building a full-stack web application. Start the plan text with PLAN-MARKER-72045: and number each step."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for some plan text to appear
    wait_for_streaming_text(chat_panel, "PLAN-MARKER-72045")

    # Interrupt
    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)

    # Follow-up: verify memory
    send_and_wait(chat_panel, "What were you just planning? Reply starting with PLAN-RECALL:")
    assert_last_message_contains(chat_panel, "PLAN-RECALL")
