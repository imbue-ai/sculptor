import { act, renderHook, type RenderHookResult } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { taskAtomFamily } from "../atoms/tasks";
import { useMarkRead } from "./useMarkRead";

// Capture calls to the mark-read endpoint without hitting the network.
const { mockMarkRead } = vi.hoisted(() => ({ mockMarkRead: vi.fn() }));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return { ...actual, markWorkspaceAgentRead: mockMarkRead };
});

const makeTask = (updatedAt: string, lastReadAt: string | null): CodingAgentTaskView =>
  ({ id: "agent-1", status: "READY", updatedAt, lastReadAt }) as unknown as CodingAgentTaskView;

const renderMarkRead = (store: ReturnType<typeof createStore>): RenderHookResult<void, unknown> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => createElement(Provider, { store }, children);
  return renderHook(() => useMarkRead("ws-1", "agent-1"), { wrapper });
};

beforeEach(() => {
  vi.clearAllMocks();
  mockMarkRead.mockResolvedValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useMarkRead", () => {
  it("flushes a pending debounced read when the agent is left mid-debounce", () => {
    const store = createStore();
    store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead(store);
    // The mount marks the agent read once; isolate the flush from it.
    expect(mockMarkRead).toHaveBeenCalledTimes(1);
    mockMarkRead.mockClear();

    // A new update arrives while viewing — schedules a debounced read.
    act(() => {
      store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z"));
    });

    // Leaving the agent before the debounce fires must flush the pending read,
    // so the agent persists as read instead of reappearing unread.
    act(() => {
      unmount();
    });

    expect(mockMarkRead).toHaveBeenCalledTimes(1);
    expect(mockMarkRead).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ agent_id: "agent-1" }) }),
    );
  });

  it("does not flush when there is no pending read", () => {
    const store = createStore();
    store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead(store);
    expect(mockMarkRead).toHaveBeenCalledTimes(1);
    mockMarkRead.mockClear();

    act(() => {
      unmount();
    });

    expect(mockMarkRead).not.toHaveBeenCalled();
  });

  it("does not flush when the user marked the agent unread while a read was pending", () => {
    const store = createStore();
    store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:05.000Z", "2024-01-01T00:00:01.000Z"));
    const { unmount } = renderMarkRead(store);
    mockMarkRead.mockClear();

    // A new update schedules a debounced read...
    act(() => {
      store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:06.000Z", "2024-01-01T00:00:01.000Z"));
    });
    // ...then the user explicitly marks it unread (lastReadAt -> null).
    act(() => {
      store.set(taskAtomFamily("agent-1"), makeTask("2024-01-01T00:00:06.000Z", null));
    });

    act(() => {
      unmount();
    });

    expect(mockMarkRead).not.toHaveBeenCalled();
  });
});
