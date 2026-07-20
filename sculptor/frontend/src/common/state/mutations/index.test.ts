import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { TaskStatus } from "../../../api";
import { HTTPException } from "../../Errors.ts";
import {
  queryClient as sharedQueryClient,
  syncTasksToQueryCache,
  taskIdsQueryKey,
  taskQueryKey,
} from "../../queryClient.ts";
import { isUnreadOverrideActive, resetUnreadOverridesForTesting } from "../atoms/unreadOverrides";
import {
  applyOptimisticTaskDelete,
  MUTATION_SETTLE_TIMEOUT_MS,
  rollbackOptimisticTaskDelete,
  useDeleteTaskMutation,
  useMarkReadMutation,
  useMarkUnreadMutation,
  useRestoreTaskMutation,
  useTaskRenameMutation,
} from "./index";

// ── Mock API ────────────────────────────────────────────────
const { mockMarkRead, mockMarkUnread, mockRename, mockRestore, mockDelete } = vi.hoisted(() => ({
  mockMarkRead: vi.fn(),
  mockMarkUnread: vi.fn(),
  mockRename: vi.fn(),
  mockRestore: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    markWorkspaceAgentRead: mockMarkRead,
    markWorkspaceAgentUnread: mockMarkUnread,
    renameWorkspaceAgent: mockRename,
    restoreWorkspaceAgent: mockRestore,
    deleteWorkspaceAgent: mockDelete,
  };
});

// ── Helpers ─────────────────────────────────────────────────

const WS_ID = "ws-1";
const AGENT_ID = "agent-1";
const UPDATED_AT = "2024-01-01T00:00:00.000Z";
const LATER_UPDATED_AT = "2024-01-01T00:05:00.000Z";

const makeTask = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: AGENT_ID,
    title: "Original Title",
    status: TaskStatus.READY,
    isDeleted: false,
    updatedAt: UPDATED_AT,
    lastReadAt: "2024-01-01T00:00:00.000Z",
    ...overrides,
  }) as unknown as CodingAgentTaskView;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const makeWrapper = () => {
  return ({ children }: { children: ReactNode }): ReactElement =>
    createElement(QueryClientProvider, { client: sharedQueryClient }, children);
};

const seedTask = (task: CodingAgentTaskView): void => {
  sharedQueryClient.setQueryData(taskQueryKey(task.id as string), task);
};

const getCachedTask = (id: string): CodingAgentTaskView | null | undefined =>
  sharedQueryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(id));

// ── Lifecycle ───────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockMarkRead.mockResolvedValue(undefined);
  mockMarkUnread.mockResolvedValue(undefined);
  mockRename.mockResolvedValue(undefined);
  mockRestore.mockResolvedValue(undefined);
  mockDelete.mockResolvedValue(undefined);
  sharedQueryClient.removeQueries({ queryKey: ["sculptor"] });
  // Unread overrides live in a module-level map, so they leak across tests
  // without an explicit reset.
  resetUnreadOverridesForTesting();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ═══════════════════════════════════════════════════════════
// useMarkReadMutation
// ═══════════════════════════════════════════════════════════

describe("useMarkReadMutation", () => {
  it("calls markWorkspaceAgentRead with the correct path", async () => {
    seedTask(makeTask());
    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(mockMarkRead).toHaveBeenCalledOnce();
    expect(mockMarkRead).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
    });
  });

  it("optimistically sets lastReadAt on the cached task", async () => {
    seedTask(makeTask({ lastReadAt: "2020-01-01T00:00:00.000Z" }));
    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).not.toBe("2020-01-01T00:00:00.000Z");
    expect(cached?.lastReadAt).toBeTruthy();
  });

  it("rolls back the cache when the API call rejects", async () => {
    const originalLastRead = "2020-01-01T00:00:00.000Z";
    seedTask(makeTask({ lastReadAt: originalLastRead }));
    mockMarkRead.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).toBe(originalLastRead);
  });

  it("skips the rollback when a WS frame wrote the task while the request was in flight", async () => {
    seedTask(makeTask({ lastReadAt: "2020-01-01T00:00:00.000Z" }));
    const serverTask = makeTask({ lastReadAt: null, updatedAt: LATER_UPDATED_AT });
    mockMarkRead.mockImplementationOnce(() => {
      // The frame is authoritative: it must survive the failed request's
      // rollback (the delta stream will not re-send an unchanged task).
      syncTasksToQueryCache({ [AGENT_ID]: serverTask });
      return Promise.reject(new Error("network"));
    });

    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedTask(AGENT_ID)).toEqual(serverTask);
  });
});

// ═══════════════════════════════════════════════════════════
// useMarkUnreadMutation
// ═══════════════════════════════════════════════════════════

