from sculptor.foundation.state.chat_state import AskUserQuestionData
from sculptor.foundation.state.chat_state import QuestionOption
from sculptor.foundation.state.chat_state import UserQuestion
from sculptor.foundation.state.chat_state import make_plan_approval_question
from sculptor.agents.default.claude_code_sdk.mcp_result_formatters import format_ask_user_question_result
from sculptor.agents.default.claude_code_sdk.mcp_result_formatters import format_exit_plan_mode_result
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage


def _build_message(
    questions: list[UserQuestion],
    answers: dict[str, str],
    notes: dict[str, str] | None = None,
    tool_use_id: str = "toolu_test",
) -> UserQuestionAnswerMessage:
    return UserQuestionAnswerMessage(
        answers=answers,
        notes=notes or {},
        question_data=AskUserQuestionData(questions=questions, tool_use_id=tool_use_id),
        tool_use_id=tool_use_id,
    )


def test_ask_user_question_single_select() -> None:
    question = UserQuestion(
        question="Favorite color?",
        header="Color",
        options=[
            QuestionOption(label="Blue", description=""),
            QuestionOption(label="Red", description=""),
        ],
        multi_select=False,
    )
    message = _build_message([question], {"Favorite color?": "Blue"})
    expected = 'User has answered your questions: "Favorite color?"="Blue". You can now continue with the user\'s answers in mind.'
    assert format_ask_user_question_result(message) == expected


def test_ask_user_question_multi_select() -> None:
    question = UserQuestion(
        question="Pick languages",
        header="Languages",
        options=[
            QuestionOption(label="Python", description=""),
            QuestionOption(label="Rust", description=""),
        ],
        multi_select=True,
    )
    message = _build_message([question], {"Pick languages": "Python, Rust"})
    expected = 'User has answered your questions: "Pick languages"="Python, Rust". You can now continue with the user\'s answers in mind.'
    assert format_ask_user_question_result(message) == expected


def test_ask_user_question_two_questions_joined_with_comma_space() -> None:
    q1 = UserQuestion(
        question="First?",
        header="First",
        options=[QuestionOption(label="Yes", description="")],
        multi_select=False,
    )
    q2 = UserQuestion(
        question="Second?",
        header="Second",
        options=[QuestionOption(label="No", description="")],
        multi_select=False,
    )
    message = _build_message([q1, q2], {"First?": "Yes", "Second?": "No"})
    expected = 'User has answered your questions: "First?"="Yes", "Second?"="No". You can now continue with the user\'s answers in mind.'
    assert format_ask_user_question_result(message) == expected


def test_ask_user_question_freeform_only_duplicates_text_in_answer_and_notes() -> None:
    """Native CLI puts the freeform 'Other' text in BOTH ``answers[Q]`` and
    ``notes[Q]`` (T = freeform text, notes = freeform text).  The frontend
    submits the same value in both fields when the user typed Other text
    without selecting any predefined option.
    """
    question = UserQuestion(
        question="Anything else?",
        header="Other",
        options=[QuestionOption(label="No", description="")],
        multi_select=False,
        other_label="Other",
    )
    message = _build_message([question], {"Anything else?": "foo"}, notes={"Anything else?": "foo"})
    expected = 'User has answered your questions: "Anything else?"="foo" user notes: foo. You can now continue with the user\'s answers in mind.'
    assert format_ask_user_question_result(message) == expected


def test_ask_user_question_mixed_select_and_freeform_appends_user_notes() -> None:
    """When the user selects predefined options AND types freeform text, the
    answer string carries the comma-joined labels followed by the freeform
    text (matching the native CLI), and ``notes[Q]`` carries just the
    freeform text — rendered as a separate ``user notes:`` sub-part.
    """
    question = UserQuestion(
        question="Cuisines?",
        header="Cuisines",
        options=[
            QuestionOption(label="Italian", description=""),
            QuestionOption(label="Thai", description=""),
        ],
        multi_select=True,
        other_label="Other",
    )
    message = _build_message(
        [question],
        {"Cuisines?": "Italian, Chinese"},
        notes={"Cuisines?": "Chinese"},
    )
    expected = 'User has answered your questions: "Cuisines?"="Italian, Chinese" user notes: Chinese. You can now continue with the user\'s answers in mind.'
    assert format_ask_user_question_result(message) == expected


