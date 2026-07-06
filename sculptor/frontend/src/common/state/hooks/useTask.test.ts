import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "../../../api";
import {
  queryClient as sharedQueryClient,
  syncTasksToQueryCache,
  taskIdsQueryKey,
  taskQueryKey,
} from "../../queryClient.ts";
import { useTask, useTaskIds } from "./useTask";

// useTask/useTaskIds tests get their own QueryClient to avoid polluting the
// singleton with test state. syncTasksToQueryCache tests use the real singleton.
let testQueryClient: QueryClient;

const createWrapper =
  (qc: QueryClient) =>
  ({ children }: { children: ReactNode }): ReactElement =>
    createElement(QueryClientProvider, { client: qc }, children);

const createMockTask = (id: string, overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id,
    title: `Task ${id}`,
    isDeleted: false,
    status: "IDLE",
    workspaceId: "ws-1",
    lastReadAt: null,
    updatedAt: "2026-07-01T00:00:00Z",
    ...overrides,
  }) as CodingAgentTaskView;

beforeEach(() => {
  testQueryClient = new QueryClient({
    defaultOptions: {
      queries: { staleTime: Infinity, retry: false },
    },
  });
  // Clear the singleton before every test so syncTasksToQueryCache state
  // doesn't leak between tests.
  sharedQueryClient.removeQueries({ queryKey: ["sculptor"] });
});

afterEach(() => {
  testQueryClient.clear();
});

describe("useTask", () => {
  it("returns null when the cache has no value for the task id", () => {
    const { result } = renderHook(() => useTask("task-1"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toBeNull();
  });

  it("returns the task value written via the WS bridge", () => {
    const task = createMockTask("task-1");
    testQueryClient.setQueryData<CodingAgentTaskView | null>(taskQueryKey("task-1"), task);

    const { result } = renderHook(() => useTask("task-1"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toEqual(task);
  });

  it("returns null when the cache value is null (soft-deleted task)", () => {
    testQueryClient.setQueryData<CodingAgentTaskView | null>(taskQueryKey("deleted"), null);

    const { result } = renderHook(() => useTask("deleted"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toBeNull();
  });

  it("re-renders when the cache entry for the task changes", async () => {
    const taskV1 = createMockTask("task-1");
    testQueryClient.setQueryData<CodingAgentTaskView | null>(taskQueryKey("task-1"), taskV1);

    const { result } = renderHook(() => useTask("task-1"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current?.updatedAt).toBe("2026-07-01T00:00:00Z");

    const taskV2 = createMockTask("task-1", { updatedAt: "2026-07-02T00:00:00Z" });
    testQueryClient.setQueryData<CodingAgentTaskView | null>(taskQueryKey("task-1"), taskV2);

    await waitFor(() => {
      expect(result.current?.updatedAt).toBe("2026-07-02T00:00:00Z");
    });
  });
});

describe("useTaskIds", () => {
  it("returns undefined when no WS frame has seeded the cache", () => {
    const { result } = renderHook(() => useTaskIds(), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toBeUndefined();
  });

  it("returns ids seeded via the WS bridge", () => {
    testQueryClient.setQueryData<ReadonlyArray<string>>(taskIdsQueryKey(), ["a", "b"]);

    const { result } = renderHook(() => useTaskIds(), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toEqual(["a", "b"]);
  });
});

describe("syncTasksToQueryCache", () => {
  it("writes non-deleted tasks to the query cache", () => {
    const tasks: Record<string, CodingAgentTaskView> = {
      "task-1": createMockTask("task-1"),
      "task-2": createMockTask("task-2"),
    };
    syncTasksToQueryCache(tasks);
    expect(sharedQueryClient.getQueryData(taskQueryKey("task-1"))).toEqual(createMockTask("task-1"));
    expect(sharedQueryClient.getQueryData(taskQueryKey("task-2"))).toEqual(createMockTask("task-2"));
  });

  it("sets soft-deleted tasks to null in the cache", () => {
    const task = createMockTask("deleted-task");
    syncTasksToQueryCache({ "deleted-task": task });
    expect(sharedQueryClient.getQueryData(taskQueryKey("deleted-task"))).not.toBeNull();

    syncTasksToQueryCache({ "deleted-task": { ...task, isDeleted: true } });
    expect(sharedQueryClient.getQueryData(taskQueryKey("deleted-task"))).toBeNull();
  });

  it("populates taskIds with non-deleted ids and removes deleted ones", () => {
    syncTasksToQueryCache({
      "t-1": createMockTask("t-1"),
      "t-2": createMockTask("t-2"),
    });
    expect(sharedQueryClient.getQueryData(taskIdsQueryKey())).toEqual(expect.arrayContaining(["t-1", "t-2"]));

    // Second frame: t-2 is now soft-deleted, t-3 is new.
    syncTasksToQueryCache({
      "t-2": { ...createMockTask("t-2"), isDeleted: true },
      "t-3": createMockTask("t-3"),
    });
    const finalIds = sharedQueryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey());
    expect(finalIds).toContain("t-1");
    expect(finalIds).toContain("t-3");
    expect(finalIds).not.toContain("t-2");
  });

  it("preserves order of ids from prior frames, appending new ones at the end", () => {
    syncTasksToQueryCache({
      a: createMockTask("a"),
      b: createMockTask("b"),
    });
    syncTasksToQueryCache({
      c: createMockTask("c"),
    });
    const ids = sharedQueryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey());
    expect(ids).toEqual(["a", "b", "c"]);
  });

  it("does not update taskIds when no ids actually changed", () => {
    syncTasksToQueryCache({
      a: createMockTask("a"),
    });
    const before = sharedQueryClient.getQueryData(taskIdsQueryKey());

    // Re-send the same task with a different title but same id.
    syncTasksToQueryCache({
      a: createMockTask("a", { title: "new title" }),
    });
    const after = sharedQueryClient.getQueryData(taskIdsQueryKey());

    // Same reference — taskIds unchanged.
    expect(before).toBe(after);
  });
});
