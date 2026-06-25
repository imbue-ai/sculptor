import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/components/sections/persistence/types.ts";
import { makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";

import { ensureAgentPanelsPlacedAtom } from "./agentPanelPlacement.ts";

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
});
