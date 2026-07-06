import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { queryClient as sharedQueryClient, taskIdsQueryKey, taskQueryKey } from "../../queryClient.ts";
import {
  useMarkReadMutation,
  useMarkUnreadMutation,
  useOptimisticTaskDeleteMutation,
  useRestoreTaskMutation,
  useTaskRenameMutation,
} from "./index";

// ── Mock API ────────────────────────────────────────────────
const { mockMarkRead, mockMarkUnread, mockRename, mockDelete, mockRestore } = vi.hoisted(() => ({
  mockMarkRead: vi.fn(),
  mockMarkUnread: vi.fn(),
  mockRename: vi.fn(),
  mockDelete: vi.fn(),
  mockRestore: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    markWorkspaceAgentRead: mockMarkRead,
    markWorkspaceAgentUnread: mockMarkUnread,
    renameWorkspaceAgent: mockRename,
    deleteWorkspaceAgent: mockDelete,
    restoreWorkspaceAgent: mockRestore,
  };
});

// ── Helpers ─────────────────────────────────────────────────

const WS_ID = "ws-1";
const AGENT_ID = "agent-1";

const makeTask = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: AGENT_ID,
    title: "Original Title",
    status: "READY",
    updatedAt: "2024-01-01T00:00:00.000Z",
    lastReadAt: "2024-01-01T00:00:00.000Z",
    ...overrides,
  }) as unknown as CodingAgentTaskView;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

/** Wrapper that provides QueryClientProvider (and optionally Jotai Provider). */
const makeWrapper = (store?: ReturnType<typeof createStore>) => {
  return ({ children }: { children: ReactNode }): ReactElement => {
    const tree = createElement(QueryClientProvider, { client: sharedQueryClient }, children);
    if (store) {
      return createElement(Provider, { store }, tree);
    }
    return tree;
  };
};

const seedTask = (task: CodingAgentTaskView): void => {
  sharedQueryClient.setQueryData(taskQueryKey(task.id as string), task);
};

const seedTaskIds = (ids: ReadonlyArray<string>): void => {
  sharedQueryClient.setQueryData(taskIdsQueryKey(), ids);
};

const getCachedTask = (id: string): CodingAgentTaskView | null | undefined =>
  sharedQueryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(id));

const getCachedTaskIds = (): ReadonlyArray<string> | undefined =>
  sharedQueryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey());

// ── Lifecycle ───────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockMarkRead.mockResolvedValue(undefined);
  mockMarkUnread.mockResolvedValue(undefined);
  mockRename.mockResolvedValue(undefined);
  mockDelete.mockResolvedValue(undefined);
  mockRestore.mockResolvedValue(undefined);
  sharedQueryClient.removeQueries({ queryKey: ["sculptor"] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ═══════════════════════════════════════════════════════════
// useMarkReadMutation
// ═══════════════════════════════════════════════════════════

describe("useMarkReadMutation", () => {
  it("calls markWorkspaceAgentRead with the correct path", async () => {
    const task = makeTask();
    seedTask(task);
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useMarkReadMutation(WS_ID, AGENT_ID), { wrapper });

    act(() => {
      result.current.mutate();
    });
    await flushMicrotasks();

    expect(mockMarkRead).toHaveBeenCalledOnce();
    expect(mockMarkRead).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
    });
  });

  it("optimistically sets lastReadAt on the cached task", async () => {
    const task = makeTask({ lastReadAt: "2020-01-01T00:00:00.000Z" });
    seedTask(task);
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useMarkReadMutation(WS_ID, AGENT_ID), { wrapper });

    act(() => {
      result.current.mutate();
    });
    // onMutate is sync-ish; the cache should already be updated.
    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).not.toBe("2020-01-01T00:00:00.000Z");
    expect(cached?.lastReadAt).toBeTruthy();
  });

  it("rolls back the cache when the API call rejects", async () => {
    const originalLastRead = "2020-01-01T00:00:00.000Z";
    const task = makeTask({ lastReadAt: originalLastRead });
    seedTask(task);
    mockMarkRead.mockRejectedValueOnce(new Error("network"));

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useMarkReadMutation(WS_ID, AGENT_ID), { wrapper });

    act(() => {
      result.current.mutate();
    });
    await flushMicrotasks();

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).toBe(originalLastRead);
  });
});

// ═══════════════════════════════════════════════════════════
// useMarkUnreadMutation
// ═══════════════════════════════════════════════════════════

describe("useMarkUnreadMutation", () => {
  it("calls markWorkspaceAgentUnread with the correct path", async () => {
    const task = makeTask();
    seedTask(task);
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useMarkUnreadMutation(WS_ID, AGENT_ID), { wrapper });

    act(() => {
      result.current.mutate();
    });
    await flushMicrotasks();

    expect(mockMarkUnread).toHaveBeenCalledOnce();
    expect(mockMarkUnread).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
    });
  });

  it("optimistically sets lastReadAt to null on the cached task", async () => {
    const task = makeTask({ lastReadAt: "2024-06-01T00:00:00.000Z" });
    seedTask(task);
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useMarkUnreadMutation(WS_ID, AGENT_ID), { wrapper });

    act(() => {
      result.current.mutate();
    });

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).toBeNull();
  });

  it("rolls back the cache when the API call rejects", async () => {
    const originalLastRead = "2024-06-01T12:00:00.000Z";
    const task = makeTask({ lastReadAt: originalLastRead });
    seedTask(task);
    mockMarkUnread.mockRejectedValueOnce(new Error("network"));

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useMarkUnreadMutation(WS_ID, AGENT_ID), { wrapper });

    act(() => {
      result.current.mutate();
    });
    await flushMicrotasks();

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).toBe(originalLastRead);
  });
});

