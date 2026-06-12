"""Regression test for SCU-530.

Bug: when the agent emits ``mcp__sculptor__ask_user_question`` and the
underlying CLI request errors out (API timeout, network partition, system
suspend) before the user answers, the runner leaves
``is_waiting_for_question_answer`` permanently set. Subsequent
``ChatInputUserMessage``s are then silently appended to
``queued_user_input_messages`` in
``sculptor/tasks/handlers/run_agent/v1.py`` and never reach the agent.

Fix: clear ``is_waiting_for_question_answer`` when the in-flight chat
request fails or is stopped while still waiting for an AUQ answer.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_tool_blocks
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to keep sending messages after the agent's request fails mid-question")
def test_follow_up_message_after_auq_failure_is_dispatched(sculptor_instance_: SculptorInstance) -> None:
    """SCU-530: a chat message sent after AUQ+failure must reach the agent."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=(
            "fake_claude:ask_user_question_then_api_error `{"
            '"questions": [{'
            '"question": "Pick a color",'
            '"header": "Color",'
            '"options": ['
            '{"label": "Red", "description": "warm"},'
            '{"label": "Blue", "description": "cool"}'
            "],"
            '"multiSelect": false'
            "}],"
            '"message": "API Error: Request timed out"'
            "}`"
        ),
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The AUQ tool block exists in the DOM — proves the agent reached the
    # AUQ-emitting state and the runner saw ``AskUserQuestionAgentMessage``
    # (setting ``is_waiting_for_question_answer``). The block may be
    # collapsed (``hidden``) by default after the failure, so check
    # existence via ``to_have_count`` rather than visibility.
    ask_tool_blocks = get_ask_user_question_tool_blocks(page)
    expect(ask_tool_blocks).to_have_count(1)

    # The request fails — the wrapper emits a RequestFailureAgentMessage and
    # an error block surfaces in chat. ``expect()`` auto-retries until the
    # failure has propagated, so we wait directly on the user-visible
    # artifact rather than on a thinking-indicator proxy.
    expect(chat_panel.get_error_block()).to_be_visible()

    # Send a follow-up without answering the question. Before the fix this
    # message was silently appended to ``queued_user_input_messages`` and the
    # agent never saw it; with the fix it must be dispatched and produce a
    # response echoing the marker text below.
    recovery_marker = "RECOVERY_AFTER_AUQ_FAILURE_MARKER"
    send_chat_message(chat_panel, f'fake_claude:text `{{"text": "{recovery_marker}"}}`')

    # Two messages should contain the marker: the user's follow-up and the
    # agent's echoed reply. With the bug only the user's message exists —
    # the runner silently queues the follow-up and no assistant response
    # ever arrives, so this expect times out at count=1.
    recovery_messages = chat_panel.get_messages().filter(has_text=recovery_marker)
    expect(recovery_messages).to_have_count(2)
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
