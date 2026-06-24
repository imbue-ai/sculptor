import { describe, expect, it } from "vitest";

import {
  buildInitializeControlRequest,
  buildInterruptControlRequest,
  buildStdinUserMessage,
  getClaudeCommand,
  modelShortnameFor,
  shellQuote,
} from "~/harness/claude/launch";

describe("getClaudeCommand", () => {
  it("always emits the load-bearing launch contract", () => {
    const [bash, dashC, command] = getClaudeCommand({
      binaryPath: "/bin/claude",
      systemPrompt: "",
      enableStreaming: true,
    });
    expect(bash).toBe("bash");
    expect(dashC).toBe("-c");
    expect(command).toContain("exec env IS_SANDBOX=1 /bin/claude");
    expect(command).toContain(
      "--dangerously-skip-permissions --permission-prompt-tool stdio",
    );
    expect(command).toContain("--output-format=stream-json --verbose");
    expect(command).toContain("--input-format stream-json");
    expect(command).toContain("--include-hook-events");
    expect(command).toContain("--include-partial-messages");
    expect(command).toContain(
      `--mcp-config '${JSON.stringify({ mcpServers: { sculptor: { type: "sdk", name: "sculptor" } } })}'`,
    );
    expect(command).toContain(
      "--disallowed-tools AskUserQuestion,ExitPlanMode",
    );
    // No conditional flags when not provided.
    expect(command).not.toContain("--resume");
    expect(command).not.toContain("--model");
    expect(command).not.toContain("--settings");
    expect(command).not.toContain("--effort");
  });

  it("adds conditional flags when provided", () => {
    const [, , command] = getClaudeCommand({
      binaryPath: "/bin/claude",
      systemPrompt: "be helpful",
      sessionId: "sess_1",
      modelShortname: "opus[1m]",
      fastMode: true,
      effort: "xhigh",
    });
    expect(command).toContain("--resume sess_1");
    expect(command).toContain("--append-system-prompt 'be helpful'");
    expect(command).toContain("--model 'opus[1m]'");
    expect(command).toContain(
      `--settings '${JSON.stringify({ fastMode: true })}'`,
    );
    expect(command).toContain("--effort xhigh");
  });
});

describe("shellQuote", () => {
  it("quotes only when necessary and escapes single quotes", () => {
    expect(shellQuote("plain")).toBe("plain");
    expect(shellQuote("")).toBe("''");
    expect(shellQuote("has space")).toBe("'has space'");
    expect(shellQuote("it's")).toBe("'it'\\''s'");
  });
});

describe("modelShortnameFor", () => {
  it("maps known models and omits unknown / fake", () => {
    expect(modelShortnameFor("CLAUDE-4-OPUS")).toBe("opus[1m]");
    expect(modelShortnameFor("CLAUDE-4-SONNET-200K")).toBe("sonnet");
    expect(modelShortnameFor("FAKE_CLAUDE")).toBeNull();
    expect(modelShortnameFor(null)).toBeNull();
  });
});

describe("stdin control messages", () => {
  it("builds the user-message envelope with an empty session id", () => {
    expect(JSON.parse(buildStdinUserMessage("hello"))).toEqual({
      type: "user",
      session_id: "",
      message: { role: "user", content: "hello" },
      parent_tool_use_id: null,
    });
  });

  it("builds the PreCompact initialize request", () => {
    const req = JSON.parse(
      buildInitializeControlRequest("sculptor_pre_compact", "req_init_1"),
    );
    expect(req.request.subtype).toBe("initialize");
    expect(req.request.hooks.PreCompact).toEqual([
      { matcher: "auto", hookCallbackIds: ["sculptor_pre_compact"] },
      { matcher: "manual", hookCallbackIds: ["sculptor_pre_compact"] },
    ]);
  });

  it("builds the interrupt request", () => {
    expect(JSON.parse(buildInterruptControlRequest("req_interrupt_1"))).toEqual(
      {
        type: "control_request",
        request_id: "req_interrupt_1",
        request: { subtype: "interrupt" },
      },
    );
  });
});