// ═══════════════════════════════════════════════════════════
// useTaskRenameMutation
// ═══════════════════════════════════════════════════════════

describe("useTaskRenameMutation", () => {
  it("calls renameWorkspaceAgent with the correct path and body", async () => {
    const task = makeTask();
    seedTask(task);
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "New Name" });
    });
    await flushMicrotasks();

    expect(mockRename).toHaveBeenCalledOnce();
    expect(mockRename).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
      body: { title: "New Name" },
    });
  });

  it("optimistically updates the title in the cache", async () => {
    const task = makeTask({ title: "Old Title" });
    seedTask(task);
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Shiny New Title" });
    });

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("Shiny New Title");
  });

  it("rolls back the cache when the API call rejects", async () => {
    const task = makeTask({ title: "Keep Me" });
    seedTask(task);
    mockRename.mockRejectedValueOnce(new Error("network"));

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Bad Rename" });
    });
    await flushMicrotasks();

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("Keep Me");
  });
});

// ═══════════════════════════════════════════════════════════
// useOptimisticTaskDeleteMutation
// ═══════════════════════════════════════════════════════════

describe("useOptimisticTaskDeleteMutation", () => {
  it("calls deleteWorkspaceAgent with the correct path", async () => {
    const task = makeTask();
    seedTask(task);
    seedTaskIds([AGENT_ID, "agent-2"]);

    const store = createStore();
    const wrapper = makeWrapper(store);
    const { result } = renderHook(() => useOptimisticTaskDeleteMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ taskId: AGENT_ID, taskTitle: "Original Title" });
    });
    await flushMicrotasks();

    expect(mockDelete).toHaveBeenCalledOnce();
    expect(mockDelete).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
      meta: { skipWsAck: true },
    });
  });

  it("optimistically removes the task from cache and taskIds", async () => {
    const task = makeTask();
    seedTask(task);
    seedTaskIds([AGENT_ID, "agent-2"]);

    const store = createStore();
    const wrapper = makeWrapper(store);
    const { result } = renderHook(() => useOptimisticTaskDeleteMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ taskId: AGENT_ID, taskTitle: "Original Title" });
    });

    // Task should be null'd in cache.
    expect(getCachedTask(AGENT_ID)).toBeNull();
    // Task should be removed from the taskIds list.
    expect(getCachedTaskIds()).toEqual(["agent-2"]);
  });

  it("rolls back the cache and taskIds when the API call rejects", async () => {
    const task = makeTask({ title: "Restore Me" });
    seedTask(task);
    seedTaskIds([AGENT_ID, "agent-2"]);
    mockDelete.mockRejectedValueOnce(new Error("network"));

    const store = createStore();
    const wrapper = makeWrapper(store);
    const { result } = renderHook(() => useOptimisticTaskDeleteMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ taskId: AGENT_ID, taskTitle: "Restore Me" });
    });
    await flushMicrotasks();

    // Task should be restored.
    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("Restore Me");
    // Task id should be back in the list.
    expect(getCachedTaskIds()).toContain(AGENT_ID);
  });

  it("invokes onNavigateAfterDelete during onMutate", async () => {
    const task = makeTask();
    seedTask(task);
    seedTaskIds([AGENT_ID]);

    const onNavigate = vi.fn();
    const store = createStore();
    const wrapper = makeWrapper(store);
    const { result } = renderHook(() => useOptimisticTaskDeleteMutation(WS_ID, { onNavigateAfterDelete: onNavigate }), {
      wrapper,
    });

    act(() => {
      result.current.mutate({ taskId: AGENT_ID, taskTitle: "Original Title" });
    });

    expect(onNavigate).toHaveBeenCalledOnce();
    expect(onNavigate).toHaveBeenCalledWith(AGENT_ID, expect.objectContaining({ id: AGENT_ID }));
  });
});

// ═══════════════════════════════════════════════════════════
// useRestoreTaskMutation
// ═══════════════════════════════════════════════════════════

describe("useRestoreTaskMutation", () => {
  it("calls restoreWorkspaceAgent with the correct path", async () => {
    // A soft-deleted task is null in cache.
    sharedQueryClient.setQueryData(taskQueryKey(AGENT_ID), null);

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useRestoreTaskMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(mockRestore).toHaveBeenCalledOnce();
    expect(mockRestore).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
    });
  });

  it("optimistically sets the cached task to null", async () => {
    // Even if there's a stale task in cache, restore clears it optimistically
    // (the WS bridge will write the real restored task later).
    const staleTask = makeTask({ title: "Stale" });
    seedTask(staleTask);

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useRestoreTaskMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID });
    });

    expect(getCachedTask(AGENT_ID)).toBeNull();
  });

  it("rolls back the cache when the API call rejects", async () => {
    const prevTask = makeTask({ title: "Was Deleted" });
    seedTask(prevTask);
    mockRestore.mockRejectedValueOnce(new Error("network"));

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useRestoreTaskMutation(WS_ID), { wrapper });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID });
    });
    await flushMicrotasks();

    // Cache should be rolled back to the pre-mutation value.
    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("Was Deleted");
  });
});
