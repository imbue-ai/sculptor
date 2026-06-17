import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "~/api";
import { taskAtomFamily, taskIdsAtom } from "~/common/state/atoms/tasks.ts";
import { terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { zoneAssignmentsAtom } from "~/components/panels/atoms.ts";
import { hasPendingSplitPanelAtom } from "~/pages/workspace/panels/panelDerivedAtoms.ts";

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

const makeTask = (id: string): CodingAgentTaskView => ({ id }) as unknown as CodingAgentTaskView;

describe("hasPendingSplitPanelAtom", () => {
  it("is false when nothing is assigned to the split half", () => {
    const store = createStore();
    store.set(zoneAssignmentsAtom, { "agent:t1": "center" });
    expect(store.get(hasPendingSplitPanelAtom("center"))).toBe(false);
  });

  it("is true while the task list has not loaded yet", () => {
    const store = createStore();
    store.set(zoneAssignmentsAtom, { "agent:t1": "center:split" });
    // taskIdsAtom defaults to undefined → sources still loading.
    expect(store.get(hasPendingSplitPanelAtom("center"))).toBe(true);
  });

  it("is true when the assigned agent's task exists", () => {
    const store = createStore();
    store.set(zoneAssignmentsAtom, { "agent:t1": "center:split" });
    store.set(taskIdsAtom, ["t1"]);
    store.set(taskAtomFamily("t1"), makeTask("t1"));
    expect(store.get(hasPendingSplitPanelAtom("center"))).toBe(true);
  });

  it("is false when the assigned agent's task is gone (deleted agent)", () => {
    const store = createStore();
    store.set(zoneAssignmentsAtom, { "agent:t1": "center:split" });
    store.set(taskIdsAtom, []);
    expect(store.get(hasPendingSplitPanelAtom("center"))).toBe(false);
  });

  it("is true for the default terminal (index 0) even with no stored terminal tabs", () => {
    const store = createStore();
    store.set(zoneAssignmentsAtom, { "terminal:ws1:0": "center:split" });
    store.set(taskIdsAtom, []);
    expect(store.get(hasPendingSplitPanelAtom("center"))).toBe(true);
  });

  it("tracks a non-default terminal's existence in the terminal tab state", () => {
    const store = createStore();
    store.set(zoneAssignmentsAtom, { "terminal:ws1:5": "center:split" });
    store.set(taskIdsAtom, []);
    expect(store.get(hasPendingSplitPanelAtom("center"))).toBe(false);
    store.set(terminalTabStateAtom, { ws1: [{ id: "terminal-5", index: 5, label: "Terminal 6" }] });
    expect(store.get(hasPendingSplitPanelAtom("center"))).toBe(true);
  });

  it("does not notify on task-list churn while the answer is unchanged", () => {
    const store = createStore();
    store.set(zoneAssignmentsAtom, { "agent:t1": "center:split" });
    store.set(taskIdsAtom, ["t1"]);
    store.set(taskAtomFamily("t1"), makeTask("t1"));
    let notifications = 0;
    store.sub(hasPendingSplitPanelAtom("center"), () => {
      notifications += 1;
    });
    // Streaming task updates: new ids array, new task object — same answer.
    store.set(taskIdsAtom, ["t1", "t2"]);
    store.set(taskAtomFamily("t2"), makeTask("t2"));
    store.set(taskAtomFamily("t1"), makeTask("t1"));
    expect(notifications).toBe(0);
  });
});