describe("useMarkUnreadMutation", () => {
  it("calls markWorkspaceAgentUnread with the correct path", async () => {
    seedTask(makeTask());
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(mockMarkUnread).toHaveBeenCalledOnce();
    expect(mockMarkUnread).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
    });
  });

  it("records the override and clears lastReadAt optimistically", async () => {
    seedTask(makeTask({ lastReadAt: "2024-06-01T00:00:00.000Z" }));
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    expect(getCachedTask(AGENT_ID)?.lastReadAt).toBeNull();
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: UPDATED_AT })).toBe(true);
  });

  it("keys an idle-agent override to the task's updatedAt at mark time", async () => {
    seedTask(makeTask());
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    // A later turn expires the override without an explicit clear.
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: LATER_UPDATED_AT })).toBe(false);
  });

  it("holds a running agent's override through the rest of its run", async () => {
    seedTask(makeTask({ status: TaskStatus.RUNNING }));
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.RUNNING, updatedAt: LATER_UPDATED_AT })).toBe(true);
  });

  it("preserves the other task fields on the optimistic update", async () => {
    seedTask(makeTask({ title: "My agent" }));
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("My agent");
    expect(cached?.updatedAt).toBe(UPDATED_AT);
  });

  it("does nothing for a task the stream has not delivered", async () => {
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: "missing-task" });
    });
    await flushMicrotasks();

    expect(isUnreadOverrideActive("missing-task", { status: TaskStatus.READY, updatedAt: UPDATED_AT })).toBe(false);
    expect(mockMarkUnread).not.toHaveBeenCalled();
  });

  it("rolls back the cache AND clears the override when the API call rejects", async () => {
    const originalLastRead = "2024-06-01T12:00:00.000Z";
    seedTask(makeTask({ lastReadAt: originalLastRead }));
    mockMarkUnread.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedTask(AGENT_ID)?.lastReadAt).toBe(originalLastRead);
    // The persist failed, so the dot must not stay pinned to "unread".
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: UPDATED_AT })).toBe(false);
  });

  it("keeps the frame and the override when a WS frame wrote the task before the request failed", async () => {
    seedTask(makeTask());
    // A frame carrying the committed unread (e.g. the request timed out after
    // the server applied it).
    const serverTask = makeTask({ lastReadAt: null });
    mockMarkUnread.mockImplementationOnce(() => {
      syncTasksToQueryCache({ [AGENT_ID]: serverTask });
      return Promise.reject(new Error("timeout"));
    });

    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedTask(AGENT_ID)).toEqual(serverTask);
    // No rollback happened, so the override stays on its normal lifecycle.
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: UPDATED_AT })).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════
// useTaskRenameMutation
// ═══════════════════════════════════════════════════════════

describe("useTaskRenameMutation", () => {
  it("calls renameWorkspaceAgent with the correct path and body", async () => {
    seedTask(makeTask());
    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper: makeWrapper() });

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
    seedTask(makeTask({ title: "Old Title" }));
    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Shiny New Title" });
    });

    expect(getCachedTask(AGENT_ID)?.title).toBe("Shiny New Title");
  });

  it("rolls back the cache when the API call rejects", async () => {
    seedTask(makeTask({ title: "Keep Me" }));
    mockRename.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Bad Rename" });
    });
    await flushMicrotasks();

    expect(getCachedTask(AGENT_ID)?.title).toBe("Keep Me");
  });

  it("skips the rollback when a WS frame wrote the task while the request was in flight", async () => {
    seedTask(makeTask({ title: "Old Title" }));
    const serverTask = makeTask({ title: "Renamed Elsewhere", updatedAt: LATER_UPDATED_AT });
    mockRename.mockImplementationOnce(() => {
      syncTasksToQueryCache({ [AGENT_ID]: serverTask });
      return Promise.reject(new Error("network"));
    });

    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Bad Rename" });
    });
    await flushMicrotasks();

    expect(getCachedTask(AGENT_ID)).toEqual(serverTask);
  });
});

// ═══════════════════════════════════════════════════════════
// useRestoreTaskMutation
// ═══════════════════════════════════════════════════════════

