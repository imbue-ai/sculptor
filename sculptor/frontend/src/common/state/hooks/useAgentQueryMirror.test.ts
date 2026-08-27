import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "../../../api";
import { agentAtomFamily, agentIdsAtom, agentsArrayAtom } from "../atoms/agents";
import { agentQueryKey, queryClient, syncAgentsToQueryCache } from "../queryClient.ts";
import { useAgentQueryMirror } from "./useAgentQueryMirror";

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

const renderMirror = (store: ReturnType<typeof createStore>): ReturnType<typeof renderHook> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => createElement(Provider, { store }, children);
  return renderHook(() => useAgentQueryMirror(), { wrapper });
};

beforeEach(() => {
  queryClient.removeQueries({ queryKey: ["sculptor"] });
});

describe("useAgentQueryMirror", () => {
  it("projects WS frames into the Jotai agent atoms", () => {
    const store = createStore();
    renderMirror(store);

    syncAgentsToQueryCache({ "t-1": createMockAgent("t-1"), "t-2": createMockAgent("t-2") });

    expect(store.get(agentAtomFamily("t-1"))).toEqual(createMockAgent("t-1"));
    expect(store.get(agentAtomFamily("t-2"))).toEqual(createMockAgent("t-2"));
    expect(store.get(agentIdsAtom)).toEqual(["t-1", "t-2"]);
  });

  it("marks the agent list as loaded (undefined -> []) on an empty first frame", () => {
    const store = createStore();
    renderMirror(store);
    expect(store.get(agentsArrayAtom)).toBeUndefined();

    // A zero-agent instance streams frames whose agent-view map is empty; the
    // first frame must still flip the list from "loading" to "loaded, empty".
    syncAgentsToQueryCache({});

    expect(store.get(agentIdsAtom)).toEqual([]);
    expect(store.get(agentsArrayAtom)).toEqual([]);
  });

  it("projects tombstones: atom null, id dropped, per-agent settings removed", () => {
    const store = createStore();
    renderMirror(store);
    const agent = createMockAgent("t-1");
    syncAgentsToQueryCache({ "t-1": agent });
    localStorage.setItem("sculptor-fast-mode-t-1", "true");

    syncAgentsToQueryCache({ "t-1": { ...agent, isDeleted: true } });

    expect(store.get(agentAtomFamily("t-1"))).toBeNull();
    expect(store.get(agentIdsAtom)).toEqual([]);
    expect(localStorage.getItem("sculptor-fast-mode-t-1")).toBeNull();
  });

  it("projects optimistic mutation writes, not just WS frames", () => {
    const store = createStore();
    renderMirror(store);
    const agent = createMockAgent("t-1");
    syncAgentsToQueryCache({ "t-1": agent });

    // A mutation's optimistic update writes the cache directly.
    queryClient.setQueryData(agentQueryKey("t-1"), { ...agent, title: "Renamed" });

    expect(store.get(agentAtomFamily("t-1"))?.title).toBe("Renamed");
  });

  it("does not notify Jotai subscribers for a frame that changes nothing", () => {
    const store = createStore();
    renderMirror(store);
    const agent = createMockAgent("t-1");
    syncAgentsToQueryCache({ "t-1": agent });

    let notificationCount = 0;
    const unsubscribe = store.sub(agentAtomFamily("t-1"), () => {
      notificationCount += 1;
    });

    // Structural sharing keeps the cached agent referentially identical, so
    // the mirror's same-reference guard skips the atom write.
    syncAgentsToQueryCache({ "t-1": createMockAgent("t-1") });

    expect(notificationCount).toBe(0);
    unsubscribe();
  });

  it("seeds Jotai from cache state that arrived before the mirror mounted", () => {
    syncAgentsToQueryCache({ "t-1": createMockAgent("t-1") });

    const store = createStore();
    renderMirror(store);

    expect(store.get(agentAtomFamily("t-1"))).toEqual(createMockAgent("t-1"));
    expect(store.get(agentIdsAtom)).toEqual(["t-1"]);
  });

  it("stops projecting after unmount", () => {
    const store = createStore();
    const { unmount } = renderMirror(store);
    syncAgentsToQueryCache({ "t-1": createMockAgent("t-1") });

    unmount();
    syncAgentsToQueryCache({ "t-1": createMockAgent("t-1", { title: "After unmount" }) });

    expect(store.get(agentAtomFamily("t-1"))?.title).toBe("Task t-1");
  });
});
