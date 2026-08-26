import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { queryClient, taskIdsQueryKey, taskQueryKey } from "../../queryClient.ts";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { useOptimisticTaskDelete } from "./useOptimisticTaskDelete";

// Mock the delete endpoint so we can force failures and inspect retry targets.
const { mockDeleteWorkspaceAgent } = vi.hoisted(() => ({
  mockDeleteWorkspaceAgent: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    deleteWorkspaceAgent: mockDeleteWorkspaceAgent,
  };
});

vi.mock("~/common/NavigateUtils.ts", () => ({
  useImbueNavigate: (): Record<string, unknown> => ({ navigateToRoot: vi.fn() }),
  useImbueLocation: (): Record<string, unknown> => ({ isAgentRoute: false }),
  useImbueParams: (): Record<string, unknown> => ({ taskID: undefined }),
}));

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const createMockTask = (id: string): CodingAgentTaskView =>
  ({
    id,
    taskStatus: "RUNNING",
    isDeleted: false,
  }) as CodingAgentTaskView;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

// The hook snapshots and tombstones tasks in the query cache; tests seed the
// cache the same way the WS bridge does.
const seedTask = (task: CodingAgentTaskView): void => {
  queryClient.setQueryData(taskQueryKey(task.id as string), task);
};

const getCachedTask = (id: string): CodingAgentTaskView | null | undefined =>
  queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(id));

// The hook uses both a Jotai store (workspace mapping, toasts) and a TanStack
// mutation (the delete request), so both providers are required.
const makeWrapper =
  (store: ReturnType<typeof createStore>) =>
  ({ children }: { children: ReactNode }): ReactElement =>
    createElement(Provider, { store }, createElement(QueryClientProvider, { client: queryClient }, children));

beforeEach(() => {
  vi.clearAllMocks();
  queryClient.removeQueries({ queryKey: ["sculptor"] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useOptimisticTaskDelete", () => {
  it("retries the task captured per-call, not the most recently failed task", async () => {
    // Regression for the shared-ref bug: the toast's Retry used to re-delete
    // whichever task failed most recently, so retrying the FIRST failure would
    // wrongly target the SECOND task.
    const store = createStore();
    queryClient.setQueryData(taskIdsQueryKey(), ["task-A", "task-B"]);
    seedTask(createMockTask("task-A"));
    seedTask(createMockTask("task-B"));

    const { result } = renderHook(() => useOptimisticTaskDelete({ workspaceId: "ws-1" }), {
      wrapper: makeWrapper(store),
    });

    // Both initial deletes reject -> two error toasts (each set on the same atom).
    mockDeleteWorkspaceAgent.mockRejectedValue(new Error("network"));

    result.current.execute("task-A", "Task A");
    await flushMicrotasks();
    const firstRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    result.current.execute("task-B", "Task B");
    await flushMicrotasks();
    const secondRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    expect(firstRetry).toBeDefined();
    expect(secondRetry).toBeDefined();
    expect(firstRetry).not.toBe(secondRetry);

    // Re-seed task-A so its optimistic re-delete proceeds to the API call.
    seedTask(createMockTask("task-A"));
    queryClient.setQueryData(taskIdsQueryKey(), ["task-A"]);

    mockDeleteWorkspaceAgent.mockClear();
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    // Invoke the FIRST failure's Retry. It must re-delete task-A, not task-B.
    firstRetry!();
    await flushMicrotasks();

    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledTimes(1);
    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ agent_id: "task-A" }) }),
    );
  });

  it("sends the DELETE even when the task is missing from the cache (SCU-1832)", async () => {
    // A stale reference (route, palette action) can outlive the cache entry.
    // The cache's ignorance must not silently swallow the user's delete —
    // the server is the authority on deletability.
    const store = createStore();
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    const { result } = renderHook(() => useOptimisticTaskDelete({ workspaceId: "ws-1" }), {
      wrapper: makeWrapper(store),
    });

    result.current.execute("task-ghost", "Ghost Task");
    await flushMicrotasks();

    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledOnce();
    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ agent_id: "task-ghost" }) }),
    );
    expect(store.get(deleteErrorToastAtom)).toBeNull();
  });

  it("skips the snapshot-dependent navigation callback when there was nothing to snapshot", async () => {
    // The custom callback's contract is a real pre-delete snapshot (it computes
    // sibling positions from it) — with no snapshot it must not run at all.
    const store = createStore();
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);
    const onNavigateAfterDelete = vi.fn();

    const { result } = renderHook(() => useOptimisticTaskDelete({ workspaceId: "ws-1", onNavigateAfterDelete }), {
      wrapper: makeWrapper(store),
    });

    result.current.execute("task-ghost", "Ghost Task");
    await flushMicrotasks();

    expect(onNavigateAfterDelete).not.toHaveBeenCalled();
    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledOnce();
  });

  it("tombstones the task before the navigation callback observes it", () => {
    // The removal must be visible in every store by the time callbacks run, so
    // a callback reading the cache sees the tombstone, not the live task.
    const store = createStore();
    queryClient.setQueryData(taskIdsQueryKey(), ["task-A"]);
    seedTask(createMockTask("task-A"));
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    let observedDuringCallback: CodingAgentTaskView | null | undefined = createMockTask("task-A");
    const onNavigateAfterDelete = vi.fn((taskId: string): void => {
      observedDuringCallback = getCachedTask(taskId);
    });

    const { result } = renderHook(() => useOptimisticTaskDelete({ workspaceId: "ws-1", onNavigateAfterDelete }), {
      wrapper: makeWrapper(store),
    });

    result.current.execute("task-A", "Task A");

    expect(onNavigateAfterDelete).toHaveBeenCalledOnce();
    expect(observedDuringCallback).toBeNull();
    expect(queryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey())).toEqual([]);
  });
});
