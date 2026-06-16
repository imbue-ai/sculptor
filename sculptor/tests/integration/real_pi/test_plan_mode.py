"""Real pi integration tests: plan mode.

Mirrors ``real_claude/test_plan_mode.py`` for pi. Plan mode is delivered by the
pinned ``sculptor_backchannel`` extension: Sculptor drives entry via the
chat-input plan-first toggle (the ``enter_plan_mode`` flag + a plan-mode prompt
preamble), the model presents a plan and calls the ``exit_plan_mode`` tool, and
that tool's blocking dialog surfaces as the Sculptor plan-approval prompt.

Divergences (REQ-CAP-ALL-3, justified in the MR):
- Plan entry is the Sculptor chat-input toggle, not a native prompt-driven mode
  (pi has no native plan mode); unlike Claude we click the toggle rather than
  saying "enter plan mode".
- No interrupt-during-plan mirror — interruption is a separate capability
  (``supports_interruption``), still False for pi.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import prefixed
from tests.integration.real_pi.helpers import real_pi


@real_pi
@pytest.mark.timeout(300)
def test_plan_mode_enter_and_approve(sculptor_instance_: SculptorInstance) -> None:
    """Toggle plan mode, have pi present a plan via exit_plan_mode, approve it."""
    page = sculptor_instance_.page

    # First turn just gets the workspace ready with the chat input + toggle visible.
    task_page = create_pi_workspace_and_send(
        sculptor_instance_, "Reply with exactly: READY.", workspace_name="Real Pi Plan Mode"
    )
    chat_panel = task_page.get_chat_panel()

    # Enter plan mode via the chat-input toggle, then send the planning request.
    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_be_visible()
    toggle.click()
    expect(toggle).to_have_attribute("data-active", "true")
    send_chat_message(
        chat_panel=chat_panel,
        message=prefixed(
            "Present a short plan to create a hello.txt file containing 'hello world', then call the "
            + "exit_plan_mode tool to ask me to approve it. Do not create the file until I approve."
        ),
    )

    # The plan-approval prompt appears once pi calls exit_plan_mode.
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(auq_panel.get_question_text().filter(has_text="proceed").first).to_be_visible()

    # Approve; plan mode clears and the agent proceeds.
    auq_panel.select_option("Approve plan")
    auq_panel.submit()

    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_error_block()).to_have_count(0)
    expect(chat_panel.get_plan_mode_toggle()).to_have_attribute("data-active", "false")


@real_pi
@pytest.mark.timeout(600)
def test_plan_mode_with_revision(sculptor_instance_: SculptorInstance) -> None:
    """Revise pi's plan via the 'Revise' affordance; pi re-plans, then we approve."""
    page = sculptor_instance_.page

    task_page = create_pi_workspace_and_send(
        sculptor_instance_, "Reply with exactly: READY.", workspace_name="Real Pi Plan Revision"
    )
    chat_panel = task_page.get_chat_panel()

    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_be_visible()
    toggle.click()
    expect(toggle).to_have_attribute("data-active", "true")
    send_chat_message(
        chat_panel=chat_panel,
        message=prefixed(
            "Present a plan to create a file called 'original.txt' with the content 'original content', "
            + "then call the exit_plan_mode tool to ask for approval. Do not create the file until I approve."
        ),
    )

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Revise: select the free-form "Other"/"Revise" affordance and type feedback.
    auq_panel.select_option("Other")
    auq_panel.type_other_text("Change the filename to 'revised.txt' instead of 'original.txt'.")
    auq_panel.submit()

    # The revision panel disappears, pi re-plans, and a fresh approval prompt appears.
    expect(auq_panel._locator).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(auq_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    auq_panel.select_option("Approve plan")
    auq_panel.submit()

    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_error_block()).to_have_count(0)
