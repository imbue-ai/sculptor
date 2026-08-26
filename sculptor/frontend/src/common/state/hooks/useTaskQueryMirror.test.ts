import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "../../../api";
import { queryClient, syncTasksToQueryCache, taskQueryKey } from "../../queryClient.ts";
import { taskAtomFamily, taskIdsAtom, tasksArrayAtom } from "../atoms/tasks";
import { useTaskQueryMirror } from "./useTaskQueryMirror";

const createMockTask = (id: string, overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
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
  return renderHook(() => useTaskQueryMirror(), { wrapper });
};

beforeEach(() => {
  queryClient.removeQueries({ queryKey: ["sculptor"] });
});

describe("useTaskQueryMirror", () => {
  it("projects WS frames into the Jotai task atoms", () => {
    const store = createStore();
    renderMirror(store);

    syncTasksToQueryCache({ "t-1": createMockTask("t-1"), "t-2": createMockTask("t-2") });

    expect(store.get(taskAtomFamily("t-1"))).toEqual(createMockTask("t-1"));
    expect(store.get(taskAtomFamily("t-2"))).toEqual(createMockTask("t-2"));
    expect(store.get(taskIdsAtom)).toEqual(["t-1", "t-2"]);
  });

  it("marks the task list as loaded (undefined -> []) on an empty first frame", () => {
    const store = createStore();
    renderMirror(store);
    expect(store.get(tasksArrayAtom)).toBeUndefined();

    // A zero-task instance streams frames whose task-view map is empty; the
    // first frame must still flip the list from "loading" to "loaded, empty".
    syncTasksToQueryCache({});

    expect(store.get(taskIdsAtom)).toEqual([]);
    expect(store.get(tasksArrayAtom)).toEqual([]);
  });

  it("projects tombstones: atom null, id dropped, per-task settings removed", () => {
    const store = createStore();
    renderMirror(store);
    const task = createMockTask("t-1");
    syncTasksToQueryCache({ "t-1": task });
    localStorage.setItem("sculptor-fast-mode-t-1", "true");

    syncTasksToQueryCache({ "t-1": { ...task, isDeleted: true } });

    expect(store.get(taskAtomFamily("t-1"))).toBeNull();
    expect(store.get(taskIdsAtom)).toEqual([]);
    expect(localStorage.getItem("sculptor-fast-mode-t-1")).toBeNull();
  });

  it("projects optimistic mutation writes, not just WS frames", () => {
    const store = createStore();
    renderMirror(store);
    const task = createMockTask("t-1");
    syncTasksToQueryCache({ "t-1": task });

    // A mutation's optimistic update writes the cache directly.
    queryClient.setQueryData(taskQueryKey("t-1"), { ...task, title: "Renamed" });

    expect(store.get(taskAtomFamily("t-1"))?.title).toBe("Renamed");
  });

  it("does not notify Jotai subscribers for a frame that changes nothing", () => {
    const store = createStore();
    renderMirror(store);
    const task = createMockTask("t-1");
    syncTasksToQueryCache({ "t-1": task });

    let notificationCount = 0;
    const unsubscribe = store.sub(taskAtomFamily("t-1"), () => {
      notificationCount += 1;
    });

    // Structural sharing keeps the cached task referentially identical, so
    // the mirror's same-reference guard skips the atom write.
    syncTasksToQueryCache({ "t-1": createMockTask("t-1") });

    expect(notificationCount).toBe(0);
    unsubscribe();
  });

  it("seeds Jotai from cache state that arrived before the mirror mounted", () => {
    syncTasksToQueryCache({ "t-1": createMockTask("t-1") });

    const store = createStore();
    renderMirror(store);

    expect(store.get(taskAtomFamily("t-1"))).toEqual(createMockTask("t-1"));
    expect(store.get(taskIdsAtom)).toEqual(["t-1"]);
  });

  it("stops projecting after unmount", () => {
    const store = createStore();
    const { unmount } = renderMirror(store);
    syncTasksToQueryCache({ "t-1": createMockTask("t-1") });

    unmount();
    syncTasksToQueryCache({ "t-1": createMockTask("t-1", { title: "After unmount" }) });

    expect(store.get(taskAtomFamily("t-1"))?.title).toBe("Task t-1");
  });
});