def test_ask_user_question_selected_only_omits_user_notes() -> None:
    """When the user selects predefined options and does NOT type freeform
    text, the result omits the ``user notes:`` sub-part entirely (matching
    the native CLI, which only emits ``notes`` annotations when the user
    typed something).
    """
    question = UserQuestion(
        question="Languages?",
        header="Languages",
        options=[
            QuestionOption(label="Python", description=""),
            QuestionOption(label="Rust", description=""),
        ],
        multi_select=True,
    )
    message = _build_message([question], {"Languages?": "Python, Rust"})
    expected = 'User has answered your questions: "Languages?"="Python, Rust". You can now continue with the user\'s answers in mind.'
    assert format_ask_user_question_result(message) == expected


def test_ask_user_question_dismissed_returns_dismissal_text() -> None:
    question = UserQuestion(
        question="Do you want X?",
        header="X",
        options=[QuestionOption(label="Yes", description="")],
        multi_select=False,
    )
    message = _build_message([question], {})
    expected = "User dismissed the question(s) without answering. Stop and wait for the user to provide further instructions before taking any more actions."
    assert format_ask_user_question_result(message) == expected


def test_ask_user_question_dismissed_sentinel_value_returns_dismissal_text() -> None:
    """The frontend's dismiss handler writes the literal `[Dismissed]` sentinel
    into `answers` (not an empty value), so the formatter must recognize that
    sentinel as equivalent to dismissal — otherwise the agent would receive a
    bogus `"Q"="[Dismissed]"` "answer" and keep working."""
    q1 = UserQuestion(
        question="Do you want X?",
        header="X",
        options=[QuestionOption(label="Yes", description="")],
        multi_select=False,
    )
    q2 = UserQuestion(
        question="Do you want Y?",
        header="Y",
        options=[QuestionOption(label="Yes", description="")],
        multi_select=False,
    )
    message = _build_message([q1, q2], {"Do you want X?": "[Dismissed]", "Do you want Y?": "[Dismissed]"})
    expected = "User dismissed the question(s) without answering. Stop and wait for the user to provide further instructions before taking any more actions."
    assert format_ask_user_question_result(message) == expected


def test_exit_plan_mode_approved_has_no_trailing_period() -> None:
    question_data = make_plan_approval_question("toolu_plan")
    message = UserQuestionAnswerMessage(
        answers={question_data.questions[0].question: "Approve plan"},
        question_data=question_data,
        tool_use_id="toolu_plan",
    )
    expected = (
        "User has approved your plan. You can now start coding. Start with updating your todo list if applicable"
    )
    assert format_exit_plan_mode_result(message) == expected


def test_exit_plan_mode_revision_uses_newline_before_feedback_line() -> None:
    question_data = make_plan_approval_question("toolu_plan")
    message = UserQuestionAnswerMessage(
        answers={question_data.questions[0].question: "rework step 2 please"},
        question_data=question_data,
        tool_use_id="toolu_plan",
    )
    expected = "The agent proposed a plan that was rejected by the user. The user chose to stay in plan mode rather than proceed with implementation.\nUser feedback on this plan: rework step 2 please"
    assert format_exit_plan_mode_result(message) == expected


def test_exit_plan_mode_no_answer_returns_single_rejection_line() -> None:
    """When there is no answer at all (not the realistic Dismiss path — see
    `test_exit_plan_mode_dismissed_sentinel_value_returns_stop_and_wait` for
    that), the formatter returns the bare rejection line with no feedback."""
    question_data = make_plan_approval_question("toolu_plan")
    message = UserQuestionAnswerMessage(
        answers={},
        question_data=question_data,
        tool_use_id="toolu_plan",
    )
    expected = "The agent proposed a plan that was rejected by the user. The user chose to stay in plan mode rather than proceed with implementation."
    assert format_exit_plan_mode_result(message) == expected


def test_exit_plan_mode_dismissed_sentinel_value_returns_stop_and_wait() -> None:
    """When the user clicks Dismiss on the plan approval prompt, the frontend
    writes `[Dismissed]` into the answer (same sentinel as AUQ dismiss). The
    formatter must recognize that and tell the agent to stop and wait —
    otherwise the agent gets a bogus `User feedback on this plan: [Dismissed]`
    revision request and keeps revising the plan."""
    question_data = make_plan_approval_question("toolu_plan")
    message = UserQuestionAnswerMessage(
        answers={question_data.questions[0].question: "[Dismissed]"},
        question_data=question_data,
        tool_use_id="toolu_plan",
    )
    expected = "User dismissed the plan approval without responding. Stop and wait for the user to provide further instructions before taking any more actions."
    assert format_exit_plan_mode_result(message) == expected
