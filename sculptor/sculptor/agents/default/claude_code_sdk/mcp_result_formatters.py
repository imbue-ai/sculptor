"""Pure formatters that turn a `UserQuestionAnswerMessage` into the `text`
payload of a successful MCP `tool_result.content[]` block.

Most strings here are pinned byte-for-byte to the native Claude Code CLI's
output (extracted from the 2.1.117 binary). The pinning matters because
Claude was trained on these exact strings; any drift can change downstream
reasoning. The exceptions are the dismissal strings (`_AUQ_DISMISSED_TEXT`
and `_PLAN_DISMISSED_TEXT`): the native CLI tells the agent to "Proceed
using your best judgment" on dismiss, but Sculptor has no Ctrl+C / Esc
equivalent that interrupts the agent — Dismiss is the user's stop signal.
We override those strings deliberately to make dismiss mean "stop and
wait for further instructions".
"""

from sculptor.agents.default.claude_code_sdk.process_manager_utils import is_plan_approval
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage

_AUQ_DISMISSED_TEXT = "User dismissed the question(s) without answering. Stop and wait for the user to provide further instructions before taking any more actions."

# Sentinel the frontend writes into `answers` when the user dismisses an AUQ
# (see AlphaChatInterface.tsx `handleDismissQuestion`). The frontend uses it
# to render a "Dismissed" badge in chat history, so we keep it in the
# persisted message — but for purposes of the agent-facing tool result we
# treat it as equivalent to no answer.
_DISMISSED_ANSWER_VALUE = "[Dismissed]"

_PLAN_APPROVED_TEXT = (
    "User has approved your plan. You can now start coding. Start with updating your todo list if applicable"
)

_PLAN_REJECTED_FIRST_LINE = "The agent proposed a plan that was rejected by the user. The user chose to stay in plan mode rather than proceed with implementation."

_PLAN_DISMISSED_TEXT = "User dismissed the plan approval without responding. Stop and wait for the user to provide further instructions before taking any more actions."


def format_ask_user_question_result(message: UserQuestionAnswerMessage) -> str:
    """Format a successful AskUserQuestion answer as the native CLI does.

    Returns the dismissal text when no question received a non-empty answer
    (or every answer is the `[Dismissed]` sentinel the frontend writes on
    dismiss). Otherwise returns
    `User has answered your questions: <parts>. You can now continue with the user's answers in mind.`,
    where each part is `"Q"="<answers[Q]>"` followed by an optional
    ` user notes: <notes[Q]>` sub-part when the user typed freeform "Other"
    text. The native CLI emits `notes` independently of `answers`; freeform
    text appears in *both* fields, so a freeform-only answer renders as
    `"Q"="<text>" user notes: <text>` (the same value duplicated).
    """
    parts: list[str] = []
    for question in message.question_data.questions:
        answer_value = message.answers.get(question.question, "")
        if not answer_value or answer_value == _DISMISSED_ANSWER_VALUE:
            continue
        sub_parts = [f'"{question.question}"="{answer_value}"']
        notes_value = message.notes.get(question.question, "")
        if notes_value:
            sub_parts.append(f"user notes: {notes_value}")
        parts.append(" ".join(sub_parts))

    if not parts:
        return _AUQ_DISMISSED_TEXT

    joined = ", ".join(parts)
    return f"User has answered your questions: {joined}. You can now continue with the user's answers in mind."


def format_exit_plan_mode_result(message: UserQuestionAnswerMessage) -> str:
    """Format an ExitPlanMode resolution.

    Approval is detected via `is_plan_approval`. Dismissal is detected by the
    `[Dismissed]` sentinel the frontend writes on Dismiss; in that case the
    agent is told to stop and wait (Sculptor-specific override; see module
    docstring). Anything else is a revision request: if the user supplied
    freeform feedback the revision string includes a second
    `User feedback on this plan: …` line, otherwise just the rejection line
    stands alone.
    """
    if is_plan_approval(message):
        return _PLAN_APPROVED_TEXT

    feedback = ""
    is_dismissed = False
    for question in message.question_data.questions:
        answer_value = message.answers.get(question.question, "").strip()
        if answer_value == _DISMISSED_ANSWER_VALUE:
            is_dismissed = True
            continue
        if answer_value:
            feedback = answer_value

    if is_dismissed and not feedback:
        return _PLAN_DISMISSED_TEXT

    if feedback:
        return f"{_PLAN_REJECTED_FIRST_LINE}\nUser feedback on this plan: {feedback}"
    return _PLAN_REJECTED_FIRST_LINE
