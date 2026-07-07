import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { queryClient as sharedQueryClient, taskQueryKey } from "../../queryClient.ts";
import { useMarkReadMutation, useMarkUnreadMutation, useRestoreTaskMutation, useTaskRenameMutation } from "./index";

// ── Mock API ────────────────────────────────────────────────
const { mockMarkRead, mockMarkUnread, mockRename, mockRestore } = vi.hoisted(() => ({
  mockMarkRead: vi.fn(),
  mockMarkUnread: vi.fn(),
  mockRename: vi.fn(),
  mockRestore: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    markWorkspaceAgentRead: mockMarkRead,
    markWorkspaceAgentUnread: mockMarkUnread,
    renameWorkspaceAgent: mockRename,
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

/** Wrapper that provides QueryClientProvider. Hooks use `useStore()` with the default store. */
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
    const { result } = renderHook(() => useMarkReadMutation(WS_ID, AGENT_ID), { wrapper: makeWrapper() });

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
    const { result } = renderHook(() => useMarkReadMutation(WS_ID, AGENT_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate();
    });

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).not.toBe("2020-01-01T00:00:00.000Z");
    expect(cached?.lastReadAt).toBeTruthy();
  });

  it("rolls back the cache when the API call rejects", async () => {
    const originalLastRead = "2020-01-01T00:00:00.000Z";
    const task = makeTask({ lastReadAt: originalLastRead });
    seedTask(task);
    mockMarkRead.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useMarkReadMutation(WS_ID, AGENT_ID), { wrapper: makeWrapper() });

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

  it("optimistically sets lastReadAt to null on the cached task", async () => {
    const task = makeTask({ lastReadAt: "2024-06-01T00:00:00.000Z" });
    seedTask(task);
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.lastReadAt).toBeNull();
  });

  it("rolls back the cache when the API call rejects", async () => {
    const originalLastRead = "2024-06-01T12:00:00.000Z";
    const task = makeTask({ lastReadAt: originalLastRead });
    seedTask(task);
    mockMarkUnread.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
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
    const task = makeTask({ title: "Old Title" });
    seedTask(task);
    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper: makeWrapper() });

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

    const { result } = renderHook(() => useTaskRenameMutation(WS_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Bad Rename" });
    });
    await flushMicrotasks();

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("Keep Me");
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

  it("does not modify the cache during onMutate", async () => {
    const task = makeTask({ title: "Stale" });
    seedTask(task);

    const { result } = renderHook(() => useRestoreTaskMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    // Restore intentionally snapshots without writing — the WS bridge delivers
    // the authoritative restored task.
    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("Stale");
  });

  it("rolls back the cache when the API call rejects", async () => {
    const prevTask = makeTask({ title: "Was Deleted" });
    seedTask(prevTask);
    mockRestore.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useRestoreTaskMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    const cached = getCachedTask(AGENT_ID);
    expect(cached?.title).toBe("Was Deleted");
  });
});
