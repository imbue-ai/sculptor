import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { TaskStatus } from "../../../api";
import { HTTPException } from "../../utils/errors.ts";
import { isUnreadOverrideActive, resetUnreadOverridesForTesting } from "../atoms/unreadOverrides";
import {
  agentIdsQueryKey,
  agentQueryKey,
  queryClient as sharedQueryClient,
  syncAgentsToQueryCache,
} from "../queryClient.ts";
import {
  applyOptimisticAgentDelete,
  MUTATION_SETTLE_TIMEOUT_MS,
  rollbackOptimisticAgentDelete,
  useAgentRenameMutation,
  useDeleteAgentMutation,
  useMarkReadMutation,
  useMarkUnreadMutation,
  useRestoreAgentMutation,
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

const makeAgent = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
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

const seedAgent = (agent: CodingAgentTaskView): void => {
  sharedQueryClient.setQueryData(agentQueryKey(agent.id as string), agent);
};

const getCachedAgent = (id: string): CodingAgentTaskView | null | undefined =>
  sharedQueryClient.getQueryData<CodingAgentTaskView | null>(agentQueryKey(id));

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
    seedAgent(makeAgent());
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

  it("optimistically sets lastReadAt on the cached agent", async () => {
    seedAgent(makeAgent({ lastReadAt: "2020-01-01T00:00:00.000Z" }));
    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    const cached = getCachedAgent(AGENT_ID);
    expect(cached?.lastReadAt).not.toBe("2020-01-01T00:00:00.000Z");
    expect(cached?.lastReadAt).toBeTruthy();
  });

  it("rolls back the cache when the API call rejects", async () => {
    const originalLastRead = "2020-01-01T00:00:00.000Z";
    seedAgent(makeAgent({ lastReadAt: originalLastRead }));
    mockMarkRead.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    const cached = getCachedAgent(AGENT_ID);
    expect(cached?.lastReadAt).toBe(originalLastRead);
  });

  it("skips the rollback when a WS frame wrote the agent while the request was in flight", async () => {
    seedAgent(makeAgent({ lastReadAt: "2020-01-01T00:00:00.000Z" }));
    const serverAgent = makeAgent({ lastReadAt: null, updatedAt: LATER_UPDATED_AT });
    mockMarkRead.mockImplementationOnce(() => {
      // The frame is authoritative: it must survive the failed request's
      // rollback (the delta stream will not re-send an unchanged agent).
      syncAgentsToQueryCache({ [AGENT_ID]: serverAgent });
      return Promise.reject(new Error("network"));
    });

    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedAgent(AGENT_ID)).toEqual(serverAgent);
  });
});

// ═══════════════════════════════════════════════════════════
// useMarkUnreadMutation
// ═══════════════════════════════════════════════════════════

