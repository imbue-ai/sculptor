import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "~/api";
import type { WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/components/sections/persistence/types.ts";
import { makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";

import {
  activateAgentPanelAtom,
  ensureAgentPanelsPlacedAtom,
  workspaceAgentIdsAtomFamily,
  workspaceAgentIdsWhenLoadedAtomFamily,
} from "./agentPanelPlacement.ts";
import { taskAtomFamily, taskIdsAtom } from "./atoms/tasks.ts";

function storeWith(layout: Partial<WorkspaceLayoutState>, workspaceId = "ws-test"): ReturnType<typeof createStore> {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, workspaceId);
  store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT, ...layout });
  return store;
}

beforeEach(() => {
  localStorage.clear();
});

describe("ensureAgentPanelsPlacedAtom", () => {
  it("places a never-seen agent in the center section", () => {
    const store = storeWith({});
    store.set(ensureAgentPanelsPlacedAtom, ["1"]);

    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement[makeAgentPanelId("1")]).toBe("center");
    expect(layout.order.center).toEqual([makeAgentPanelId("1")]);
  });

  it("appends only the missing agents, preserving existing center order", () => {
    const a1 = makeAgentPanelId("1");
    const a2 = makeAgentPanelId("2");
    const store = storeWith({ placement: { [a1]: "center" }, order: { center: [a1] } });

    store.set(ensureAgentPanelsPlacedAtom, ["1", "2"]);

    const layout = store.get(workspaceLayoutAtom);
    expect(layout.order.center).toEqual([a1, a2]);
    expect(layout.placement[a2]).toBe("center");
  });

  it("is a no-op when every agent is already placed (avoids persist churn)", () => {
    const a1 = makeAgentPanelId("1");
    const store = storeWith({ placement: { [a1]: "center" }, order: { center: [a1] } });
    const before = store.get(workspaceLayoutAtom);

    store.set(ensureAgentPanelsPlacedAtom, ["1"]);

    expect(store.get(workspaceLayoutAtom)).toBe(before);
  });

  it("does not move an agent already placed in another section", () => {
    const a1 = makeAgentPanelId("1");
    const store = storeWith({ placement: { [a1]: "right" }, order: { right: [a1] }, expanded: { right: true } });

    store.set(ensureAgentPanelsPlacedAtom, ["1"]);

    expect(store.get(workspaceLayoutAtom).placement[a1]).toBe("right");
    expect(store.get(workspaceLayoutAtom).order.center ?? []).toEqual([]);
  });

  it("is purely additive: keeps the active panel and active sub-section (no focus steal)", () => {
    const a1 = makeAgentPanelId("1");
    const a2 = makeAgentPanelId("2");
    const store = storeWith({
      placement: { [a1]: "center" },
      order: { center: [a1] },
      activePanel: { center: a1 },
      activeSubSection: "center",
    });

    // A background agent (a2) appears — it should become a tab but must not steal focus.
    store.set(ensureAgentPanelsPlacedAtom, ["1", "2"]);

    const layout = store.get(workspaceLayoutAtom);
    // a2 is surfaced as a new tab...
    expect(layout.order.center).toEqual([a1, a2]);
    // ...but focus stays on the agent the user was already viewing.
    expect(layout.activePanel.center).toBe(a1);
    expect(layout.activeSubSection).toBe("center");
  });

  it("is idempotent: a double run (or an every-tick run) cannot duplicate order entries", () => {
    const a1 = makeAgentPanelId("1");
    const a2 = makeAgentPanelId("2");
    const store = storeWith({});

    store.set(ensureAgentPanelsPlacedAtom, ["1", "2"]);
    const afterFirstRun = store.get(workspaceLayoutAtom);
    store.set(ensureAgentPanelsPlacedAtom, ["1", "2"]);

    expect(store.get(workspaceLayoutAtom)).toBe(afterFirstRun);
    expect(afterFirstRun.order.center).toEqual([a1, a2]);
  });

  it("places an agent task id given twice exactly once", () => {
    const a1 = makeAgentPanelId("1");
    const store = storeWith({});

    store.set(ensureAgentPanelsPlacedAtom, ["1", "1"]);

    expect(store.get(workspaceLayoutAtom).order.center).toEqual([a1]);
  });

  it("does not duplicate a stale order entry left behind for an unplaced panel", () => {
    // An order entry can survive without a matching placement (an inconsistent
    // persisted snapshot); re-placing that agent must yield exactly one tab.
    const a1 = makeAgentPanelId("1");
    const store = storeWith({ placement: {}, order: { center: [a1] } });

    store.set(ensureAgentPanelsPlacedAtom, ["1"]);

    const layout = store.get(workspaceLayoutAtom);
    expect(layout.order.center).toEqual([a1]);
    expect(layout.placement[a1]).toBe("center");
  });

  it("collapses duplicate order entries already persisted for a placed panel", () => {
    const a1 = makeAgentPanelId("1");
    const a2 = makeAgentPanelId("2");
    const store = storeWith({
      placement: { [a1]: "center", [a2]: "center" },
      order: { center: [a1, a2, a1] },
    });

    store.set(ensureAgentPanelsPlacedAtom, ["1", "2"]);

    expect(store.get(workspaceLayoutAtom).order.center).toEqual([a1, a2]);
  });

  it("does not prune a placed agent panel whose task id is no longer listed", () => {
    // Deleting an agent removes its panel through the agent close/delete flow;
    // the reconcile only ever adds.
    const ghost = makeAgentPanelId("ghost");
    const a1 = makeAgentPanelId("1");
    const store = storeWith({ placement: { [ghost]: "center" }, order: { center: [ghost] } });

    store.set(ensureAgentPanelsPlacedAtom, ["1"]);

    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement[ghost]).toBe("center");
    expect(layout.order.center).toEqual([ghost, a1]);
  });

  it("appends to the center primary when the center is split, leaving the secondary alone", () => {
    const a1 = makeAgentPanelId("1");
    const a2 = makeAgentPanelId("2");
    const store = storeWith({
      placement: { [a1]: "center:secondary" },
      order: { "center:secondary": [a1] },
      splits: { center: { axis: "vertical", ratio: 0.5 } },
    });

    store.set(ensureAgentPanelsPlacedAtom, ["1", "2"]);

    const layout = store.get(workspaceLayoutAtom);
    // a1 already lives in the split half and stays there; only a2 is placed.
    expect(layout.placement[a1]).toBe("center:secondary");
    expect(layout.order["center:secondary"]).toEqual([a1]);
    expect(layout.order.center).toEqual([a2]);
    expect(layout.placement[a2]).toBe("center");
    expect(layout.splits.center).toEqual({ axis: "vertical", ratio: 0.5 });
  });
});

