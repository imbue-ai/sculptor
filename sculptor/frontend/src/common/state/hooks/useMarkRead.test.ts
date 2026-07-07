import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, type RenderHookResult } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { queryClient as sharedQueryClient } from "../../queryClient.ts";
import { taskAtomFamily } from "../atoms/tasks";
import { resetUnreadOverridesForTesting, setUnreadOverride } from "../atoms/unreadOverrides";
import { useMarkRead } from "./useMarkRead";

// Capture calls to the mark-read/mark-unread endpoints without hitting the network.
const { mockMarkRead, mockMarkUnread } = vi.hoisted(() => ({ mockMarkRead: vi.fn(), mockMarkUnread: vi.fn() }));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return { ...actual, markWorkspaceAgentRead: mockMarkRead, markWorkspaceAgentUnread: mockMarkUnread };
});

const makeTask = (updatedAt: string, lastReadAt: string | null, id = "agent-1"): CodingAgentTaskView =>
  ({ id, status: "READY", updatedAt, lastReadAt }) as unknown as CodingAgentTaskView;

const renderMarkRead = (store: ReturnType<typeof createStore>): RenderHookResult<void, unknown> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
    createElement(QueryClientProvider, { client: sharedQueryClient }, createElement(Provider, { store }, children));
  return renderHook(() => useMarkRead("ws-1", "agent-1"), { wrapper });
};

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

beforeEach(() => {
  vi.clearAllMocks();
  mockMarkRead.mockResolvedValue(true);
  mockMarkUnread.mockResolvedValue(true);
  // Unread overrides live in a module-level map (not a Jotai store), so they
  // leak across tests without an explicit reset.
  resetUnreadOverridesForTesting();
  // Clear the shared queryClient cache between tests so tasks don't leak.
  sharedQueryClient.removeQueries({ queryKey: ["sculptor"] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useMarkRead", () => {
  it("flushes a pending debounced read when the agent is left mid-debounce", async () => {
    const store = createStore();
    store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead(store);
    // The mount fires markRead via useEffect → .mutate() which schedules on a
    // microtask. Flush microtasks so the mock is recorded before this assertion.
    await flushMicrotasks();
    expect(mockMarkRead).toHaveBeenCalledTimes(1);
    mockMarkRead.mockClear();

    // A new update arrives while viewing — schedules a debounced read.
    act(() => {
      store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z"));
    });

    // Leaving the agent before the debounce fires must flush the pending read.
    act(() => {
      unmount();
    });
    await flushMicrotasks();

    expect(mockMarkRead).toHaveBeenCalledTimes(1);
    expect(mockMarkRead).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ agent_id: "agent-1" }) }),
    );
  });

  it("does not flush when there is no pending read", async () => {
    const store = createStore();
    store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead(store);
    await flushMicrotasks();
    expect(mockMarkRead).toHaveBeenCalledTimes(1);
    mockMarkRead.mockClear();

    act(() => {
      unmount();
    });
    await flushMicrotasks();

    expect(mockMarkRead).not.toHaveBeenCalled();
  });

  it("does not flush when the user marked the agent unread while a read was pending", async () => {
    const store = createStore();
    store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead(store);
    await flushMicrotasks();
    mockMarkRead.mockClear();

    // A new update schedules a debounced read...
    act(() => {
      store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z"));
    });
    // ...then the user explicitly marks it unread. The mark-unread mutation
    // records the override AND clears lastReadAt optimistically.
    act(() => {
      const task = store.get(taskAtomFamily("agent-1"))!;
      setUnreadOverride("agent-1", task);
      store.set(taskAtomFamily("agent-1"), { ...task, lastReadAt: null });
    });

    act(() => {
      unmount();
    });
    await flushMicrotasks();

    expect(mockMarkRead).not.toHaveBeenCalled();
  });

  it("preserves an explicit mark-unread on the agent being left when switching agents", async () => {
    const store = createStore();
    store.set(taskAtomFamily("agent-x"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z", "agent-x"));
    store.set(taskAtomFamily("agent-y"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z", "agent-y"));
    const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
      createElement(QueryClientProvider, { client: sharedQueryClient }, createElement(Provider, { store }, children));
    const { rerender } = renderHook(({ agentId }: { agentId: string }) => useMarkRead("ws-1", agentId), {
      wrapper,
      initialProps: { agentId: "agent-x" },
    });
    await flushMicrotasks();
    mockMarkRead.mockClear();

    // agent-x gets an update (schedules a debounced read), then the user marks
    // agent-x unread before the debounce fires (recording its unread override).
    act(() => {
      store.set(taskAtomFamily("agent-x"), makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z", "agent-x"));
    });
    act(() => {
      const task = store.get(taskAtomFamily("agent-x"))!;
      setUnreadOverride("agent-x", task);
      store.set(taskAtomFamily("agent-x"), { ...task, lastReadAt: null });
    });

    // Switching to agent-y must consult agent-x's state (it is explicitly
    // unread), not agent-y's, so the flush must not re-mark agent-x read.
    act(() => {
      rerender({ agentId: "agent-y" });
    });

    await flushMicrotasks();

    const didMarkAgentXRead = mockMarkRead.mock.calls.some(
      (call) => (call[0] as { path?: { agent_id?: string } })?.path?.agent_id === "agent-x",
    );
    expect(didMarkAgentXRead).toBe(false);
  });
});
