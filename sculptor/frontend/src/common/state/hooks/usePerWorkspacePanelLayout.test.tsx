import { act, renderHook } from "@testing-library/react";
import type { createStore } from "jotai";
import { Provider } from "jotai";
import { Circle } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  activeWorkspaceIdAtom,
  createPanelStore,
  zoneSizesAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import type { PanelDefinition } from "~/components/panels/types.ts";
import { diffPanelOpenAtom, diffPanelSplitRatioAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";

import type { UserConfig } from "../../../api";
import { userConfigAtom } from "../atoms/userConfig.ts";
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
    id: "terminal",
    displayName: "Terminal",
    description: "Test panel",
    icon: Circle,
    defaultZone: "bottom",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
  {
    id: "changes",
    displayName: "Changes",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
];

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

// ── Helpers ──────────────────────────────────────────────────────────

const createDefaultStore = (): ReturnType<typeof createStore> =>
  createPanelStore(TEST_PANELS, { useDefaultLayout: true });

const enablePerWorkspace = (store: ReturnType<typeof createStore>): void => {
  store.set(userConfigAtom, { isPanelLayoutPerWorkspace: true } as unknown as UserConfig);
};

const disablePerWorkspace = (store: ReturnType<typeof createStore>): void => {
  store.set(userConfigAtom, { isPanelLayoutPerWorkspace: false } as unknown as UserConfig);
};

const renderPerWorkspaceHook = (
  workspaceId: string,
  store: ReturnType<typeof createStore>,
): ReturnType<typeof renderHook<void, { workspaceId: string }>> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  return renderHook(({ workspaceId: wsId }) => usePerWorkspacePanelLayout(wsId), {
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
      expect(store.get(activeWorkspaceIdAtom)).toBe("ws-1");

      rerender({ workspaceId: "ws-2" });
      expect(store.get(activeWorkspaceIdAtom)).toBe("ws-2");
    });
  });

  describe("when per-workspace is disabled", () => {
    it("does not save or restore visibility on workspace switch", () => {
      const store = createDefaultStore();
      // Set specific visibility for ws-1
      store.set(zoneVisibilityAtom, { "top-left": true, bottom: false, "top-right": true });

      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      // Switch to ws-2
      rerender({ workspaceId: "ws-2" });

      // Visibility should remain unchanged (not restored from storage)
      const vis = store.get(zoneVisibilityAtom);
      expect(vis["top-left"]).toBe(true);
      expect(vis["bottom"]).toBe(false);
      expect(vis["top-right"]).toBe(true);
    });
  });

  describe("when per-workspace is enabled", () => {
    it("preserves visibility independently per workspace when switching", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      // Start on ws-1, set its visibility
      store.set(zoneVisibilityAtom, { "top-left": true, bottom: true, "top-right": false });
      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      // Modify visibility while on ws-1 (triggers persist effect)
      act(() => {
        store.set(zoneVisibilityAtom, { "top-left": true, bottom: true, "top-right": false });
      });

      // Switch to ws-2 — no saved state, so visibility stays as-is
      rerender({ workspaceId: "ws-2" });

      // Change visibility on ws-2
      act(() => {
        store.set(zoneVisibilityAtom, { "top-left": false, bottom: false, "top-right": true });
      });

      // Switch back to ws-1 — should restore ws-1's saved visibility
      rerender({ workspaceId: "ws-1" });

      const vis = store.get(zoneVisibilityAtom);
      expect(vis["top-left"]).toBe(true);
      expect(vis["bottom"]).toBe(true);
      expect(vis["top-right"]).toBe(false);
    });

    it("preserves sizes independently per workspace when switching", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      // Start on ws-1 with specific sizes
      store.set(zoneSizesAtom, { "top-left": 30, bottom: 25 });
      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      // Trigger persist
      act(() => {
        store.set(zoneSizesAtom, { "top-left": 30, bottom: 25 });
      });

      // Switch to ws-2
      rerender({ workspaceId: "ws-2" });

      // Change sizes on ws-2
      act(() => {
        store.set(zoneSizesAtom, { "top-left": 50, bottom: 40 });
      });

      // Switch back to ws-1 — should restore ws-1's sizes
      rerender({ workspaceId: "ws-1" });

      const sizes = store.get(zoneSizesAtom);
      expect(sizes["top-left"]).toBe(30);
      expect(sizes["bottom"]).toBe(25);
    });

    it("loads saved state on initial mount if available", () => {
      // Pre-populate localStorage with saved state for ws-1
      localStorage.setItem(
        "sculptor-zone-visibility-ws-ws-1",
        JSON.stringify({ "top-left": false, bottom: true, "top-right": true }),
      );
      localStorage.setItem("sculptor-zone-sizes-ws-ws-1", JSON.stringify({ "top-left": 15, bottom: 35 }));

      const store = createDefaultStore();
      enablePerWorkspace(store);

      renderPerWorkspaceHook("ws-1", store);

      const vis = store.get(zoneVisibilityAtom);
      expect(vis["top-left"]).toBe(false);
      expect(vis["bottom"]).toBe(true);

      const sizes = store.get(zoneSizesAtom);
      expect(sizes["top-left"]).toBe(15);
      expect(sizes["bottom"]).toBe(35);
    });

    it("does not overwrite atoms on initial mount when no saved state exists", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      // Set up some initial visibility
      store.set(zoneVisibilityAtom, { "top-left": true, bottom: true, "top-right": true });
      store.set(zoneSizesAtom, { "top-left": 20 });

      renderPerWorkspaceHook("ws-new", store);

      // Should keep the existing values since there's no saved state for ws-new
      const vis = store.get(zoneVisibilityAtom);
      expect(vis["top-left"]).toBe(true);
      expect(vis["bottom"]).toBe(true);

      const sizes = store.get(zoneSizesAtom);
      expect(sizes["top-left"]).toBe(20);
    });

    it("persists visibility changes to workspace-scoped localStorage", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(zoneVisibilityAtom, { "top-left": true, bottom: false, "top-right": true });
      });

      const stored = localStorage.getItem("sculptor-zone-visibility-ws-ws-1");
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored!)).toEqual({ "top-left": true, bottom: false, "top-right": true });
    });

    it("persists size changes to workspace-scoped localStorage", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(zoneSizesAtom, { "top-left": 42, bottom: 33 });
      });

      const stored = localStorage.getItem("sculptor-zone-sizes-ws-ws-1");
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored!)).toEqual({ "top-left": 42, bottom: 33 });
    });

    it("preserves diff panel open state independently per workspace when switching", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      store.set(diffPanelOpenAtom, true);
      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      // Trigger persist for ws-1's "true"
      act(() => {
        store.set(diffPanelOpenAtom, true);
      });

      rerender({ workspaceId: "ws-2" });

      // Close on ws-2
      act(() => {
        store.set(diffPanelOpenAtom, false);
      });

      // Switching back to ws-1 should restore its saved "true"
      rerender({ workspaceId: "ws-1" });
      expect(store.get(diffPanelOpenAtom)).toBe(true);
    });

    it("preserves diff panel split ratio independently per workspace when switching", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      store.set(diffPanelSplitRatioAtom, 70);
      const { rerender } = renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(diffPanelSplitRatioAtom, 70);
      });

      rerender({ workspaceId: "ws-2" });

      act(() => {
        store.set(diffPanelSplitRatioAtom, 30);
      });

      rerender({ workspaceId: "ws-1" });
      expect(store.get(diffPanelSplitRatioAtom)).toBe(70);
    });

    it("loads saved diff panel state on initial mount if available", () => {
      localStorage.setItem("sculptor-diffPanel-open-ws-ws-1", JSON.stringify(true));
      localStorage.setItem("sculptor-diffPanel-splitRatio-ws-ws-1", JSON.stringify(65));

      const store = createDefaultStore();
      enablePerWorkspace(store);

      renderPerWorkspaceHook("ws-1", store);

      expect(store.get(diffPanelOpenAtom)).toBe(true);
      expect(store.get(diffPanelSplitRatioAtom)).toBe(65);
    });

    it("persists diff panel open changes to workspace-scoped localStorage", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(diffPanelOpenAtom, true);
      });

      const stored = localStorage.getItem("sculptor-diffPanel-open-ws-ws-1");
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored!)).toBe(true);
    });

    it("persists diff panel split ratio changes to workspace-scoped localStorage", () => {
      const store = createDefaultStore();
      enablePerWorkspace(store);

      renderPerWorkspaceHook("ws-1", store);

      act(() => {
        store.set(diffPanelSplitRatioAtom, 42);
      });

      const stored = localStorage.getItem("sculptor-diffPanel-splitRatio-ws-ws-1");
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored!)).toBe(42);
    });
  });

  describe("toggling per-workspace mode", () => {
    it("starts saving per-workspace when enabled after being disabled", () => {
      const store = createDefaultStore();
      // Start disabled
      disablePerWorkspace(store);

      const { rerender: rerenderHook } = renderPerWorkspaceHook("ws-1", store);

      // Enable per-workspace mode
      act(() => {
        enablePerWorkspace(store);
      });

      // Re-render to pick up the config change
      rerenderHook({ workspaceId: "ws-1" });

      // Now change visibility — should persist to workspace-scoped key
      act(() => {
        store.set(zoneVisibilityAtom, { "top-left": false, bottom: true });
      });

      const stored = localStorage.getItem("sculptor-zone-visibility-ws-ws-1");
      expect(stored).not.toBeNull();
    });
  });
});