describe("workspaceAgentIdsAtomFamily", () => {
  const taskFor = (
    id: string,
    workspaceId: string,
    overrides: Partial<CodingAgentTaskView> = {},
  ): CodingAgentTaskView => ({ id, workspaceId, isDeleted: false, ...overrides }) as CodingAgentTaskView;

  it("lists only the workspace's task ids", () => {
    const store = createStore();
    store.set(taskIdsAtom, ["t1", "t2", "t3"]);
    store.set(taskAtomFamily("t1"), taskFor("t1", "ws-a"));
    store.set(taskAtomFamily("t2"), taskFor("t2", "ws-b"));
    store.set(taskAtomFamily("t3"), taskFor("t3", "ws-a"));

    expect(store.get(workspaceAgentIdsAtomFamily("ws-a"))).toEqual(["t1", "t3"]);
    expect(store.get(workspaceAgentIdsAtomFamily("ws-b"))).toEqual(["t2"]);
  });

  it("is reference-stable across a task tick that does not change the id list", () => {
    // tasksArrayAtom rebuilds its array on every per-task write; the slice must
    // swallow that so the bootstrap does not re-render per streaming tick.
    const store = createStore();
    store.set(taskIdsAtom, ["t1"]);
    store.set(taskAtomFamily("t1"), taskFor("t1", "ws-a"));

    const first = store.get(workspaceAgentIdsAtomFamily("ws-a"));
    store.set(taskAtomFamily("t1"), taskFor("t1", "ws-a", { title: "tick" }));

    expect(store.get(workspaceAgentIdsAtomFamily("ws-a"))).toBe(first);
  });
});

