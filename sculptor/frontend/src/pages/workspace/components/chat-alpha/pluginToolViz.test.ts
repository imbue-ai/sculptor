import type { ComponentType } from "react";
import { describe, expect, it } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import type { PluginToolVisualization } from "~/plugins/pluginRegistry.ts";
import type { ToolCallView, ToolVisualizationDefinition } from "~/plugins/types.ts";

import { buildToolCallView, selectToolVisualization } from "./pluginToolViz.ts";
import type { PillState } from "./toolPill.types.ts";

const NoopBody: ComponentType<{ call: ToolCallView }> = () => null;

/** A registry entry wrapping a definition — only the definition is read by dispatch. */
const entry = (definition: Partial<ToolVisualizationDefinition> & { id: string }): PluginToolVisualization => ({
  definition: { toolNames: ["Workflow"], body: NoopBody, ...definition },
  wrappedBody: () => null,
  pluginId: `plugin-${definition.id}`,
});

const callFor = (overrides: Partial<ToolCallView> = {}): ToolCallView => ({
  id: "call-1",
  toolName: "Workflow",
  agentType: "claude",
  input: {},
  status: "success",
  invocation: null,
  result: null,
  durationSeconds: null,
  ...overrides,
});

describe("selectToolVisualization", () => {
  it("matches only registrations whose toolNames contain the call's tool name (exact)", () => {
    const defs = [entry({ id: "a", toolNames: ["Read"] }), entry({ id: "b", toolNames: ["Workflow"] })];
    expect(selectToolVisualization(defs, callFor({ toolName: "Workflow" }))?.definition.id).toBe("b");
    expect(selectToolVisualization(defs, callFor({ toolName: "Workflo" }))).toBeNull();
    expect(selectToolVisualization(defs, callFor({ toolName: "mcp__srv__Workflow" }))).toBeNull();
  });

  it("does not match a scoped registration against a null agentType", () => {
    const defs = [entry({ id: "a", agentTypes: ["claude"] })];
    expect(selectToolVisualization(defs, callFor({ agentType: null }))).toBeNull();
  });

  it("matches an unscoped registration against a null agentType", () => {
    const defs = [entry({ id: "a" })];
    expect(selectToolVisualization(defs, callFor({ agentType: null }))?.definition.id).toBe("a");
  });

  it("filters by agentTypes when scoped", () => {
    const defs = [entry({ id: "a", agentTypes: ["pi", "registered:my-tool"] })];
    expect(selectToolVisualization(defs, callFor({ agentType: "claude" }))).toBeNull();
    expect(selectToolVisualization(defs, callFor({ agentType: "pi" }))?.definition.id).toBe("a");
    expect(selectToolVisualization(defs, callFor({ agentType: "registered:my-tool" }))?.definition.id).toBe("a");
  });

  it("skips a candidate whose canRender returns false and falls through to the next", () => {
    const defs = [
      entry({ id: "keep", toolNames: ["Workflow"] }),
      entry({ id: "decline", toolNames: ["Workflow"], canRender: () => false }),
    ];
    // "decline" is later (last-wins) but declines, so the earlier "keep" survives.
    expect(selectToolVisualization(defs, callFor())?.definition.id).toBe("keep");
  });

  it("treats a throwing canRender as declined rather than fatal", () => {
    const defs = [
      entry({ id: "keep", toolNames: ["Workflow"] }),
      entry({
        id: "throws",
        toolNames: ["Workflow"],
        canRender: () => {
          throw new Error("boom");
        },
      }),
    ];
    expect(() => selectToolVisualization(defs, callFor())).not.toThrow();
    expect(selectToolVisualization(defs, callFor())?.definition.id).toBe("keep");
  });

  it("returns null when every candidate declines", () => {
    const defs = [entry({ id: "a", canRender: () => false })];
    expect(selectToolVisualization(defs, callFor())).toBeNull();
  });

  it("lets the last-registered survivor win among eligible candidates", () => {
    const defs = [entry({ id: "first", toolNames: ["Workflow"] }), entry({ id: "second", toolNames: ["Workflow"] })];
    expect(selectToolVisualization(defs, callFor())?.definition.id).toBe("second");
  });
});

const useBlock = (overrides: Partial<ToolUseBlock> = {}): ToolUseBlock => ({
  type: "tool_use",
  id: "tool-1",
  name: "Workflow",
  input: { script: "x" },
  ...overrides,
});

const resultBlock = (overrides: Partial<ToolResultBlock> = {}): ToolResultBlock => ({
  type: "tool_result",
  toolUseId: "tool-1",
  toolName: "Workflow",
  invocationString: "Workflow(...)",
  content: { contentType: "generic", text: "done" },
  ...overrides,
});

describe("buildToolCallView", () => {
  const build = (block: ToolUseBlock | null, result: ToolResultBlock | null, pillState: PillState): ToolCallView =>
    buildToolCallView({ block, result, pillState, agentType: "claude" });

  it("maps pill state to status (initializing → running, error → error, else success)", () => {
    expect(build(useBlock(), null, "initializing").status).toBe("running");
    expect(build(useBlock(), resultBlock({ isError: true }), "error").status).toBe("error");
    expect(build(useBlock(), resultBlock(), "completed").status).toBe("success");
  });

  it("carries block input and id/toolName from the block when present", () => {
    const call = build(useBlock({ input: { script: "hi" } }), null, "initializing");
    expect(call.id).toBe("tool-1");
    expect(call.toolName).toBe("Workflow");
    expect(call.input).toEqual({ script: "hi" });
  });

  it("builds a result-only call: null input, id/toolName from the result", () => {
    const call = build(null, resultBlock({ toolUseId: "res-9", toolName: "Workflow" }), "completed");
    expect(call.input).toBeNull();
    expect(call.id).toBe("res-9");
    expect(call.toolName).toBe("Workflow");
  });

  it("extracts result text from GenericToolContent and flags errors", () => {
    const ok = build(useBlock(), resultBlock({ content: { contentType: "generic", text: "output" } }), "completed");
    expect(ok.result).toEqual({ text: "output", isError: false });

    const errored = build(
      useBlock(),
      resultBlock({ isError: true, content: { contentType: "generic", text: "nope" } }),
      "error",
    );
    expect(errored.result).toEqual({ text: "nope", isError: true });
  });

  it("leaves result null while the call is still running", () => {
    expect(build(useBlock(), null, "initializing").result).toBeNull();
  });

  it("reports null duration when the result carries none", () => {
    expect(build(useBlock(), resultBlock({ durationSeconds: null }), "completed").durationSeconds).toBeNull();
    expect(build(useBlock(), resultBlock({ durationSeconds: 2.5 }), "completed").durationSeconds).toBe(2.5);
  });

  it("prefers the block invocation string, falling back to the result's", () => {
    expect(build(useBlock({ invocationString: "from-block" }), resultBlock(), "completed").invocation).toBe(
      "from-block",
    );
    expect(build(null, resultBlock({ invocationString: "from-result" }), "completed").invocation).toBe("from-result");
  });
});