describe("useRestoreTaskMutation", () => {
  it("calls restoreWorkspaceAgent with the correct path", async () => {
    sharedQueryClient.setQueryData(taskQueryKey(AGENT_ID), null);

    const { result } = renderHook(() => useRestoreTaskMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(mockRestore).toHaveBeenCalledOnce();
    expect(mockRestore).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
    });
  });

  it("never writes the cache — the WS delivers the restored task", async () => {
    sharedQueryClient.setQueryData(taskQueryKey(AGENT_ID), null);
    mockRestore.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useRestoreTaskMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    // No optimistic write on mutate, no rollback write on failure.
    expect(getCachedTask(AGENT_ID)).toBeNull();
  });

  it("does not clobber a WS-delivered restore when the request fails late", async () => {
    sharedQueryClient.setQueryData(taskQueryKey(AGENT_ID), null);
    const restoredTask = makeTask();
    mockRestore.mockImplementationOnce(() => {
      // Server committed the restore and streamed it before the HTTP response
      // failed (e.g. a timeout).
      syncTasksToQueryCache({ [AGENT_ID]: restoredTask });
      return Promise.reject(new Error("timeout"));
    });

    const { result } = renderHook(() => useRestoreTaskMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedTask(AGENT_ID)).toEqual(restoredTask);
  });
});

// ═══════════════════════════════════════════════════════════
// useDeleteTaskMutation
// ═══════════════════════════════════════════════════════════

describe("useDeleteTaskMutation", () => {
  // The caller tombstones synchronously via applyOptimisticTaskDelete and
  // threads the context into the mutation; these tests exercise that contract.
  const seedForDelete = (): void => {
    sharedQueryClient.setQueryData(taskIdsQueryKey(), [AGENT_ID]);
    seedTask(makeTask());
  };

  const getIds = (): ReadonlyArray<string> | undefined =>
    sharedQueryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey());

  it("calls deleteWorkspaceAgent with the skipWsAck path", async () => {
    seedForDelete();
    const deleteContext = applyOptimisticTaskDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteTaskMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID, deleteContext });
    });
    await flushMicrotasks();

    expect(mockDelete).toHaveBeenCalledOnce();
    expect(mockDelete).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
      meta: { skipWsAck: true, timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
  });

  it("tombstones the entry and removes the id (via the caller's apply)", () => {
    seedForDelete();

    applyOptimisticTaskDelete(AGENT_ID);

    expect(getCachedTask(AGENT_ID)).toBeNull();
    expect(getIds()).toEqual([]);
  });

  it("applies nothing for a task the cache never had, so rollback stays a no-op", () => {
    // A ghost apply must not write a tombstone (that would fake "deleted" for
    // an unknown entry) nor touch the ids list. The caller still sends the
    // DELETE; there is just nothing local to undo.
    const context = applyOptimisticTaskDelete("agent-ghost");

    expect(context.prev).toBeUndefined();
    expect(getCachedTask("agent-ghost")).toBeUndefined();
    expect(getIds()).toBeUndefined();

    rollbackOptimisticTaskDelete("agent-ghost", context);
    expect(getCachedTask("agent-ghost")).toBeUndefined();
  });

  it("treats a 404 as success: the agent is already gone, so the tombstone stands", async () => {
    seedForDelete();
    mockDelete.mockRejectedValueOnce(new HTTPException(404, "Agent agent-1 not found"));

    const deleteContext = applyOptimisticTaskDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteTaskMutation(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ workspaceId: WS_ID, agentId: AGENT_ID, deleteContext });
    });

    expect(getCachedTask(AGENT_ID)).toBeNull();
    expect(getIds()).toEqual([]);
  });

  it("restores the entry and re-adds the id when the request rejects", async () => {
    seedForDelete();
    const original = makeTask();
    mockDelete.mockRejectedValueOnce(new Error("network"));

    const deleteContext = applyOptimisticTaskDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteTaskMutation(), { wrapper: makeWrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ workspaceId: WS_ID, agentId: AGENT_ID, deleteContext }),
      ).rejects.toThrow("network");
    });

    expect(getCachedTask(AGENT_ID)).toEqual(original);
    expect(getIds()).toContain(AGENT_ID);
  });

  it("skips the restore when a WS frame wrote the task while the request was in flight", async () => {
    seedForDelete();
    // A frame carrying the committed delete (e.g. the request timed out after
    // the server applied it): the tombstone must survive the failed request's
    // rollback.
    const serverTask = makeTask({ isDeleted: true });
    mockDelete.mockImplementationOnce(() => {
      syncTasksToQueryCache({ [AGENT_ID]: serverTask });
      return Promise.reject(new Error("timeout"));
    });

    const deleteContext = applyOptimisticTaskDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteTaskMutation(), { wrapper: makeWrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ workspaceId: WS_ID, agentId: AGENT_ID, deleteContext }),
      ).rejects.toThrow("timeout");
    });

    // The frame tombstoned it too, so the entry stays null and the id stays out.
    expect(getCachedTask(AGENT_ID)).toBeNull();
    expect(getIds() ?? []).not.toContain(AGENT_ID);
  });
});
