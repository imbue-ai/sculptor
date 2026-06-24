// Shared contract for pi's interactive-backchannel extension, ported from
// `pi_agent/backchannel.py`. The pinned `sculptor_backchannel` extension
// registers `ask_user_question` + `exit_plan_mode`, each opening a blocking pi
// dialog surfaced as an `extension_ui_request`; Sculptor maps both onto the
// harness-agnostic `AskUserQuestionAgentMessage` and routes the answer back as
// the matching `extension_ui_response`.

import type {
  AskUserQuestionData,
  UserQuestionAnswer,
} from "~/harness/claude/mcp";

export const ASK_USER_QUESTION_TOOL_NAME = "ask_user_question";
export const EXIT_PLAN_MODE_TOOL_NAME = "exit_plan_mode";
// Sentinel title the extension's exit_plan_mode tool passes to ctx.ui.select.
export const PLAN_APPROVAL_DIALOG_TITLE = "__sculptor_plan_approval__";
// Pi questions carry only a title + options (no per-question category).
const PI_QUESTION_HEADER = "Question";
const DISMISSED_ANSWER_VALUE = "[Dismissed]";
const PLAN_APPROVAL_HEADER = "Plan approval";
const PLAN_APPROVE_ANSWER = "Approve plan";

// The canonical Sculptor plan-approval question (matches the Claude path's
// `make_plan_approval_question`). Pi presents the plan inline, so there is no
// plan-file path to surface.
export function makePlanApprovalQuestion(
  toolUseId: string,
): AskUserQuestionData {
  return {
    questions: [
      {
        question: "Planning complete. How would you like to proceed?",
        header: PLAN_APPROVAL_HEADER,
        options: [
          {
            label: PLAN_APPROVE_ANSWER,
            description: "Proceed with implementing the plan",
          },
        ],
        multi_select: false,
        other_label: "Revise",
      },
    ],
    tool_use_id: toolUseId,
    plan_file_path: null,
  };
}

// Build the single-question AskUserQuestionData for a pi ask-user-question.
// Empty options → free-form; non-empty → multiple choice. Mirrors
// `build_ask_user_question_data`.
export function buildAskUserQuestionData(
  question: string,
  options: string[],
  toolUseId: string,
): AskUserQuestionData {
  return {
    questions: [
      {
        question,
        header: PI_QUESTION_HEADER,
        options: options.map((option) => ({ label: option, description: "" })),
        multi_select: false,
        other_label: "Other",
      },
    ],
    tool_use_id: toolUseId,
    plan_file_path: null,
  };
}

export function isPlanApproval(answer: UserQuestionAnswer): boolean {
  if (
    !answer.question_data.questions.some(
      (q) => q.header === PLAN_APPROVAL_HEADER,
    )
  ) {
    return false;
  }
  return Object.values(answer.answers).some(
    (v) => v.trim() === PLAN_APPROVE_ANSWER,
  );
}

function singleAnswerValue(answer: UserQuestionAnswer): string | null {
  for (const question of answer.question_data.questions) {
    const value = answer.answers[question.question];
    if (value) {
      return value;
    }
  }
  for (const value of Object.values(answer.answers)) {
    if (value) {
      return value;
    }
  }
  return null;
}

// Build the `extension_ui_response` body (sans type/id). A dismissed/empty
// answer becomes a cancellation. Mirrors `extension_ui_response_body`.
export function extensionUiResponseBody(
  answer: UserQuestionAnswer,
): Record<string, unknown> {
  const value = singleAnswerValue(answer);
  if (value === null || value === DISMISSED_ANSWER_VALUE) {
    return { cancelled: true };
  }
  return { value };
}
