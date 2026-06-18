from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import make_plan_approval_question


def test_make_plan_approval_question_default_path_is_none() -> None:
    q = make_plan_approval_question(tool_use_id="toolu_x")
    assert q.plan_file_path is None
    assert q.tool_use_id == "toolu_x"


def test_make_plan_approval_question_propagates_plan_file_path() -> None:
    q = make_plan_approval_question(tool_use_id="toolu_x", plan_file_path="/abs/.claude/plans/y.md")
    assert q.plan_file_path == "/abs/.claude/plans/y.md"


def test_make_plan_approval_question_text_is_harness_neutral() -> None:
    # The canonical plan question is shown by every harness (including pi, which
    # is deliberately Claude-free), so it must not name a specific agent.
    question_text = make_plan_approval_question(tool_use_id="toolu_x").questions[0].question
    assert "Claude" not in question_text


def test_ask_user_question_data_deserializes_without_plan_file_path() -> None:
    legacy_payload = {
        "questions": [
            {
                "question": "Pick one",
                "header": "Header",
                "options": [{"label": "A", "description": "first"}],
                "multi_select": False,
            }
        ],
        "tool_use_id": "toolu_legacy",
    }
    parsed = AskUserQuestionData.model_validate(legacy_payload)
    assert parsed.plan_file_path is None
    assert parsed.tool_use_id == "toolu_legacy"
