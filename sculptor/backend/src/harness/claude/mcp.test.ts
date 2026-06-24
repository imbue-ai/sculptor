import { describe, expect, it, vi } from "vitest";

import {
  formatAskUserQuestionResult,
  formatExitPlanModeResult,
  isPlanApproval,
  SculptorMcpServer,
  type UserQuestionAnswer,
  validateArguments,
} from "~/harness/claude/mcp";

const VALID_QUESTION = {
  question: "Pick one",
  header: "Choice",
  options: [
    { label: "A", description: "first" },
    { label: "B", description: "second" },
  ],
  multiSelect: false,
};

describe("validateArguments", () => {
  it("accepts a well-formed ask_user_question call", () => {
    expect(
      validateArguments("mcp__sculptor__ask_user_question", {
        questions: [VALID_QUESTION],
      }),
    ).toBeNull();
  });

  it("rejects missing/oversized questions and bad types", () => {
    expect(validateArguments("mcp__sculptor__ask_user_question", {})).toMatch(
      /missing required field 'questions'/,
    );
    expect(
      validateArguments("mcp__sculptor__ask_user_question", { questions: [] }),
    ).toMatch(/1-4 items/);
    expect(
      validateArguments("mcp__sculptor__ask_user_question", {
        questions: [{ ...VALID_QUESTION, multiSelect: "false" }],
      }),
    ).toMatch(/required schema/);
    expect(
      validateArguments("mcp__sculptor__ask_user_question", {
        questions: [
          { ...VALID_QUESTION, options: [{ label: "A", description: "x" }] },
        ],
      }),
    ).toMatch(/options' must contain 2-10/);
  });

  it("accepts any object for exit_plan_mode", () => {
    expect(validateArguments("mcp__sculptor__exit_plan_mode", {})).toBeNull();
  });
});

describe("SculptorMcpServer", () => {
  it("answers initialize / tools/list", () => {
    const respond = vi.fn();
    const server = new SculptorMcpServer(respond);
    server.handleMessage("c1", { method: "initialize", id: 1 });
    expect(respond.mock.calls[0]?.[1]).toMatchObject({
      mcp_response: { id: 1, result: { serverInfo: { name: "sculptor" } } },
    });

    server.handleMessage("c2", { method: "tools/list", id: 2 });
    const tools = (
      respond.mock.calls[1]?.[1] as {
        mcp_response: { result: { tools: { name: string }[] } };
      }
    ).mcp_response.result.tools;
    expect(tools.map((t) => t.name)).toEqual([
      "ask_user_question",
      "exit_plan_mode",
    ]);
  });

  it("holds a tools/call until the answer is delivered", () => {
    const respond = vi.fn();
    const server = new SculptorMcpServer(respond);
    server.registerToolUseId("tu_1", "mcp__sculptor__ask_user_question");
    server.handleMessage("c3", {
      method: "tools/call",
      id: 5,
      params: {
        name: "ask_user_question",
        arguments: { questions: [VALID_QUESTION] },
      },
    });
    // Held — no response yet.
    expect(respond).not.toHaveBeenCalled();
    expect(server.hasPendingCall("tu_1")).toBe(true);

    const answer: UserQuestionAnswer = {
      message_id: "agm_1",
      tool_use_id: "tu_1",
      question_data: {
        questions: [{ question: "Pick one", header: "Choice", options: [] }],
        tool_use_id: "tu_1",
      },
      answers: { "Pick one": "A" },
      notes: {},
    };
    server.deliverAnswer(answer);
    expect(respond).toHaveBeenCalledTimes(1);
    const payload = respond.mock.calls[0]?.[1] as {
      mcp_response: { id: number; result: { content: { text: string }[] } };
    };
    expect(payload.mcp_response.id).toBe(5);
    expect(payload.mcp_response.result.content[0]?.text).toContain(
      '"Pick one"="A"',
    );
  });

  it("returns a JSON-RPC error for malformed tools/call arguments", () => {
    const respond = vi.fn();
    const server = new SculptorMcpServer(respond);
    server.registerToolUseId("tu_1", "mcp__sculptor__ask_user_question");
    server.handleMessage("c4", {
      method: "tools/call",
      id: 6,
      params: { name: "ask_user_question", arguments: { questions: [] } },
    });
    expect(respond.mock.calls[0]?.[1]).toMatchObject({
      mcp_response: { error: { code: -32602 } },
    });
  });
});

describe("result formatters", () => {
  const planAnswer = (answers: Record<string, string>): UserQuestionAnswer => ({
    message_id: "m",
    tool_use_id: "t",
    question_data: {
      questions: [
        {
          question: "Planning complete. How would you like to proceed?",
          header: "Plan approval",
          options: [],
        },
      ],
      tool_use_id: "t",
    },
    answers,
    notes: {},
  });

  it("formats an answered question and a dismissal", () => {
    const base: UserQuestionAnswer = {
      message_id: "m",
      tool_use_id: "t",
      question_data: {
        questions: [{ question: "Q1", header: "H", options: [] }],
        tool_use_id: "t",
      },
      answers: { Q1: "yes" },
      notes: { Q1: "because" },
    };
    expect(formatAskUserQuestionResult(base)).toBe(
      'User has answered your questions: "Q1"="yes" user notes: because. You can now continue with the user\'s answers in mind.',
    );
    expect(
      formatAskUserQuestionResult({
        ...base,
        answers: { Q1: "[Dismissed]" },
        notes: {},
      }),
    ).toMatch(/User dismissed the question/);
  });

  it("detects plan approval vs revision", () => {
    expect(
      isPlanApproval(
        planAnswer({
          "Planning complete. How would you like to proceed?": "Approve plan",
        }),
      ),
    ).toBe(true);
    expect(
      formatExitPlanModeResult(
        planAnswer({
          "Planning complete. How would you like to proceed?": "Approve plan",
        }),
      ),
    ).toMatch(/approved your plan/);
    expect(
      formatExitPlanModeResult(
        planAnswer({
          "Planning complete. How would you like to proceed?":
            "please change X",
        }),
      ),
    ).toMatch(/User feedback on this plan: please change X/);
  });
});
