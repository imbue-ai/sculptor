import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "../../../api";
import {
  agentIdsQueryKey,
  agentQueryKey,
  queryClient as sharedQueryClient,
  syncAgentsToQueryCache,
} from "../queryClient.ts";
import { useAgent, useAgentIds } from "./useAgent";

// useAgent/useAgentIds tests get their own QueryClient to avoid polluting the
// singleton with test state. syncAgentsToQueryCache tests use the real singleton.
let testQueryClient: QueryClient;

const createWrapper =
  (qc: QueryClient) =>
  ({ children }: { children: ReactNode }): ReactElement =>
    createElement(QueryClientProvider, { client: qc }, children);

const createMockAgent = (id: string, overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
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
  // Clear the singleton before every test so syncAgentsToQueryCache state
  // doesn't leak between tests.
  sharedQueryClient.removeQueries({ queryKey: ["sculptor"] });
});

afterEach(() => {
  testQueryClient.clear();
});

describe("useAgent", () => {
  it("returns null when the cache has no value for the agent id", () => {
    const { result } = renderHook(() => useAgent("task-1"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toBeNull();
  });

  it("returns the agent value written via the WS bridge", () => {
    const agent = createMockAgent("task-1");
    testQueryClient.setQueryData<CodingAgentTaskView | null>(agentQueryKey("task-1"), agent);

    const { result } = renderHook(() => useAgent("task-1"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toEqual(agent);
  });

  it("returns null when the cache value is null (soft-deleted agent)", () => {
    testQueryClient.setQueryData<CodingAgentTaskView | null>(agentQueryKey("deleted"), null);

    const { result } = renderHook(() => useAgent("deleted"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toBeNull();
  });

  it("re-renders when the cache entry for the agent changes", async () => {
    const agentV1 = createMockAgent("task-1");
    testQueryClient.setQueryData<CodingAgentTaskView | null>(agentQueryKey("task-1"), agentV1);

    const { result } = renderHook(() => useAgent("task-1"), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current?.updatedAt).toBe("2026-07-01T00:00:00Z");

    const agentV2 = createMockAgent("task-1", { updatedAt: "2026-07-02T00:00:00Z" });
    testQueryClient.setQueryData<CodingAgentTaskView | null>(agentQueryKey("task-1"), agentV2);

    await waitFor(() => {
      expect(result.current?.updatedAt).toBe("2026-07-02T00:00:00Z");
    });
  });
});

describe("useAgentIds", () => {
  it("returns undefined when no WS frame has seeded the cache", () => {
    const { result } = renderHook(() => useAgentIds(), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toBeUndefined();
  });

  it("returns ids seeded via the WS bridge", () => {
    testQueryClient.setQueryData<ReadonlyArray<string>>(agentIdsQueryKey(), ["a", "b"]);

    const { result } = renderHook(() => useAgentIds(), {
      wrapper: createWrapper(testQueryClient),
    });
    expect(result.current).toEqual(["a", "b"]);
  });
});

describe("syncAgentsToQueryCache", () => {
  it("writes non-deleted agents to the query cache", () => {
    const agents: Record<string, CodingAgentTaskView> = {
      "task-1": createMockAgent("task-1"),
      "task-2": createMockAgent("task-2"),
    };
    syncAgentsToQueryCache(agents);
    expect(sharedQueryClient.getQueryData(agentQueryKey("task-1"))).toEqual(createMockAgent("task-1"));
    expect(sharedQueryClient.getQueryData(agentQueryKey("task-2"))).toEqual(createMockAgent("task-2"));
  });

  it("sets soft-deleted agents to null in the cache", () => {
    const agent = createMockAgent("deleted-task");
    syncAgentsToQueryCache({ "deleted-task": agent });
    expect(sharedQueryClient.getQueryData(agentQueryKey("deleted-task"))).not.toBeNull();

    syncAgentsToQueryCache({ "deleted-task": { ...agent, isDeleted: true } });
    expect(sharedQueryClient.getQueryData(agentQueryKey("deleted-task"))).toBeNull();
  });

  it("populates agentIds with non-deleted ids and removes deleted ones", () => {
    syncAgentsToQueryCache({
      "t-1": createMockAgent("t-1"),
      "t-2": createMockAgent("t-2"),
    });
    expect(sharedQueryClient.getQueryData(agentIdsQueryKey())).toEqual(expect.arrayContaining(["t-1", "t-2"]));

    // Second frame: t-2 is now soft-deleted, t-3 is new.
    syncAgentsToQueryCache({
      "t-2": { ...createMockAgent("t-2"), isDeleted: true },
      "t-3": createMockAgent("t-3"),
    });
    const finalIds = sharedQueryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey());
    expect(finalIds).toContain("t-1");
    expect(finalIds).toContain("t-3");
    expect(finalIds).not.toContain("t-2");
  });

  it("preserves order of ids from prior frames, appending new ones at the end", () => {
    syncAgentsToQueryCache({
      a: createMockAgent("a"),
      b: createMockAgent("b"),
    });
    syncAgentsToQueryCache({
      c: createMockAgent("c"),
    });
    const ids = sharedQueryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey());
    expect(ids).toEqual(["a", "b", "c"]);
  });

  it("does not update agentIds when no ids actually changed", () => {
    syncAgentsToQueryCache({
      a: createMockAgent("a"),
    });
    const before = sharedQueryClient.getQueryData(agentIdsQueryKey());

    // Re-send the same agent with a different title but same id.
    syncAgentsToQueryCache({
      a: createMockAgent("a", { title: "new title" }),
    });
    const after = sharedQueryClient.getQueryData(agentIdsQueryKey());

    // Same reference — agentIds unchanged.
    expect(before).toBe(after);
  });
});
