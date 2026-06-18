import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage, Task } from "~/api";
import { AgentTaskStatus, ArtifactType, ElementIds } from "~/api";
import {
  activeTurnIdAtomFamily,
  liveTaskTurnIdAtomFamily,
  tasksPhaseAtomFamily,
} from "~/common/state/atoms/statusPillTasks.ts";

import { StatusPill } from "./StatusPill.tsx";

const { mockUseAgentStatus, mockUseElapsedTime, mockUseTaskDetailWithDefaults } = vi.hoisted(() => ({
  mockUseAgentStatus: vi.fn(),
  mockUseElapsedTime: vi.fn(),
  mockUseTaskDetailWithDefaults: vi.fn(),
}));

vi.mock("./useAgentStatus.ts", () => ({
  useAgentStatus: mockUseAgentStatus,
}));

vi.mock("./useElapsedTime.ts", () => ({
  useElapsedTime: mockUseElapsedTime,
}));

vi.mock("~/common/state/hooks/useTaskDetail.ts", () => ({
  useTaskDetailWithDefaults: mockUseTaskDetailWithDefaults,
}));

vi.mock("~/common/NavigateUtils.ts", () => ({
  useWorkspacePageParams: (): { workspaceID: string; agentID: string } => ({
    workspaceID: "ws-1",
    agentID: "agent-1",
  }),
}));

vi.mock("~/electron/utils.ts", () => ({
  getMetaKey: (): string => "⌘",
  isModifierPressed: (): boolean => false,
  isMac: (): boolean => true,
}));

// Each test gets a fresh Jotai store so persisted per-task atoms (active
// turn id, live-task turn id, phase) don't leak between tests. localStorage
// is cleared in beforeEach for the same reason — atomWithStorage reads it.
let testStore = createStore();

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
  <Provider store={testStore}>
    <Theme>{children}</Theme>
  </Provider>
);

const defaultProps = {
  taskStatus: null as null,
  isAutoCompacting: false,
  isStreaming: false,
  inProgressChatMessage: null as ChatMessage | null,
  workingUserMessageId: null as string | null,
};

const emptyTaskDetail = {
  completedChatMessages: [],
  inProgressChatMessage: null,
  queuedChatMessages: [],
  workingUserMessageId: null,
  artifacts: {},
  pendingUserQuestion: null,
  submittedQuestionAnswers: {},
  isInPlanMode: false,
};

const taskDetailWithTasks = (tasks: Array<Task>): typeof emptyTaskDetail => ({
  ...emptyTaskDetail,
  artifacts: { [ArtifactType.PLAN]: { tasks, version: 2, objectType: "TaskListArtifact" } },
});

