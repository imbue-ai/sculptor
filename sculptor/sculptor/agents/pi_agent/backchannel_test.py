"""Tests for the pi backchannel contract helpers (`backchannel.py`)."""

from __future__ import annotations

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.sculptor.state.chat_state import AskUserQuestionData
from imbue_core.sculptor.state.chat_state import QuestionOption
from imbue_core.sculptor.state.chat_state import UserQuestion
from imbue_core.sculptor.state.chat_state import make_plan_approval_question
from sculptor.agents.pi_agent.backchannel import DISMISSED_ANSWER_VALUE
from sculptor.agents.pi_agent.backchannel import PLAN_APPROVAL_HEADER
from sculptor.agents.pi_agent.backchannel import PLAN_APPROVE_ANSWER
from sculptor.agents.pi_agent.backchannel import extension_ui_response_body
from sculptor.agents.pi_agent.backchannel import is_plan_approval
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage


def _answer(answers: dict[str, str], question_data: AskUserQuestionData) -> UserQuestionAnswerMessage:
    return UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers=answers,
        question_data=question_data,
        tool_use_id=question_data.tool_use_id,
    )


def _question(text: str, *, options: list[str]) -> AskUserQuestionData:
    return AskUserQuestionData(
        questions=[
            UserQuestion(
                question=text,
                header="Question",
                options=[QuestionOption(label=o, description="") for o in options],
                multi_select=False,
                other_label="Other",
            )
        ],
        tool_use_id="t1",
    )


def test_plan_approval_constants_track_canonical_question() -> None:
    canonical = make_plan_approval_question(tool_use_id="x")
    assert PLAN_APPROVAL_HEADER == canonical.questions[0].header
    assert PLAN_APPROVE_ANSWER == canonical.questions[0].options[0].label


def test_is_plan_approval_true_only_on_approve() -> None:
    plan = make_plan_approval_question(tool_use_id="p1")
    question_text = plan.questions[0].question
    assert is_plan_approval(_answer({question_text: PLAN_APPROVE_ANSWER}, plan)) is True
    # A revision (free-form text) is not an approval.
    assert is_plan_approval(_answer({question_text: "add a rollback step"}, plan)) is False
    # A non-plan question is never a plan approval, even if answered "Approve plan".
    regular = _question("Proceed?", options=["Approve plan"])
    assert is_plan_approval(_answer({"Proceed?": PLAN_APPROVE_ANSWER}, regular)) is False


def test_extension_ui_response_body_for_selected_value() -> None:
    question = _question("Tea or coffee?", options=["tea", "coffee"])
    assert extension_ui_response_body(_answer({"Tea or coffee?": "coffee"}, question)) == {"value": "coffee"}


def test_extension_ui_response_body_for_free_form_value() -> None:
    question = _question("Your name?", options=[])
    assert extension_ui_response_body(_answer({"Your name?": "Ada"}, question)) == {"value": "Ada"}


def test_extension_ui_response_body_for_dismissal() -> None:
    question = _question("Pick one", options=["a", "b"])
    body = extension_ui_response_body(_answer({"Pick one": DISMISSED_ANSWER_VALUE}, question))
    assert body == {"cancelled": True}


def test_extension_ui_response_body_for_empty_answers_is_cancellation() -> None:
    question = _question("Pick one", options=["a", "b"])
    assert extension_ui_response_body(_answer({}, question)) == {"cancelled": True}
