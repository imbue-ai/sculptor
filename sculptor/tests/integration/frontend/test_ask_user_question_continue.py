"""Integration test: AskUserQuestion when Claude ignores the stop instruction.

Reproduces the scenario where Claude calls AskUserQuestion, gets an error
tool_result from the CLI, and continues working in the same turn instead
of stopping.  This lets us observe the consequences:
- The continuation text gets appended to the same assistant message
- The user sees the question UI and the continuation simultaneously
- After answering, the follow-up invocation produces a separate message

Note: This test does NOT reproduce the message-merge race condition (where
UserQuestionAnswerMessage arrives before RequestSuccessAgentMessage) because
FakeClaude exits instantly, so RequestSuccessAgentMessage always arrives before
the user answers.  The race is covered by the unit test in
message_conversion_test.py::test_user_question_answer_before_request_success_produces_separate_messages.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to observe consequences when the agent continues after AskUserQuestion")
def test_ask_user_question_and_continue(sculptor_instance_: SculptorInstance) -> None:
    """Test what happens when Claude ignores the stop instruction after AskUserQuestion.

    FakeClaude emits AskUserQuestion with an error tool_result, then a follow-up
    assistant text message — all in one process invocation.  This simulates Claude
    treating the AskUserQuestion error as a rejection and continuing to work.

    Observed behavior:
    - The Q&A panel appears (from the AskUserQuestion tool_use block)
    - The continuation text is visible in the first assistant message
    - The agent finishes (process exits after emitting all output)
    - After the user answers, a follow-up invocation produces a separate message
    - Total completed messages: user + assistant(ask+continuation) + assistant(follow-up) = 3
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question_and_continue `{
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
  ],
  "continuation_text": "[FakeClaude] I decided to keep working instead of waiting."
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The Q&A panel should appear from the AskUserQuestion tool_use block
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)

    # Gate Submit on the assistant TurnFooter — it appears only after turn metrics are attached
    # at RequestSuccess, so it forces us to wait for run #1 to fully finalize even while WAITING
    # suppresses the StatusPill (otherwise UQAM clobbers current_request_id and run #1's tail
    # merges into run #2's reply — SCU-699).
    assistant_message = chat_panel.get_messages().nth(1)
    expect(
        assistant_message.get_by_test_id(ElementIDs.TURN_FOOTER),
        "agent run #1 to fully finalize before answering",
    ).to_be_visible(timeout=30_000)

    # At this point we have 2 completed messages:
    # 1. User message (the prompt)
    # 2. Assistant message (AskUserQuestion tool block + continuation text)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Now answer the question — this triggers a follow-up invocation
    auq_panel.select_first_option_and_submit()

    expect(auq_panel).not_to_be_visible()

    # Wait for the follow-up invocation to finish
    expect(chat_panel.get_thinking_indicator(), "agent to finish after answer").not_to_be_visible(timeout=30_000)

    # After the follow-up, we should have 3 completed messages:
    # 1. User message
    # 2. Assistant message (AskUserQuestion + continuation)
    # 3. Assistant message (follow-up response after answer)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)
