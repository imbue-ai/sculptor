"""Shared contract for the pi interactive-backchannel extension.

The Sculptor backchannel extension (`extensions/sculptor_backchannel.ts`) and
the Python harness/wrapper that drive it must agree on the tool names and the
plan-approval dialog title. Defining them here once keeps the TypeScript
extension, the harness's gated methods (`PiHarness`), and the dispatcher
(`PiAgent`) in lockstep — renaming a tool means editing this module and the
`.ts` in the same change (REQ-EXT).

The extension registers two tools, each of which opens a blocking pi dialog
(`ctx.ui.select` / `ctx.ui.input`, never with a `timeout`) and surfaces it as an
`extension_ui_request`:

- `ask_user_question` — a single multiple-choice (`select`) or free-form
  (`input`) question.
- `exit_plan_mode` — presents the finished plan for approval via a `select`
  dialog whose title is the plan-approval sentinel below.

Sculptor maps both onto the harness-agnostic `AskUserQuestionAgentMessage`
contract and routes the user's `UserQuestionAnswerMessage` back as the matching
`extension_ui_response`.
"""

from __future__ import annotations

from collections.abc import Sequence

from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import QuestionOption
from sculptor.state.chat_state import UserQuestion
from sculptor.state.chat_state import make_plan_approval_question

# Tool names registered by sculptor_backchannel.ts — MUST match the `.ts`.
ASK_USER_QUESTION_TOOL_NAME: str = "ask_user_question"
EXIT_PLAN_MODE_TOOL_NAME: str = "exit_plan_mode"

# Sentinel title the extension's `exit_plan_mode` tool passes to
# `ctx.ui.select`. Both backchannel dialogs ride the same
# `extension_ui_request{method:"select"}` lane; the dispatcher tells a
# plan-approval dialog apart from a regular ask-user-question by this exact
# title — MUST match the `.ts`.
PLAN_APPROVAL_DIALOG_TITLE: str = "__sculptor_plan_approval__"

# The default header shown for a pi ask-user-question. pi's `ctx.ui.select` /
# `ctx.ui.input` carry only a title and options, so — unlike Claude's AUQ — pi
# questions have no per-question category; this stands in for one.
PI_QUESTION_HEADER: str = "Question"

# Frontend sentinel for a dismissed question / plan (the value the chat UI
# writes when the user dismisses without answering). Mirrors the Claude path's
# `_DISMISSED_ANSWER_VALUE` (`mcp_result_formatters.py`); when the user's answer
# is this, the dispatcher sends `{"cancelled": true}` back to pi's blocked
# dialog so the extension's `execute` resolves to the dismissal branch.
DISMISSED_ANSWER_VALUE: str = "[Dismissed]"

# Derived from the canonical Sculptor plan-approval question so the header and
# approve-label can never drift from `make_plan_approval_question`.
_CANONICAL_PLAN_QUESTION = make_plan_approval_question(tool_use_id="")
PLAN_APPROVAL_HEADER: str = _CANONICAL_PLAN_QUESTION.questions[0].header
PLAN_APPROVE_ANSWER: str = _CANONICAL_PLAN_QUESTION.questions[0].options[0].label


def build_ask_user_question_data(question: str, options: Sequence[str], tool_use_id: str) -> AskUserQuestionData:
    """Build the single-question `AskUserQuestionData` for a pi ask-user-question.

    Shared by the live dispatch (from the `extension_ui_request`) and the
    page-reload reconstruction (from the persisted `ask_user_question` tool
    block) so both render an identical Q&A panel. Empty `options` → a free-form
    question; non-empty → multiple choice. `other_label` always lets the user
    type a free-form answer too.
    """
    return AskUserQuestionData(
        questions=[
            UserQuestion(
                question=question,
                header=PI_QUESTION_HEADER,
                options=[QuestionOption(label=option, description="") for option in options],
                multi_select=False,
                other_label="Other",
            )
        ],
        tool_use_id=tool_use_id,
    )


def is_plan_approval(message: UserQuestionAnswerMessage) -> bool:
    """True when this answer approves (rather than revises/dismisses) a plan.

    Mirrors the Claude path's `is_plan_approval` (`process_manager_utils.py`):
    the question must be the synthesized plan-approval question (header match)
    and the user's answer must be the approve label.
    """
    if not any(question.header == PLAN_APPROVAL_HEADER for question in message.question_data.questions):
        return False
    return any(answer.strip() == PLAN_APPROVE_ANSWER for answer in message.answers.values())


def extension_ui_response_body(message: UserQuestionAnswerMessage) -> dict[str, object]:
    """Build the `extension_ui_response` body (sans `type`/`id`) for an answer.

    The extension's dialogs are single-question `select`/`input` calls, so there
    is exactly one answer to relay back to the blocked dialog. A dismissed answer
    becomes a cancellation (`{"cancelled": true}`); any other answer is sent as
    the dialog `value` (the selected option, or the free-form / "Revise" text —
    pi returns whatever value the client posts).
    """
    value = _single_answer_value(message)
    if value is None or value == DISMISSED_ANSWER_VALUE:
        return {"cancelled": True}
    return {"value": value}


def _single_answer_value(message: UserQuestionAnswerMessage) -> str | None:
    """Return the one answer string for the dialog, or None if there is none.

    Prefers the answer keyed by the question text; falls back to any non-empty
    answer (a single-question dialog has at most one).
    """
    for question in message.question_data.questions:
        answer = message.answers.get(question.question)
        if answer:
            return answer
    for answer in message.answers.values():
        if answer:
            return answer
    return None
