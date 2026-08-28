import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { ToolResultBlock, WorkflowAgentProgress, WorkflowTaskState } from "~/api";
import { ElementIds } from "~/api";

import { AlphaWorkflowPopover } from "../AlphaWorkflowPopover.tsx";

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
  toolCalls: 4,
  durationMs: 61200,
  lastToolSummary: "Grep: TODO in src/",
  recentToolSummaries: ["Read(src/a.ts)", "Grep: TODO in src/"],
  ...overrides,
});

const makeState = (overrides: Partial<WorkflowTaskState> = {}): WorkflowTaskState => ({
  objectType: "WorkflowTaskState",
  taskId: "task-wf-1",
  toolUseId: "toolu-wf-1",
  workflowName: "review-changes",
  status: "running",
  entries: [
    { objectType: "WorkflowPhaseProgress", index: 0, title: "Review", kind: "" },
    { objectType: "WorkflowPhaseProgress", index: 1, title: "Verify", kind: "" },
    makeAgent(),
    makeAgent({
      index: 1,
      label: "verify:bug-1",
      phaseIndex: 1,
      phaseTitle: "Verify",
      state: "start",
      startedAt: null,
    }),
  ],
  usage: { objectType: "WorkflowUsage", totalTokens: 52310, toolUses: 17, durationMs: 63210 },
  lastToolName: "Grep",
  summary: "",
  ...overrides,
});

const makeResult = (): ToolResultBlock => ({
  toolUseId: "toolu-wf-1",
  toolName: "Workflow",
  invocationString: "review-changes",
  content: {
    contentType: "generic",
    text: "Workflow launched in background. Task ID: w18genw0r",
  },
  isError: false,
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const renderPopover = (state?: WorkflowTaskState): ReturnType<typeof render> =>
  render(<AlphaWorkflowPopover state={state} displayName="review-changes" result={makeResult()} />, {
    wrapper: Wrapper,
  });

afterEach(() => {
  cleanup();
});

describe("AlphaWorkflowPopover", () => {
  it("falls back to the launch acknowledgement when no workflow state exists", () => {
    renderPopover(undefined);
    expect(screen.getByText("review-changes")).toBeInTheDocument();
    expect(screen.getByText(/Workflow launched in background/)).toBeInTheDocument();
  });

  it("renders header, phases sidebar with counts, and the active phase's agents", () => {
    renderPopover(makeState());

    expect(screen.getByText("Running…")).toBeInTheDocument();
    expect(screen.getByText("52.3k tokens · 17 tools · 1m 03s")).toBeInTheDocument();

    const phaseTabs = screen.getAllByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PHASE_TAB);
    expect(phaseTabs).toHaveLength(2);
    expect(phaseTabs[0]).toHaveTextContent("Review");
    expect(phaseTabs[0]).toHaveTextContent("0/1");
    expect(phaseTabs[1]).toHaveTextContent("Verify");

    // Auto-selection follows the run: Review has the unfinished agent and is
    // first, so its agents render in the main pane.
    expect(phaseTabs[0]).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Review · 1 agent")).toBeInTheDocument();
    expect(screen.getByText("review:bugs")).toBeInTheDocument();
  });

  it("switches the agent pane when another phase is selected", () => {
    renderPopover(makeState());

    const phaseTabs = screen.getAllByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PHASE_TAB);
    fireEvent.click(phaseTabs[1]!);

    expect(screen.getByText("Verify · 1 agent")).toBeInTheDocument();
    expect(screen.getByText("verify:bug-1")).toBeInTheDocument();
    expect(screen.getByLabelText("queued")).toBeInTheDocument();
  });

  it("expands an agent row to show prompt, activity, and outcome", () => {
    renderPopover(makeState());

    const agentRow = screen.getAllByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_AGENT_ROW)[0]!;
    fireEvent.click(agentRow);

    expect(screen.getByText("Prompt")).toBeInTheDocument();
    expect(screen.getByText("Review the diff for bugs")).toBeInTheDocument();
    expect(screen.getByText("Activity — last 2 of 4 tool calls")).toBeInTheDocument();
    expect(screen.getByText("Read(src/a.ts)")).toBeInTheDocument();
    expect(screen.getByText("Grep: TODO in src/")).toBeInTheDocument();
    expect(screen.getByText("Outcome")).toBeInTheDocument();
    expect(screen.getByText("Still running…")).toBeInTheDocument();

    // Collapsible: a second click hides the details again.
    fireEvent.click(agentRow);
    expect(screen.queryByText("Prompt")).not.toBeInTheDocument();
  });

  it("shows result previews and errors as outcomes for finished agents", () => {
    renderPopover(
      makeState({
        status: "failed",
        entries: [
          { objectType: "WorkflowPhaseProgress", index: 0, title: "Review", kind: "" },
          makeAgent({ state: "done", resultPreview: "Found 2 bugs" }),
          makeAgent({ index: 1, label: "review:perf", state: "error", error: "agent exploded" }),
        ],
      }),
    );

    expect(screen.getByText("Failed")).toBeInTheDocument();

    const agentRows = screen.getAllByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_AGENT_ROW);
    fireEvent.click(agentRows[0]!);
    expect(screen.getByText("Found 2 bugs")).toBeInTheDocument();

    fireEvent.click(agentRows[1]!);
    expect(screen.getByText("agent exploded")).toBeInTheDocument();
  });

  it("groups agents with unknown phase indexes under an Agents sidebar item", () => {
    renderPopover(
      makeState({
        entries: [makeAgent({ phaseIndex: 7, phaseTitle: "" })],
      }),
    );

    const phaseTabs = screen.getAllByTestId(ElementIds.ALPHA_CHAT_WORKFLOW_PHASE_TAB);
    expect(phaseTabs).toHaveLength(1);
    expect(phaseTabs[0]).toHaveTextContent("Agents");
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
    renderPopover(
      makeState({
        entries: [{ objectType: "WorkflowPhaseProgress", index: 0, title: "Sweep", kind: "" }, ...manyAgents],
      }),
    );

    expect(screen.getByText("agent-49")).toBeInTheDocument();
    expect(screen.queryByText("agent-50")).not.toBeInTheDocument();
    expect(screen.getByText("+10 more (5 done)")).toBeInTheDocument();
  });

  it("shows a starting message while running with an empty tree", () => {
    renderPopover(makeState({ entries: [] }));
    expect(screen.getByText("Starting workflow…")).toBeInTheDocument();
  });

  it("shows an empty-run message for a finished workflow with no agents", () => {
    renderPopover(makeState({ status: "failed", entries: [] }));
    expect(screen.getByText("No agents ran.")).toBeInTheDocument();
  });
});
