import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolResultBlock, ToolUseBlock, WorkflowAgentProgress, WorkflowTaskState } from "~/api";
import type * as UseTaskDetailModule from "~/common/state/hooks/useTaskDetail";

import { WorkflowEntry } from "../WorkflowEntry.tsx";
import { formatTokenCount, formatWorkflowDuration } from "../workflowFormat.ts";

let mockWorkflowTaskStates: Record<string, WorkflowTaskState> = {};

vi.mock("~/common/state/hooks/useTaskDetail", async (importOriginal) => {
  const actual = await importOriginal<typeof UseTaskDetailModule>();
  return {
    ...actual,
    useCurrentTaskWorkflowStates: (): Record<string, WorkflowTaskState> => mockWorkflowTaskStates,
  };
});

const TOOL_USE_ID = "toolu_workflow_001";

const makeBlock = (input: Record<string, unknown> = { name: "review-changes" }): ToolUseBlock => ({
  id: TOOL_USE_ID,
  name: "Workflow",
  type: "tool_use",
  input,
});

const makeResult = (): ToolResultBlock => ({
  toolUseId: TOOL_USE_ID,
  toolName: "Workflow",
  invocationString: "review-changes",
  content: {
    contentType: "generic",
    text: "Workflow launched in background. Task ID: w18genw0r",
  },
  isError: false,
});

const makeAgent = (overrides: Partial<WorkflowAgentProgress> = {}): WorkflowAgentProgress => ({
  objectType: "WorkflowAgentProgress",
  index: 0,
  label: "review:bugs",
  phaseIndex: 0,
  phaseTitle: "Review",
  model: "claude-fable-5",
  state: "progress",
  startedAt: 1748471201000,
  promptPreview: "Review the diff for bugs",
  tokens: 31200,
  durationMs: 61200,
  lastToolSummary: "Grep: TODO in src/",
  ...overrides,
});

const makeState = (overrides: Partial<WorkflowTaskState> = {}): WorkflowTaskState => ({
  objectType: "WorkflowTaskState",
  taskId: "task-wf-1",
  toolUseId: TOOL_USE_ID,
  workflowName: "review-changes",
  status: "running",
  entries: [
    { objectType: "WorkflowPhaseProgress", index: 0, title: "Review", kind: "" },
    makeAgent(),
    makeAgent({ index: 1, label: "verify:bug-1", state: "done", resultPreview: "Confirmed real", tokens: 9800 }),
  ],
  usage: { objectType: "WorkflowUsage", totalTokens: 52310, toolUses: 17, durationMs: 63210 },
  lastToolName: "Grep",
  summary: "",
  ...overrides,
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const renderEntry = (
  block: ToolUseBlock | null = makeBlock(),
  result: ToolResultBlock | null = makeResult(),
): ReturnType<typeof render> =>
  render(<WorkflowEntry block={block} result={result} workspaceCodePath={null} />, { wrapper: Wrapper });

afterEach(() => {
  cleanup();
  mockWorkflowTaskStates = {};
});

describe("WorkflowEntry", () => {
  it("falls back to the launch acknowledgement when no workflow state exists", () => {
    renderEntry();
    expect(screen.getByText("review-changes")).toBeInTheDocument();
    expect(screen.getByText(/Workflow launched in background/)).toBeInTheDocument();
  });

  it("renders phases, agent rows, and usage totals while running", () => {
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState() };
    renderEntry();

    expect(screen.getByText("review-changes")).toBeInTheDocument();
    expect(screen.getByText("Running…")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("review:bugs")).toBeInTheDocument();
    expect(screen.getByText("verify:bug-1")).toBeInTheDocument();
    // Status icons: one running dot, one done check.
    expect(screen.getByLabelText("running")).toBeInTheDocument();
    expect(screen.getByLabelText("done")).toBeInTheDocument();
    // Secondary lines: tool activity while running, result preview when done.
    expect(screen.getByText("Grep: TODO in src/")).toBeInTheDocument();
    expect(screen.getByText("Confirmed real")).toBeInTheDocument();
    // Usage meta: tokens · tools · duration.
    expect(screen.getByText("52.3k tokens · 17 tools · 1m 03s")).toBeInTheDocument();
  });

  it("shows the error state for failed agents and the Failed status word", () => {
    mockWorkflowTaskStates = {
      [TOOL_USE_ID]: makeState({
        status: "failed",
        entries: [
          { objectType: "WorkflowPhaseProgress", index: 0, title: "Review", kind: "" },
          makeAgent({ state: "error", error: "agent exploded" }),
        ],
      }),
    };
    renderEntry();

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByLabelText("error")).toBeInTheDocument();
    expect(screen.getByText("agent exploded")).toBeInTheDocument();
  });

  it("marks agents without a start time as queued", () => {
    mockWorkflowTaskStates = {
      [TOOL_USE_ID]: makeState({
        entries: [makeAgent({ state: "start", startedAt: null, queuedAt: 1748471201000 })],
      }),
    };
    renderEntry();
    expect(screen.getByLabelText("queued")).toBeInTheDocument();
  });

  it("shows a starting message while running with an empty tree", () => {
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState({ entries: [] }) };
    renderEntry();
    expect(screen.getByText("Starting workflow…")).toBeInTheDocument();
  });

  it("renders agents with unknown phase indexes in an untitled section", () => {
    mockWorkflowTaskStates = {
      [TOOL_USE_ID]: makeState({
        entries: [makeAgent({ phaseIndex: 7, phaseTitle: "" })],
      }),
    };
    renderEntry();
    expect(screen.getByText("review:bugs")).toBeInTheDocument();
  });

  it("caps agent rows per phase and summarizes the remainder", () => {
    const manyAgents = Array.from({ length: 60 }, (_, index) =>
      makeAgent({
        index,
        label: `agent-${index}`,
        state: index < 55 ? "done" : "progress",
      }),
    );
    mockWorkflowTaskStates = {
      [TOOL_USE_ID]: makeState({
        entries: [{ objectType: "WorkflowPhaseProgress", index: 0, title: "Sweep", kind: "" }, ...manyAgents],
      }),
    };
    renderEntry();

    expect(screen.getByText("agent-49")).toBeInTheDocument();
    expect(screen.queryByText("agent-50")).not.toBeInTheDocument();
    expect(screen.getByText("+10 more (5 running, 5 done)")).toBeInTheDocument();
  });
});

describe("formatTokenCount", () => {
  it("formats token counts compactly", () => {
    expect(formatTokenCount(950)).toBe("950");
    expect(formatTokenCount(52310)).toBe("52.3k");
    expect(formatTokenCount(1_250_000)).toBe("1.3M");
  });
});

describe("formatWorkflowDuration", () => {
  it("formats durations in seconds and minutes", () => {
    expect(formatWorkflowDuration(9500)).toBe("10s");
    expect(formatWorkflowDuration(63210)).toBe("1m 03s");
  });
});
