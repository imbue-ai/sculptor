import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, type RenderHookResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement, useRef } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView, ModelOption } from "../../../api";
import { queryClient, syncTasksToQueryCache } from "../../queryClient.ts";
import { useTaskAvailableModels, useTaskStatus } from "./useTaskHelpers.ts";

const createMockTask = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: "task-1",
    status: "RUNNING",
    goal: "Test goal",
    model: "CLAUDE_4_SONNET",
    availableModels: [],
    isDeleted: false,
    harnessCapabilities: {},
    ...overrides,
  }) as unknown as CodingAgentTaskView;

const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
  createElement(QueryClientProvider, { client: queryClient }, children);

// TanStack delivers observer notifications on a macrotask (its notifyManager
// batches via setTimeout(0)), so a cache write reaches the hook only on the next
// tick — flush one inside `act` before asserting.
const flushNotifications = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const writeTasksAndFlush = async (tasks: Record<string, CodingAgentTaskView>): Promise<void> => {
  await act(async () => {
    syncTasksToQueryCache(tasks);
    await flushNotifications();
  });
};

// Render the hook while counting how many times its host re-renders — the
// fine-grained-subscription assertion is "this count stays put when an unrelated
// field changes and ticks up when the selected field changes".
const renderCountingStatus = (taskId: string): RenderHookResult<{ status: unknown; renders: number }, unknown> =>
  renderHook(
    () => {
      const renders = useRef(0);
      renders.current += 1;
      return { status: useTaskStatus(taskId), renders: renders.current };
    },
    { wrapper },
  );

beforeEach(() => {
  queryClient.removeQueries({ queryKey: ["sculptor"] });
});

describe("useTaskStatus", () => {
  it("returns undefined for an unknown task id", () => {
    const { result } = renderHook(() => useTaskStatus("unknown-task"), { wrapper });

    expect(result.current).toBeUndefined();
  });

  it("does not re-render when an unrelated task field changes", async () => {
    const task = createMockTask({ id: "task-1", status: "RUNNING", goal: "before" });
    await writeTasksAndFlush({ "task-1": task });

    const { result } = renderCountingStatus("task-1");
    const rendersAfterSeed = result.current.renders;
    expect(result.current.status).toBe("RUNNING");

    // Same status, different goal: the select result is unchanged, so structural
    // sharing must suppress the re-render.
    await writeTasksAndFlush({ "task-1": { ...task, goal: "after" } as CodingAgentTaskView });

    expect(result.current.renders).toBe(rendersAfterSeed);
    expect(result.current.status).toBe("RUNNING");
  });

  it("re-renders when the status changes", async () => {
    const task = createMockTask({ id: "task-1", status: "RUNNING" });
    await writeTasksAndFlush({ "task-1": task });

    const { result } = renderCountingStatus("task-1");
    const rendersAfterSeed = result.current.renders;

    await writeTasksAndFlush({ "task-1": { ...task, status: "WAITING" } as CodingAgentTaskView });

    expect(result.current.renders).toBeGreaterThan(rendersAfterSeed);
    expect(result.current.status).toBe("WAITING");
  });
});

describe("useTaskAvailableModels", () => {
  it("returns a referentially stable empty list across unrelated updates", async () => {
    // No backend catalog (Claude): availableModels is absent, so the select must
    // fall back to the shared EMPTY constant — one stable array identity rather
    // than a fresh `[]` each frame.
    const task = createMockTask({ id: "task-1", availableModels: undefined, status: "RUNNING" });
    await writeTasksAndFlush({ "task-1": task });

    const seen: Array<ReadonlyArray<ModelOption>> = [];
    renderHook(
      () => {
        seen.push(useTaskAvailableModels("task-1"));
        return null;
      },
      { wrapper },
    );

    await writeTasksAndFlush({ "task-1": { ...task, status: "WAITING" } as CodingAgentTaskView });

    // Every observed value is the same reference (both the absent-data coalesce
    // and the select fallback return the shared EMPTY constant).
    const first = seen[0];
    expect(first).toEqual([]);
    seen.forEach((value) => expect(value).toBe(first));
  });
});