describe("useMarkUnreadMutation", () => {
  it("calls markWorkspaceAgentUnread with the correct path", async () => {
    seedAgent(makeAgent());
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
    seedAgent(makeAgent({ lastReadAt: "2024-06-01T00:00:00.000Z" }));
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    expect(getCachedAgent(AGENT_ID)?.lastReadAt).toBeNull();
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: UPDATED_AT })).toBe(true);
  });

  it("keys an idle-agent override to the agent's updatedAt at mark time", async () => {
    seedAgent(makeAgent());
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    // A later turn expires the override without an explicit clear.
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: LATER_UPDATED_AT })).toBe(false);
  });

  it("holds a running agent's override through the rest of its run", async () => {
    seedAgent(makeAgent({ status: TaskStatus.RUNNING }));
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.RUNNING, updatedAt: LATER_UPDATED_AT })).toBe(true);
  });

  it("preserves the other agent fields on the optimistic update", async () => {
    seedAgent(makeAgent({ title: "My agent" }));
    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });

    const cached = getCachedAgent(AGENT_ID);
    expect(cached?.title).toBe("My agent");
    expect(cached?.updatedAt).toBe(UPDATED_AT);
  });

  it("does nothing for an agent the stream has not delivered", async () => {
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
    seedAgent(makeAgent({ lastReadAt: originalLastRead }));
    mockMarkUnread.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedAgent(AGENT_ID)?.lastReadAt).toBe(originalLastRead);
    // The persist failed, so the dot must not stay pinned to "unread".
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: UPDATED_AT })).toBe(false);
  });

  it("keeps the frame and the override when a WS frame wrote the agent before the request failed", async () => {
    seedAgent(makeAgent());
    // A frame carrying the committed unread (e.g. the request timed out after
    // the server applied it).
    const serverAgent = makeAgent({ lastReadAt: null });
    mockMarkUnread.mockImplementationOnce(() => {
      syncAgentsToQueryCache({ [AGENT_ID]: serverAgent });
      return Promise.reject(new Error("timeout"));
    });

    const { result } = renderHook(() => useMarkUnreadMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedAgent(AGENT_ID)).toEqual(serverAgent);
    // No rollback happened, so the override stays on its normal lifecycle.
    expect(isUnreadOverrideActive(AGENT_ID, { status: TaskStatus.READY, updatedAt: UPDATED_AT })).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════
// useAgentRenameMutation
// ═══════════════════════════════════════════════════════════

describe("useAgentRenameMutation", () => {
  it("calls renameWorkspaceAgent with the correct path and body", async () => {
    seedAgent(makeAgent());
    const { result } = renderHook(() => useAgentRenameMutation(WS_ID), { wrapper: makeWrapper() });

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
    seedAgent(makeAgent({ title: "Old Title" }));
    const { result } = renderHook(() => useAgentRenameMutation(WS_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Shiny New Title" });
    });

    expect(getCachedAgent(AGENT_ID)?.title).toBe("Shiny New Title");
  });

  it("rolls back the cache when the API call rejects", async () => {
    seedAgent(makeAgent({ title: "Keep Me" }));
    mockRename.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useAgentRenameMutation(WS_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Bad Rename" });
    });
    await flushMicrotasks();

    expect(getCachedAgent(AGENT_ID)?.title).toBe("Keep Me");
  });

  it("skips the rollback when a WS frame wrote the agent while the request was in flight", async () => {
    seedAgent(makeAgent({ title: "Old Title" }));
    const serverAgent = makeAgent({ title: "Renamed Elsewhere", updatedAt: LATER_UPDATED_AT });
    mockRename.mockImplementationOnce(() => {
      syncAgentsToQueryCache({ [AGENT_ID]: serverAgent });
      return Promise.reject(new Error("network"));
    });

    const { result } = renderHook(() => useAgentRenameMutation(WS_ID), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ agentId: AGENT_ID, newTitle: "Bad Rename" });
    });
    await flushMicrotasks();

    expect(getCachedAgent(AGENT_ID)).toEqual(serverAgent);
  });
});

// ═══════════════════════════════════════════════════════════
// useRestoreAgentMutation
// ═══════════════════════════════════════════════════════════

describe("useRestoreAgentMutation", () => {
  it("calls restoreWorkspaceAgent with the correct path", async () => {
    sharedQueryClient.setQueryData(agentQueryKey(AGENT_ID), null);

    const { result } = renderHook(() => useRestoreAgentMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(mockRestore).toHaveBeenCalledOnce();
    expect(mockRestore).toHaveBeenCalledWith({
      path: { workspace_id: WS_ID, agent_id: AGENT_ID },
    });
  });

  it("never writes the cache — the WS delivers the restored agent", async () => {
    sharedQueryClient.setQueryData(agentQueryKey(AGENT_ID), null);
    mockRestore.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useRestoreAgentMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    // No optimistic write on mutate, no rollback write on failure.
    expect(getCachedAgent(AGENT_ID)).toBeNull();
  });

  it("does not clobber a WS-delivered restore when the request fails late", async () => {
    sharedQueryClient.setQueryData(agentQueryKey(AGENT_ID), null);
    const restoredAgent = makeAgent();
    mockRestore.mockImplementationOnce(() => {
      // Server committed the restore and streamed it before the HTTP response
      // failed (e.g. a timeout).
      syncAgentsToQueryCache({ [AGENT_ID]: restoredAgent });
      return Promise.reject(new Error("timeout"));
    });

    const { result } = renderHook(() => useRestoreAgentMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ workspaceId: WS_ID, agentId: AGENT_ID });
    });
    await flushMicrotasks();

    expect(getCachedAgent(AGENT_ID)).toEqual(restoredAgent);
  });
});

