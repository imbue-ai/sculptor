"""Real pi integration tests: AskUserQuestion.

Mirrors ``real_claude/test_ask_user_question.py`` for pi. The interactive
backchannel is delivered by the pinned ``sculptor_backchannel`` extension (loaded
with the real pi binary), whose ``ask_user_question`` tool opens a blocking pi
dialog that Sculptor surfaces as the Q&A panel.

Divergence (REQ-CAP-ALL-3): pi's ``ask_user_question`` tool asks one question per
call (the ``ctx.ui.select``/``input`` dialog is single-question), so there is no
real-pi mirror of Claude's multiple-questions-in-one-call test; the model simply
calls the tool again for a second question.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import real_pi


@real_pi
@pytest.mark.timeout(300)
def test_ask_user_question_single(sculptor_instance_: SculptorInstance) -> None:
    """Pi asks a single multiple-choice question; the user answers; the agent finishes."""
    page = sculptor_instance_.page

    task_page = create_pi_workspace_and_send(
        sculptor_instance_,
        (
            "Before doing anything else, you MUST call the ask_user_question tool exactly once with "
            + "question 'What is your favorite color?' and options ['Red', 'Blue', 'Green']. "
            + "Do not do anything else until I answer."
        ),
        workspace_name="Real Pi AUQ",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(ask_panel.get_question_text().filter(has_text="favorite color").first).to_be_visible()

    ask_panel.select_option("Blue")
    ask_panel.submit()

    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_error_block()).to_have_count(0)


@real_pi
@pytest.mark.timeout(300)
def test_ask_user_question_free_text(sculptor_instance_: SculptorInstance) -> None:
    """Pi asks a question; the user answers via the free-form 'Other' affordance."""
    page = sculptor_instance_.page

    task_page = create_pi_workspace_and_send(
        sculptor_instance_,
        (
            "You MUST call the ask_user_question tool exactly once, right now, before doing anything else, "
            + "with question 'What should I name the file?' and options ['default.txt']. "
            + "Wait for my answer, then reply with exactly: FREETEXT-DONE."
        ),
        workspace_name="Real Pi AUQ Free Text",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel._locator).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # The "Other" affordance is rendered alongside the provided options, so we can
    # exercise the free-text path regardless of the options the tool was called with.
    ask_panel.select_option("Other")
    ask_panel.type_other_text("my-custom-name.txt")
    ask_panel.submit()

    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_error_block()).to_have_count(0)
