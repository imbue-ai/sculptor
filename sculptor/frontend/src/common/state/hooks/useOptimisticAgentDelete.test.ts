import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { agentIdsQueryKey, agentQueryKey, queryClient } from "../queryClient.ts";
import { useOptimisticAgentDelete } from "./useOptimisticAgentDelete";

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

vi.mock("~/common/hooks/navigation.ts", () => ({
  useImbueNavigate: (): Record<string, unknown> => ({ navigateToRoot: vi.fn() }),
  useImbueLocation: (): Record<string, unknown> => ({ isAgentRoute: false }),
  useImbueParams: (): Record<string, unknown> => ({ agentId: undefined }),
}));

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const createMockAgent = (id: string): CodingAgentTaskView =>
  ({
    id,
    status: "RUNNING",
    isDeleted: false,
  }) as CodingAgentTaskView;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

// The hook snapshots and tombstones agents in the query cache; tests seed the
// cache the same way the WS bridge does.
const seedAgent = (agent: CodingAgentTaskView): void => {
  queryClient.setQueryData(agentQueryKey(agent.id as string), agent);
};

const getCachedAgent = (id: string): CodingAgentTaskView | null | undefined =>
  queryClient.getQueryData<CodingAgentTaskView | null>(agentQueryKey(id));

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

describe("useOptimisticAgentDelete", () => {
  it("retries the agent captured per-call, not the most recently failed agent", async () => {
    // Regression for the shared-ref bug: the toast's Retry used to re-delete
    // whichever agent failed most recently, so retrying the FIRST failure would
    // wrongly target the SECOND agent.
    const store = createStore();
    queryClient.setQueryData(agentIdsQueryKey(), ["agent-A", "agent-B"]);
    seedAgent(createMockAgent("agent-A"));
    seedAgent(createMockAgent("agent-B"));

    const { result } = renderHook(() => useOptimisticAgentDelete({ workspaceId: "ws-1" }), {
      wrapper: makeWrapper(store),
    });

    // Both initial deletes reject -> two error toasts (each set on the same atom).
    mockDeleteWorkspaceAgent.mockRejectedValue(new Error("network"));

    result.current.execute("agent-A", "Agent A");
    await flushMicrotasks();
    const firstRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    result.current.execute("agent-B", "Agent B");
    await flushMicrotasks();
    const secondRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    expect(firstRetry).toBeDefined();
    expect(secondRetry).toBeDefined();
    expect(firstRetry).not.toBe(secondRetry);

    // Re-seed agent-A so its optimistic re-delete proceeds to the API call.
    seedAgent(createMockAgent("agent-A"));
    queryClient.setQueryData(agentIdsQueryKey(), ["agent-A"]);

    mockDeleteWorkspaceAgent.mockClear();
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    // Invoke the FIRST failure's Retry. It must re-delete agent-A, not agent-B.
    firstRetry!();
    await flushMicrotasks();

    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledTimes(1);
    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ agent_id: "agent-A" }) }),
    );
  });

  it("sends the DELETE even when the agent is missing from the cache (SCU-1832)", async () => {
    // A stale reference (route, palette action) can outlive the cache entry.
    // The cache's ignorance must not silently swallow the user's delete —
    // the server is the authority on deletability.
    const store = createStore();
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    const { result } = renderHook(() => useOptimisticAgentDelete({ workspaceId: "ws-1" }), {
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

    const { result } = renderHook(() => useOptimisticAgentDelete({ workspaceId: "ws-1", onNavigateAfterDelete }), {
      wrapper: makeWrapper(store),
    });

    result.current.execute("task-ghost", "Ghost Task");
    await flushMicrotasks();

    expect(onNavigateAfterDelete).not.toHaveBeenCalled();
    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledOnce();
  });

  it("tombstones the agent before the navigation callback observes it", () => {
    // The removal must be visible in every store by the time callbacks run, so
    // a callback reading the cache sees the tombstone, not the live agent.
    const store = createStore();
    queryClient.setQueryData(agentIdsQueryKey(), ["task-A"]);
    seedAgent(createMockAgent("task-A"));
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    let observedDuringCallback: CodingAgentTaskView | null | undefined = createMockAgent("task-A");
    const onNavigateAfterDelete = vi.fn((agentId: string): void => {
      observedDuringCallback = getCachedAgent(agentId);
    });

    const { result } = renderHook(() => useOptimisticAgentDelete({ workspaceId: "ws-1", onNavigateAfterDelete }), {
      wrapper: makeWrapper(store),
    });

    result.current.execute("task-A", "Task A");

    expect(onNavigateAfterDelete).toHaveBeenCalledOnce();
    expect(observedDuringCallback).toBeNull();
    expect(queryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey())).toEqual([]);
  });
});