// ═══════════════════════════════════════════════════════════
// useDeleteAgentMutation
// ═══════════════════════════════════════════════════════════

describe("useDeleteAgentMutation", () => {
  // The caller tombstones synchronously via applyOptimisticAgentDelete and
  // threads the context into the mutation; these tests exercise that contract.
  const seedForDelete = (): void => {
    sharedQueryClient.setQueryData(agentIdsQueryKey(), [AGENT_ID]);
    seedAgent(makeAgent());
  };

  const getIds = (): ReadonlyArray<string> | undefined =>
    sharedQueryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey());

  it("calls deleteWorkspaceAgent with the skipWsAck path", async () => {
    seedForDelete();
    const deleteContext = applyOptimisticAgentDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteAgentMutation(), { wrapper: makeWrapper() });

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

    applyOptimisticAgentDelete(AGENT_ID);

    expect(getCachedAgent(AGENT_ID)).toBeNull();
    expect(getIds()).toEqual([]);
  });

  it("applies nothing for an agent the cache never had, so rollback stays a no-op", () => {
    // A ghost apply must not write a tombstone (that would fake "deleted" for
    // an unknown entry) nor touch the ids list. The caller still sends the
    // DELETE; there is just nothing local to undo.
    const context = applyOptimisticAgentDelete("agent-ghost");

    expect(context.prev).toBeUndefined();
    expect(getCachedAgent("agent-ghost")).toBeUndefined();
    expect(getIds()).toBeUndefined();

    rollbackOptimisticAgentDelete("agent-ghost", context);
    expect(getCachedAgent("agent-ghost")).toBeUndefined();
  });

  it("treats a 404 as success: the agent is already gone, so the tombstone stands", async () => {
    seedForDelete();
    mockDelete.mockRejectedValueOnce(new HTTPException(404, "Agent agent-1 not found"));

    const deleteContext = applyOptimisticAgentDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteAgentMutation(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ workspaceId: WS_ID, agentId: AGENT_ID, deleteContext });
    });

    expect(getCachedAgent(AGENT_ID)).toBeNull();
    expect(getIds()).toEqual([]);
  });

  it("restores the entry and re-adds the id when the request rejects", async () => {
    seedForDelete();
    const original = makeAgent();
    mockDelete.mockRejectedValueOnce(new Error("network"));

    const deleteContext = applyOptimisticAgentDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteAgentMutation(), { wrapper: makeWrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ workspaceId: WS_ID, agentId: AGENT_ID, deleteContext }),
      ).rejects.toThrow("network");
    });

    expect(getCachedAgent(AGENT_ID)).toEqual(original);
    expect(getIds()).toContain(AGENT_ID);
  });

  it("skips the restore when a WS frame wrote the agent while the request was in flight", async () => {
    seedForDelete();
    // A frame carrying the committed delete (e.g. the request timed out after
    // the server applied it): the tombstone must survive the failed request's
    // rollback.
    const serverAgent = makeAgent({ isDeleted: true });
    mockDelete.mockImplementationOnce(() => {
      syncAgentsToQueryCache({ [AGENT_ID]: serverAgent });
      return Promise.reject(new Error("timeout"));
    });

    const deleteContext = applyOptimisticAgentDelete(AGENT_ID);
    const { result } = renderHook(() => useDeleteAgentMutation(), { wrapper: makeWrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ workspaceId: WS_ID, agentId: AGENT_ID, deleteContext }),
      ).rejects.toThrow("timeout");
    });

    // The frame tombstoned it too, so the entry stays null and the id stays out.
    expect(getCachedAgent(AGENT_ID)).toBeNull();
    expect(getIds() ?? []).not.toContain(AGENT_ID);
  });
});