describe("workspaceAgentIdsWhenLoadedAtomFamily", () => {
  const taskFor = (
    id: string,
    workspaceId: string,
    overrides: Partial<CodingAgentTaskView> = {},
  ): CodingAgentTaskView => ({ id, workspaceId, isDeleted: false, ...overrides }) as CodingAgentTaskView;

  it("is undefined until the first task snapshot arrives", () => {
    const store = createStore();
    expect(store.get(workspaceAgentIdsWhenLoadedAtomFamily("ws-a"))).toBeUndefined();
  });

  it("lists the workspace's ids — and [] for an agentless workspace — once loaded", () => {
    const store = createStore();
    store.set(taskIdsAtom, ["t1", "t2"]);
    store.set(taskAtomFamily("t1"), taskFor("t1", "ws-a"));
    store.set(taskAtomFamily("t2"), taskFor("t2", "ws-b"));

    expect(store.get(workspaceAgentIdsWhenLoadedAtomFamily("ws-a"))).toEqual(["t1"]);
    expect(store.get(workspaceAgentIdsWhenLoadedAtomFamily("ws-agentless"))).toEqual([]);
  });

  it("is reference-stable across a task tick that does not change the id list", () => {
    const store = createStore();
    store.set(taskIdsAtom, ["t1"]);
    store.set(taskAtomFamily("t1"), taskFor("t1", "ws-a"));

    const first = store.get(workspaceAgentIdsWhenLoadedAtomFamily("ws-a"));
    store.set(taskAtomFamily("t1"), taskFor("t1", "ws-a", { title: "tick" }));

    expect(store.get(workspaceAgentIdsWhenLoadedAtomFamily("ws-a"))).toBe(first);
  });
});

describe("activateAgentPanelAtom", () => {
  it("opens a never-placed agent in the center and makes it active", () => {
    const a1 = makeAgentPanelId("1");
    const store = storeWith({});

    store.set(activateAgentPanelAtom, "1");

    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement[a1]).toBe("center");
    expect(layout.order.center).toEqual([a1]);
    expect(layout.activePanel.center).toBe(a1);
  });

  it("activates an already-placed agent in place instead of pulling it into center", () => {
    const a1 = makeAgentPanelId("1");
    const other = "files";
    const store = storeWith({
      placement: { [a1]: "right", [other]: "right" },
      order: { right: [other, a1] },
      activePanel: { right: other },
      expanded: { right: true },
    });

    store.set(activateAgentPanelAtom, "1");

    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement[a1]).toBe("right");
    expect(layout.order.right).toEqual([other, a1]);
    expect(layout.activePanel.right).toBe(a1);
    expect(layout.order.center ?? []).toEqual([]);
  });

  it("re-activating the same placed agent never duplicates its tab", () => {
    const a1 = makeAgentPanelId("1");
    const store = storeWith({
      placement: { [a1]: "center" },
      order: { center: [a1] },
      activePanel: { center: a1 },
    });

    store.set(activateAgentPanelAtom, "1");
    store.set(activateAgentPanelAtom, "1");

    expect(store.get(workspaceLayoutAtom).order.center).toEqual([a1]);
  });

  it("does not move the active sub-section (tab focus follows navigation, not panes)", () => {
    const a1 = makeAgentPanelId("1");
    const store = storeWith({
      placement: { [a1]: "right" },
      order: { right: [a1] },
      expanded: { right: true },
      activeSubSection: "bottom",
    });

    store.set(activateAgentPanelAtom, "1");

    expect(store.get(workspaceLayoutAtom).activeSubSection).toBe("bottom");
  });
});