beforeEach(() => {
  mockUseElapsedTime.mockReturnValue({ elapsed: "3.2s" });
  mockUseTaskDetailWithDefaults.mockReturnValue(emptyTaskDetail);
  // jsdom doesn't implement scrollIntoView, which AgentTasksPanel calls in an
  // effect when the popover mounts. Stub it so popover-open tests don't error.
  Element.prototype.scrollIntoView = vi.fn();
  // Reset persisted atom state between tests so a previous test's
  // workingUserMessageId doesn't leak into the next one.
  localStorage.clear();
  activeTurnIdAtomFamily.remove("agent-1");
  liveTaskTurnIdAtomFamily.remove("agent-1");
  tasksPhaseAtomFamily.remove("agent-1");
  testStore = createStore();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("StatusPill", () => {
  describe("rendering", () => {
    it("renders nothing when idle", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "idle",
        label: "",
        isCancellable: false,
        isVisible: false,
      });

      const { container } = render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });
      expect(container.querySelector(`[data-testid="${ElementIds.STATUS_PILL}"]`)).toBeNull();
    });

    it("renders pill with label and elapsed time when visible", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "thinking",
        label: "Thinking...",
        isCancellable: true,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL)).toBeTruthy();
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Thinking...");
      expect(screen.getByTestId(ElementIds.STATUS_PILL_ELAPSED).textContent).toBe("3.2s");
    });

    it("renders streaming state", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "streaming",
        label: "Streaming...",
        isCancellable: true,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Streaming...");
    });

    it("renders compacting state", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "compacting",
        label: "Compacting...",
        isCancellable: false,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} isAutoCompacting={true} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Compacting...");
    });

    it("renders stopping state", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "stopping",
        label: "Stopping...",
        isCancellable: false,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Stopping...");
    });

    it("renders stopped state with check icon instead of animation", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "stopped",
        label: "Stopped",
        isCancellable: false,
        isVisible: true,
      });

      const { container } = render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Stopped");
      expect(container.querySelector(".lucide-check")).toBeTruthy();
    });

    it("renders animation (not check icon) for active states", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "thinking",
        label: "Thinking...",
        isCancellable: true,
        isVisible: true,
      });

      const { container } = render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      expect(container.querySelector(".lucide-check")).toBeNull();
    });
  });

  describe("stop button", () => {
    it("renders stop button when cancellable", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "thinking",
        label: "Thinking...",
        isCancellable: true,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      const stopButton = screen.getByTestId(ElementIds.STATUS_PILL_STOP);
      expect(stopButton).toBeTruthy();
      expect(stopButton).not.toBeDisabled();
    });

    it("does not render stop button when not cancellable", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "compacting",
        label: "Compacting...",
        isCancellable: false,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} isAutoCompacting={true} />, { wrapper: Wrapper });
      expect(screen.queryByTestId(ElementIds.STATUS_PILL_STOP)).toBeNull();
    });

    it("does not render stop button in stopped state", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "stopped",
        label: "Stopped",
        isCancellable: false,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.queryByTestId(ElementIds.STATUS_PILL_STOP)).toBeNull();
    });
  });

  describe("keyboard shortcuts", () => {
    it("does not register a Cmd+X keyboard event listener", () => {
      const addEventListenerSpy = vi.spyOn(window, "addEventListener");

      mockUseAgentStatus.mockReturnValue({
        state: "thinking",
        label: "Thinking...",
        isCancellable: true,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });

      const keydownCalls = addEventListenerSpy.mock.calls.filter(([event]) => (event as string) === "keydown");
      expect(keydownCalls).toHaveLength(0);

      addEventListenerSpy.mockRestore();
    });
  });

  describe("elapsed time", () => {
    it("passes isVisible and isTicking to useElapsedTime", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "thinking",
        label: "Thinking...",
        isCancellable: true,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });

      expect(mockUseElapsedTime).toHaveBeenCalledWith(true, true, "agent-1-init");
    });

    it("passes isTicking=false when in stopped state", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "stopped",
        label: "Stopped",
        isCancellable: false,
        isVisible: true,
      });

      render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });

      expect(mockUseElapsedTime).toHaveBeenCalledWith(true, false, "agent-1-init");
    });

    it("passes isVisible=false when idle", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "idle",
        label: "",
        isCancellable: false,
        isVisible: false,
      });

      render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });

      expect(mockUseElapsedTime).toHaveBeenCalledWith(false, false, "agent-1-init");
    });

    it("displays the elapsed time from the hook", () => {
      mockUseAgentStatus.mockReturnValue({
        state: "thinking",
        label: "Thinking...",
        isCancellable: true,
        isVisible: true,
      });
      mockUseElapsedTime.mockReturnValue({ elapsed: "12.5s" });

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_ELAPSED).textContent).toBe("12.5s");
    });
  });

  describe("tasks phase machine", () => {
    const thinkingStatus = {
      state: "thinking" as const,
      label: "Thinking...",
      isCancellable: true,
      isVisible: true,
    };

    const inProgressTask: Task = { id: "1", subject: "Doing the thing", status: AgentTaskStatus.IN_PROGRESS };
    const completedTask: Task = { id: "1", subject: "Doing the thing", status: AgentTaskStatus.COMPLETED };

    const idleStatus = {
      state: "idle" as const,
      label: "",
      isCancellable: false,
      isVisible: false,
    };

    it("does not enter `lingering` when the artifact is already all-complete on first render", () => {
      // Invariant: `lingering` can only be entered from `active`. A
      // pre-completed artifact must never light the pill up with the count
      // summary while the agent is still working.
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([completedTask]));

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Thinking...");
    });

    it("enters `lingering` from `active` when all tasks complete within the turn", () => {
      vi.useFakeTimers();
      try {
        mockUseAgentStatus.mockReturnValue(thinkingStatus);
        mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([inProgressTask]));

        const { rerender } = render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
        expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("1 / 1 \u00b7 Doing the thing");

        // Task completes → the count summary appears (phase: active → lingering).
        mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([completedTask]));
        rerender(<StatusPill {...defaultProps} isStreaming={true} />);
        expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("1 of 1 done");

        // After the linger window, phase should revert to idle and the
        // lifecycle label takes over again. Regression test: a previous
        // implementation scheduled the linger timer in the same effect that
        // wrote the phase, so the timer was canceled the moment phase
        // flipped to "lingering" and the pill got stuck on the count summary.
        vi.advanceTimersByTime(5000);
        rerender(<StatusPill {...defaultProps} isStreaming={true} />);
        expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Thinking...");
      } finally {
        vi.useRealTimers();
      }
    });

    it("resets phase to idle when a new non-null workingUserMessageId arrives, but not when it goes null", () => {
      vi.useFakeTimers();
      try {
        mockUseAgentStatus.mockReturnValue(thinkingStatus);
        mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([inProgressTask]));

        const { rerender } = render(<StatusPill {...defaultProps} isStreaming={true} workingUserMessageId="turn-1" />, {
          wrapper: Wrapper,
        });

        // Drive into the lingering phase.
        mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([completedTask]));
        rerender(<StatusPill {...defaultProps} isStreaming={true} workingUserMessageId="turn-1" />);
        expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("1 of 1 done");

        // workingUserMessageId → null must NOT cut the linger short.
        rerender(<StatusPill {...defaultProps} isStreaming={true} workingUserMessageId={null} />);
        expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("1 of 1 done");

        // A brand-new non-null id resets phase to idle, even though the
        // artifact is still all-complete (so the new turn doesn't open
        // showing a stale celebration).
        rerender(<StatusPill {...defaultProps} isStreaming={true} workingUserMessageId="turn-2" />);
        expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Thinking...");
      } finally {
        vi.useRealTimers();
      }
    });

    it("keeps the pill visible after the turn ends, showing a count summary", () => {
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      mockUseTaskDetailWithDefaults.mockReturnValue(
        taskDetailWithTasks([
          { id: "1", subject: "a", status: AgentTaskStatus.COMPLETED },
          { id: "2", subject: "b", status: AgentTaskStatus.COMPLETED },
          { id: "3", subject: "c", status: AgentTaskStatus.PENDING },
        ]),
      );

      const { rerender } = render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      // Agent goes idle but tasks remain → pill stays visible with summary.
      mockUseAgentStatus.mockReturnValue(idleStatus);
      rerender(<StatusPill {...defaultProps} isStreaming={false} />);

      expect(screen.getByTestId(ElementIds.STATUS_PILL)).toBeTruthy();
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("2 of 3 done");
    });

    it("treats an all-complete carryover artifact as stale once a new turn starts without new tasks", () => {
      // Turn 1: agent starts with an in-progress task → completes it.
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([inProgressTask]));

      const { container, rerender } = render(
        <StatusPill {...defaultProps} isStreaming={true} workingUserMessageId="turn-1" />,
        { wrapper: Wrapper },
      );

      mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([completedTask]));
      rerender(<StatusPill {...defaultProps} isStreaming={true} workingUserMessageId="turn-1" />);
      // Sanity: count summary visible while artifact still belongs to turn 1.
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("1 of 1 done");

      // Turn 1 finishes — pill stays up with the count summary.
      mockUseAgentStatus.mockReturnValue(idleStatus);
      rerender(<StatusPill {...defaultProps} isStreaming={false} workingUserMessageId={null} />);
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("1 of 1 done");

      // Turn 2 starts. Artifact is unchanged (still all-complete from turn 1).
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      rerender(<StatusPill {...defaultProps} isStreaming={true} workingUserMessageId="turn-2" />);
      // We're in an active state, so the lifecycle label shows through —
      // the stale carryover must NOT bleed into the active turn.
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Thinking...");

      // Turn 2 ends without new TodoWrite → carryover is now confirmed stale,
      // pill hides entirely rather than showing the misleading old count.
      mockUseAgentStatus.mockReturnValue(idleStatus);
      rerender(<StatusPill {...defaultProps} isStreaming={false} workingUserMessageId={null} />);
      expect(container.querySelector(`[data-testid="${ElementIds.STATUS_PILL}"]`)).toBeNull();
    });

    it("hides the pill when the agent is idle and there are no tasks", () => {
      mockUseAgentStatus.mockReturnValue(idleStatus);
      mockUseTaskDetailWithDefaults.mockReturnValue(emptyTaskDetail);

      const { container } = render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });
      expect(container.querySelector(`[data-testid="${ElementIds.STATUS_PILL}"]`)).toBeNull();
    });

    it("pins on pill click and closes on outside click", async () => {
      const user = userEvent.setup();
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([inProgressTask]));

      render(
        <Wrapper>
          <div data-testid="outside">outside</div>
          <StatusPill {...defaultProps} isStreaming={true} />
        </Wrapper>,
      );

      // First click pins → popover open.
      await user.click(screen.getByTestId(ElementIds.STATUS_PILL));
      expect(screen.getAllByTestId(ElementIds.AGENT_TASKS_ROW).length).toBeGreaterThan(0);

      // Click outside closes the pinned popover.
      fireEvent.pointerDown(screen.getByTestId("outside"));
      expect(screen.queryAllByTestId(ElementIds.AGENT_TASKS_ROW).length).toBe(0);
    });

    it("opens an empty-state popover even when no todos have arrived yet", async () => {
      // Discoverability: during any active state, hovering/clicking the pill
      // should open the tasks popover with the EmptyState, even before the
      // agent has emitted a TodoWrite artifact.
      const user = userEvent.setup();
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      // No artifacts → tasks is null.
      mockUseTaskDetailWithDefaults.mockReturnValue(emptyTaskDetail);

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });

      await user.click(screen.getByTestId(ElementIds.STATUS_PILL));
      expect(screen.getByText("No agent tasks yet")).toBeTruthy();
      expect(screen.queryAllByTestId(ElementIds.AGENT_TASKS_ROW).length).toBe(0);
    });

    it('shows "Working on N tasks..." when multiple tasks are in_progress', () => {
      // Rare TodoWrite payload — fallback label from the legacy SpotlightCard.
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      mockUseTaskDetailWithDefaults.mockReturnValue(
        taskDetailWithTasks([
          { id: "1", subject: "First", status: AgentTaskStatus.IN_PROGRESS },
          { id: "2", subject: "Second", status: AgentTaskStatus.IN_PROGRESS },
          { id: "3", subject: "Third", status: AgentTaskStatus.PENDING },
        ]),
      );

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Working on 2 tasks...");
    });

    it("truncates long in-progress task names with an ellipsis", () => {
      // PILL_TASK_NAME_MAX_LENGTH = 36; the popover renders the full text but
      // the pill caps the label so it can't blow out the chat column.
      const longContent = "A".repeat(80);
      mockUseAgentStatus.mockReturnValue(thinkingStatus);
      mockUseTaskDetailWithDefaults.mockReturnValue(
        taskDetailWithTasks([{ id: "1", subject: longContent, status: AgentTaskStatus.IN_PROGRESS }]),
      );

      render(<StatusPill {...defaultProps} isStreaming={true} />, { wrapper: Wrapper });
      const label = screen.getByTestId(ElementIds.STATUS_PILL_LABEL);
      expect(label.textContent?.endsWith("\u2026")).toBe(true);
      expect(label.textContent?.length).toBeLessThan(longContent.length);
    });

    it("hides the elapsed timer while showing the count summary", () => {
      // The elapsed timer is meaningless once the pill is in count-summary
      // mode (it would read "time since the turn started," not "time spent
      // on tasks"), so it's suppressed in both lingering and post-turn.
      mockUseAgentStatus.mockReturnValue({
        state: "idle" as const,
        label: "",
        isCancellable: false,
        isVisible: false,
      });
      mockUseTaskDetailWithDefaults.mockReturnValue(
        taskDetailWithTasks([
          { id: "1", subject: "a", status: AgentTaskStatus.COMPLETED },
          { id: "2", subject: "b", status: AgentTaskStatus.PENDING },
        ]),
      );

      render(<StatusPill {...defaultProps} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("1 of 2 done");
      expect(screen.queryByTestId(ElementIds.STATUS_PILL_ELAPSED)).toBeNull();
    });

    it("restores the count summary on remount from persisted turn ids (post-restart)", () => {
      // Simulate an app restart: pre-seed the persisted atoms with the state
      // a previous session ended in, then mount fresh with the same artifact
      // already loaded by the backend. The pill should reappear with the
      // count summary, just as it did before the restart — proving the
      // freshness check survives across remount.
      testStore.set(activeTurnIdAtomFamily("agent-1"), "turn-1");
      testStore.set(liveTaskTurnIdAtomFamily("agent-1"), "turn-1");

      mockUseAgentStatus.mockReturnValue({
        state: "idle" as const,
        label: "",
        isCancellable: false,
        isVisible: false,
      });
      mockUseTaskDetailWithDefaults.mockReturnValue(
        taskDetailWithTasks([
          { id: "1", subject: "Step 1", status: AgentTaskStatus.COMPLETED },
          { id: "2", subject: "Step 2", status: AgentTaskStatus.COMPLETED },
        ]),
      );

      render(<StatusPill {...defaultProps} workingUserMessageId={null} />, { wrapper: Wrapper });
      // hasFreshTodos branch wins (activeTurnId is non-null but matches
      // liveTaskTurnId, so the carryover is NOT stale).
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("2 of 2 done");
    });

    it("treats persisted carryover as stale once a fresh turn arrives post-remount", () => {
      // Same setup as the previous test, but now the user starts a brand-new
      // turn (a workingUserMessageId that doesn't match the persisted
      // liveTaskTurnId). Without persistence this scenario would mis-attribute
      // the carryover to the new turn; with persistence the staleness check
      // correctly hides the count summary.
      testStore.set(activeTurnIdAtomFamily("agent-1"), "turn-1");
      testStore.set(liveTaskTurnIdAtomFamily("agent-1"), "turn-1");

      mockUseAgentStatus.mockReturnValue({
        state: "thinking" as const,
        label: "Thinking...",
        isCancellable: true,
        isVisible: true,
      });
      mockUseTaskDetailWithDefaults.mockReturnValue(
        taskDetailWithTasks([
          { id: "1", subject: "Step 1", status: AgentTaskStatus.COMPLETED },
          { id: "2", subject: "Step 2", status: AgentTaskStatus.COMPLETED },
        ]),
      );

      render(<StatusPill {...defaultProps} isStreaming={true} workingUserMessageId="turn-2" />, { wrapper: Wrapper });
      // Phase reset on new turn + isStaleCarryover=true → lifecycle label wins.
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Thinking...");
    });

    it("keeps the lifecycle label during `compacting` even with an in-progress todo", () => {
      // Lifecycle states (compacting / stopping / stopped) are NOT in
      // TASKS_OVERRIDE_STATES — they keep their own labels because they
      // reflect agent-lifecycle events, not work on the todo list.
      mockUseAgentStatus.mockReturnValue({
        state: "compacting" as const,
        label: "Compacting...",
        isCancellable: false,
        isVisible: true,
      });
      mockUseTaskDetailWithDefaults.mockReturnValue(taskDetailWithTasks([inProgressTask]));

      render(<StatusPill {...defaultProps} isAutoCompacting={true} />, { wrapper: Wrapper });
      expect(screen.getByTestId(ElementIds.STATUS_PILL_LABEL).textContent).toBe("Compacting...");
    });
  });
});
