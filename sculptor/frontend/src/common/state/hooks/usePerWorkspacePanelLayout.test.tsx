import { act, renderHook } from "@testing-library/react";
import type { createStore } from "jotai";
import { Provider } from "jotai";
import { Circle } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  activePanelPerZoneAtom,
  activeWorkspaceIdAtom,
  createPanelStore,
  zoneAssignmentsAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import {
  sectionSizePercentAtom,
  sectionSizesSharedAtom,
  sectionSplitAtom,
} from "~/components/panels/sectionLayoutAtoms.ts";
import type { DefaultPanelLayout, PanelDefinition } from "~/components/panels/types.ts";

import { usePerWorkspacePanelLayout } from "./usePerWorkspacePanelLayout.ts";

// ── Test fixtures ────────────────────────────────────────────────────

const TEST_PANELS: ReadonlyArray<PanelDefinition> = [
  {
    id: "files",
    displayName: "Files",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
  {
    id: "changes",
    displayName: "Changes",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
];

const TEST_DEFAULT_LAYOUT: DefaultPanelLayout = {
  zoneAssignments: { files: "top-left", changes: "top-left" },
  activePanelPerZone: { "top-left": "files" },
  zoneVisibility: { "top-left": true, center: true, "top-right": false, bottom: false },
  zoneOrder: { "top-left": ["files", "changes"] },
};

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

// ── Helpers ──────────────────────────────────────────────────────────

const createDefaultStore = (): ReturnType<typeof createStore> => createPanelStore(TEST_PANELS);

const renderPerWorkspaceHook = (
  workspaceId: string,
  store: ReturnType<typeof createStore>,
): ReturnType<typeof renderHook<void, { workspaceId: string }>> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  return renderHook(({ workspaceId: wsId }) => usePerWorkspacePanelLayout(wsId, TEST_DEFAULT_LAYOUT), {
    wrapper,
    initialProps: { workspaceId },
  });
};

// ── Tests ────────────────────────────────────────────────────────────

describe("usePerWorkspacePanelLayout", () => {
  describe("activeWorkspaceIdAtom tracking", () => {
    it("sets activeWorkspaceIdAtom on mount", () => {
      const store = createDefaultStore();
      renderPerWorkspaceHook("ws-1", store);
      expect(store.get(activeWorkspaceIdAtom)).toBe("ws-1");
    });

    it("clears activeWorkspaceIdAtom on unmount", () => {
      const store = createDefaultStore();
      const { unmount } = renderPerWorkspaceHook("ws-1", store);
      unmount();
      expect(store.get(activeWorkspaceIdAtom)).toBeNull();
    });

    it("updates activeWorkspaceIdAtom when workspace changes", () => {
      const store = createDefaultStore();
      const { rerender } = renderPerWorkspaceHook("ws-1", store);
      rerender({ workspaceId: "ws-2" });
      expect(store.get(activeWorkspaceIdAtom)).toBe("ws-2");
    });
  });

  describe("first visit (no saved layout) falls back to the default layout", () => {
    it("resets layout atoms to the default on initial mount", () => {
      const store = createDefaultStore();
      // Seed some stale, non-default layout to prove it gets reset.
      store.set(zoneAssignmentsAtom, { stale: "center" });
      store.set(sectionSplitAtom, { center: { axis: "vertical", ratio: 0.5 } });

      renderPerWorkspaceHook("ws-1", store);

      expect(store.get(zoneAssignmentsAtom)).toEqual(TEST_DEFAULT_LAYOUT.zoneAssignments);
      expect(store.get(activePanelPerZoneAtom)).toEqual(TEST_DEFAULT_LAYOUT.activePanelPerZone);
      expect(store.get(sectionSplitAtom)).toEqual({});
    });

    it("resets to default when switching to a never-visited workspace (no leak)", () => {
      const store = createDefaultStore();
      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      // Make ws-1 layout distinctive.
      act(() => {
        store.set(zoneAssignmentsAtom, { files: "top-right" });
        store.set(sectionSplitAtom, { "top-right": { axis: "vertical", ratio: 0.5 } });
      });

      // Switch to an unvisited workspace — must reset to default, not leak ws-1.
      rerender({ workspaceId: "ws-2" });

      expect(store.get(zoneAssignmentsAtom)).toEqual(TEST_DEFAULT_LAYOUT.zoneAssignments);
      expect(store.get(sectionSplitAtom)).toEqual({});
    });
  });

  describe("restore on mount / switch", () => {
    it("restores a saved layout (assignments + split) on initial mount", () => {
      localStorage.setItem("sculptor-zone-assignments-ws-ws-1", JSON.stringify({ "agent:a": "center" }));
      localStorage.setItem(
        "sculptor-section-split-ws-ws-1",
        JSON.stringify({ center: { axis: "horizontal", ratio: 0.4 } }),
      );
      localStorage.setItem("sculptor-zone-visibility-ws-ws-1", JSON.stringify({ center: true }));

      const store = createDefaultStore();
      renderPerWorkspaceHook("ws-1", store);

      expect(store.get(zoneAssignmentsAtom)).toEqual({ "agent:a": "center" });
      expect(store.get(sectionSplitAtom)).toEqual({ center: { axis: "horizontal", ratio: 0.4 } });
      expect(store.get(zoneVisibilityAtom)).toEqual({ center: true });
    });

    it("saves the outgoing workspace and restores it when switching back", () => {
      const store = createDefaultStore();
      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      // Customize ws-1.
      act(() => {
        store.set(zoneAssignmentsAtom, { files: "top-left", "agent:a": "center" });
        store.set(sectionSplitAtom, { center: { axis: "vertical", ratio: 0.6 } });
      });

      // Switch away (ws-2 resets to default) then back to ws-1.
      rerender({ workspaceId: "ws-2" });
      act(() => {
        store.set(zoneAssignmentsAtom, { changes: "top-right" });
      });
      rerender({ workspaceId: "ws-1" });

      expect(store.get(zoneAssignmentsAtom)).toEqual({ files: "top-left", "agent:a": "center" });
      expect(store.get(sectionSplitAtom)).toEqual({ center: { axis: "vertical", ratio: 0.6 } });
    });
  });

  describe("persistence to workspace-scoped keys", () => {
    it("persists assignment and split changes to per-workspace localStorage", () => {
      const store = createDefaultStore();
      renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(zoneAssignmentsAtom, { "agent:a": "center" });
        store.set(sectionSplitAtom, { center: { axis: "horizontal", ratio: 0.3 } });
      });

      expect(JSON.parse(localStorage.getItem("sculptor-zone-assignments-ws-ws-1")!)).toEqual({ "agent:a": "center" });
      expect(JSON.parse(localStorage.getItem("sculptor-section-split-ws-ws-1")!)).toEqual({
        center: { axis: "horizontal", ratio: 0.3 },
      });
    });
  });

  describe("section sizes shared vs unique", () => {
    it("does NOT write a per-workspace size key when sizes are shared (default)", () => {
      const store = createDefaultStore();
      store.set(sectionSizesSharedAtom, true);
      renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(sectionSizePercentAtom, { left: 33 });
      });

      expect(localStorage.getItem("sculptor-section-size-percent-ws-ws-1")).toBeNull();
    });

    it("persists and restores section sizes per workspace when sizes are unique", () => {
      const store = createDefaultStore();
      store.set(sectionSizesSharedAtom, false);
      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(sectionSizePercentAtom, { left: 33 });
      });
      expect(JSON.parse(localStorage.getItem("sculptor-section-size-percent-ws-ws-1")!)).toEqual({ left: 33 });

      rerender({ workspaceId: "ws-2" });
      act(() => {
        store.set(sectionSizePercentAtom, { left: 50 });
      });
      rerender({ workspaceId: "ws-1" });
      expect(store.get(sectionSizePercentAtom)).toEqual({ left: 33 });
    });
  });
});
