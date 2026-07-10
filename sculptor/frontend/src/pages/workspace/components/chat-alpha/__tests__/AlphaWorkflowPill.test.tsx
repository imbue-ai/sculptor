import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolUseBlock, WorkflowAgentProgress, WorkflowTaskState } from "~/api";
import { ElementIds } from "~/api";
import type * as UseTaskDetailModule from "~/common/state/hooks/useTaskDetail";

import { AlphaWorkflowPill } from "../AlphaWorkflowPill.tsx";

let mockWorkflowTaskStates: Record<string, WorkflowTaskState> = {};

vi.mock("~/common/state/hooks/useTaskDetail", async (importOriginal) => {
  const actual = await importOriginal<typeof UseTaskDetailModule>();
  return {
    ...actual,
    useCurrentTaskWorkflowState: (toolUseId: string): WorkflowTaskState | undefined =>
      mockWorkflowTaskStates[toolUseId],
  };
});

const TOOL_USE_ID = "toolu_workflow_001";

const makeBlock = (): ToolUseBlock => ({
  id: TOOL_USE_ID,
  name: "Workflow",
  type: "tool_use",
  input: { name: "review-changes" },
});

const makeAgent = (overrides: Partial<WorkflowAgentProgress> = {}): WorkflowAgentProgress => ({
  objectType: "WorkflowAgentProgress",
  index: 0,
  label: "review:bugs",
  phaseIndex: 0,
  phaseTitle: "Review",
  state: "progress",
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
    makeAgent({ index: 1, label: "review:perf", state: "done" }),
  ],
  usage: { objectType: "WorkflowUsage", totalTokens: 52310, toolUses: 17, durationMs: 63210 },
  lastToolName: "Grep",
  summary: "",
  ...overrides,
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const renderPill = (): ReturnType<typeof render> =>
  render(<AlphaWorkflowPill toolUseId={TOOL_USE_ID} block={makeBlock()} />, { wrapper: Wrapper });

afterEach(() => {
  cleanup();
  mockWorkflowTaskStates = {};
});

describe("AlphaWorkflowPill", () => {
  it("describes the running workflow with its active phase and agent progress", () => {
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState() };
    renderPill();

    const pill = screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL);
    expect(pill).toHaveAttribute("data-workflow-status", "running");
    expect(pill).toHaveTextContent("Workflow review-changes — Review · 1/2 agents");
    expect(pill).toHaveTextContent("1m 03s");
  });

  it("describes the completed workflow with its agent count", () => {
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState({ status: "completed" }) };
    renderPill();

    const pill = screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL);
    expect(pill).toHaveAttribute("data-workflow-status", "completed");
    expect(pill).toHaveTextContent("Workflow review-changes — 2 agents");
  });

  it("falls back to the workflow name from the tool input without state", () => {
    renderPill();

    const pill = screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL);
    expect(pill).toHaveAttribute("data-workflow-status", "unknown");
    expect(pill).toHaveTextContent("Workflow review-changes");
  });

  it("opens the workflow popover on click", () => {
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState() };
    renderPill();

    fireEvent.click(screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL));
    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_POPOVER)).toBeInTheDocument();
    expect(screen.getAllByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PHASE_TAB).length).toBeGreaterThan(0);
  });

  it("shows a starting description while running with no agents yet", () => {
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState({ entries: [] }) };
    renderPill();
    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL)).toHaveTextContent(
      "Workflow review-changes — starting…",
    );
  });

  it("describes failed and stopped workflows", () => {
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState({ status: "failed" }) };
    const { unmount } = renderPill();
    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL)).toHaveTextContent(
      "Workflow review-changes — failed",
    );
    unmount();

    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState({ status: "stopped" }) };
    renderPill();
    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL)).toHaveTextContent(
      "Workflow review-changes — stopped",
    );
  });

  it("toggles the popover with Enter and closes it with Escape", () => {
    // The trigger is a div[role=button], so keyboard activation is bespoke —
    // this pins the Enter/Escape paths a native button would give for free.
    mockWorkflowTaskStates = { [TOOL_USE_ID]: makeState() };
    renderPill();

    const pill = screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PILL);
    fireEvent.keyDown(pill, { key: "Enter" });
    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_POPOVER)).toBeInTheDocument();

    fireEvent.keyDown(pill, { key: "Escape" });
    expect(screen.queryByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_POPOVER)).not.toBeInTheDocument();
  });
});
