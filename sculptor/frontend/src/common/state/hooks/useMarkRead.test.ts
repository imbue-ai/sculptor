import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, type RenderHookResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { queryClient as sharedQueryClient, taskQueryKey } from "../../queryClient.ts";
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

// The hook reads tasks from the query cache (useTask); tests seed and update
// the cache the same way the WS bridge does.
const seedTask = (task: CodingAgentTaskView): void => {
  sharedQueryClient.setQueryData(taskQueryKey(task.id as string), task);
};

const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
  createElement(QueryClientProvider, { client: sharedQueryClient }, children);

const renderMarkRead = (): RenderHookResult<void, unknown> =>
  renderHook(() => useMarkRead("ws-1", "agent-1"), { wrapper });

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

// Query-cache notifications are delivered via setTimeout(0) (TanStack's
// notifyManager), so a cache write only reaches the hook on the next macrotask
// — unlike the synchronous Jotai notify this hook previously relied on.
const writeTaskAndNotify = async (task: CodingAgentTaskView): Promise<void> => {
  await act(async () => {
    seedTask(task);
    await flushMicrotasks();
  });
};

beforeEach(() => {
  vi.clearAllMocks();
  mockMarkRead.mockResolvedValue(true);
  mockMarkUnread.mockResolvedValue(true);
  // Unread overrides live in a module-level map (not React state), so they
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
    seedTask(makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead();
    // The mount fires markRead via useEffect → .mutate() which schedules on a
    // microtask. Flush microtasks so the mock is recorded before this assertion.
    await flushMicrotasks();
    expect(mockMarkRead).toHaveBeenCalledTimes(1);
    mockMarkRead.mockClear();

    // A new update arrives while viewing — schedules a debounced read.
    await writeTaskAndNotify(makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z"));

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
    seedTask(makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead();
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
    seedTask(makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead();
    await flushMicrotasks();
    mockMarkRead.mockClear();

    // A new update schedules a debounced read...
    await writeTaskAndNotify(makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z"));
    // ...then the user explicitly marks it unread. The mark-unread mutation
    // records the override AND clears lastReadAt optimistically.
    const task = sharedQueryClient.getQueryData<CodingAgentTaskView>(taskQueryKey("agent-1"))!;
    setUnreadOverride("agent-1", task);
    await writeTaskAndNotify({ ...task, lastReadAt: null });

    act(() => {
      unmount();
    });
    await flushMicrotasks();

    expect(mockMarkRead).not.toHaveBeenCalled();
  });

  it("preserves an explicit mark-unread on the agent being left when switching agents", async () => {
    seedTask(makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z", "agent-x"));
    seedTask(makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z", "agent-y"));
    const { rerender } = renderHook(({ agentId }: { agentId: string }) => useMarkRead("ws-1", agentId), {
      wrapper,
      initialProps: { agentId: "agent-x" },
    });
    await flushMicrotasks();
    mockMarkRead.mockClear();

    // agent-x gets an update (schedules a debounced read), then the user marks
    // agent-x unread before the debounce fires (recording its unread override).
    await writeTaskAndNotify(makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z", "agent-x"));
    const task = sharedQueryClient.getQueryData<CodingAgentTaskView>(taskQueryKey("agent-x"))!;
    setUnreadOverride("agent-x", task);
    await writeTaskAndNotify({ ...task, lastReadAt: null });

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
