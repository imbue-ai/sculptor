// The workspace section/panel keyboard shortcuts: section collapse/cycle/maximize,
// panel cycling, new-agent, and workspace delete. Every handler registers through the
// shared keybindings registry (useKeybindingHandler), so each binding appears on and
// is configurable from the keybindings settings page.
//
// Mounted once by WorkspaceLayoutShell, which only renders on a workspace page, so the
// empty first-run state (no workspaces) never mounts these handlers and their global
// shortcuts are disabled there for free.
//
// new_workspace (Meta+T) and toggle_sidebar are handled by useGlobalKeyboardShortcuts,
// and workspace cycling (next_tab/previous_tab) by useWorkspaceCycleShortcuts — both
// mounted on every sidebar-bearing route (workspace, Home, Settings). Registering any
// of them here too would fire two handlers per press on workspace pages.
//
// Cycling reads live state through the Jotai store at press time to avoid stale
// closures and per-keystroke re-subscription.

import { useSetAtom, useStore } from "jotai";
import { useCallback } from "react";

import { useKeybindingHandler } from "~/common/keybindings/useKeybinding.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { workspaceDeleteTargetAtom } from "~/components/commandPalette/contextActions/atoms/contextActions.ts";
import {
  activePanelIdInSubSectionAtom,
  activeWorkspaceIdAtom,
  panelsInSubSectionAtom,
  workspaceLayoutAtom,
} from "~/pages/workspace/layout/atoms/section.ts";
import {
  jumpToSectionAtom,
  setActivePanelAtom,
  toggleSectionAtom,
} from "~/pages/workspace/layout/atoms/sectionActions.ts";
import { maximizedSectionAtom } from "~/pages/workspace/layout/atoms/transient.ts";
import { panelRegistryAtom } from "~/pages/workspace/layout/registry/panelRegistry.ts";
import type { PanelId } from "~/pages/workspace/layout/types/section.ts";
import { isSecondary, primaryOf, toSection } from "~/pages/workspace/layout/types/section.ts";
import { listSubSections } from "~/pages/workspace/layout/utils/layoutQueries.ts";

import { useAddPanelActions } from "./useAddPanelActions.ts";

type CycleDirection = 1 | -1;

// A missing current (-1) anchors at index 0, so the step lands on the neighbour of the
// first element (forward → second, backward → last).
const stepIndex = (length: number, current: number, direction: CycleDirection): number => {
  const base = current === -1 ? 0 : current;
  return (base + direction + length) % length;
};

// The next panel to activate when cycling within a sub-section. Cycles only over panels
// that currently RENDER — i.e. have a registry definition. An open panel without one
// (an agent whose task is mid-load or was just deleted) shows as the empty-section
// state, so including it would let a cycle land on "nothing selected" between two real
// panels. Returns undefined (a no-op) for an empty or single renderable-panel section.
export const nextCyclablePanel = (
  openPanels: ReadonlyArray<PanelId>,
  renderablePanelIds: ReadonlySet<PanelId>,
  active: PanelId | undefined,
  direction: CycleDirection,
): PanelId | undefined => {
  const panels = openPanels.filter((panelId) => renderablePanelIds.has(panelId));
  if (panels.length < 2) {
    return undefined;
  }
  const currentIndex = active === undefined ? -1 : panels.indexOf(active);
  return panels[stepIndex(panels.length, currentIndex, direction)];
};

export const useWorkspaceShortcuts = (): void => {
  const store = useStore();
  const toggleSection = useSetAtom(toggleSectionAtom);
  const jumpToSection = useSetAtom(jumpToSectionAtom);
  const setActivePanel = useSetAtom(setActivePanelAtom);
  const setMaximizedSection = useSetAtom(maximizedSectionAtom);
  const setWorkspaceDeleteTarget = useSetAtom(workspaceDeleteTargetAtom);
  const { createRecentAgent } = useAddPanelActions();

  // Cycle the active section through the expanded sub-sections incl. split halves,
  // pulsing the ring on each step. While a section is maximized only one section is on
  // screen, so the cycle moves the maximize (and the active section) across the
  // expanded sections' primaries instead — keeping every step visible rather than
  // stepping the ring, and later panel cycling, through hidden sections.
  const cycleSection = useCallback(
    (direction: CycleDirection): void => {
      const layout = store.get(workspaceLayoutAtom);
      if (store.get(maximizedSectionAtom) !== null) {
        // A split section's hidden half is never shown while maximized, so only
        // primaries participate in the maximized cycle.
        const primaries = listSubSections(layout, { includeCollapsed: false }).filter((sub) => !isSecondary(sub));
        if (primaries.length === 0) {
          return;
        }
        const currentSection = toSection(layout.activeSubSection ?? "center");
        const next = primaries[stepIndex(primaries.length, primaries.indexOf(currentSection), direction)];
        setMaximizedSection(toSection(next));
        jumpToSection({ subSection: next });
        return;
      }
      // The active-able sub-sections: the section-cycle only steps through expanded
      // sections (and their split halves) — a collapsed section cannot be active.
      const order = listSubSections(layout, { includeCollapsed: false });
      if (order.length === 0) {
        return;
      }
      const current = layout.activeSubSection ?? "center";
      const next = order[stepIndex(order.length, order.indexOf(current), direction)];
      jumpToSection({ subSection: next });
    },
    [store, jumpToSection, setMaximizedSection],
  );

  // Cycle the active panel within the active sub-section; wraps at the ends, skips
  // panels that have no renderable definition, and is a no-op for an empty or
  // single-renderable-panel section.
  const cyclePanel = useCallback(
    (direction: CycleDirection): void => {
      const layout = store.get(workspaceLayoutAtom);
      // While maximized only the maximized section's primary is on screen; cycle the
      // panels the user can actually see rather than a (possibly hidden) active
      // sub-section.
      const maximized = store.get(maximizedSectionAtom);
      const activeSub = maximized !== null ? primaryOf(maximized) : (layout.activeSubSection ?? "center");
      const openPanels = store.get(panelsInSubSectionAtom(activeSub));
      const renderablePanelIds = new Set(store.get(panelRegistryAtom).map((definition) => definition.id));
      const active = store.get(activePanelIdInSubSectionAtom(activeSub));
      const next = nextCyclablePanel(openPanels, renderablePanelIds, active, direction);
      if (next !== undefined) {
        setActivePanel({ panelId: next, in: activeSub });
      }
    },
    [store, setActivePanel],
  );

  // Maximize the active section, or restore if one is already maximized.
  const toggleMaximize = useCallback((): void => {
    if (store.get(maximizedSectionAtom) !== null) {
      setMaximizedSection(null);
      return;
    }
    const layout = store.get(workspaceLayoutAtom);
    setMaximizedSection(toSection(layout.activeSubSection ?? "center"));
  }, [store, setMaximizedSection]);

  // Open the delete-confirmation dialog for the current workspace (the same dialog
  // the palette's workspace Delete action drives, via workspaceDeleteTargetAtom).
  // The destructive delete itself only runs once the user confirms there.
  const beginDeleteWorkspace = useCallback((): void => {
    const workspaceId = store.get(activeWorkspaceIdAtom);
    if (workspaceId === null) {
      return;
    }
    const workspace = (store.get(workspacesArrayAtom) ?? []).find((candidate) => candidate.objectId === workspaceId);
    if (workspace === undefined) {
      return;
    }
    setWorkspaceDeleteTarget({ id: workspace.objectId, name: workspace.description ?? "" });
  }, [store, setWorkspaceDeleteTarget]);

  // Center never collapses: toggleSectionAtom ignores it, so the binding is
  // simply a no-op there.
  useKeybindingHandler(
    "toggle_left_panel",
    useCallback(() => toggleSection({ section: "left" }), [toggleSection]),
  );
  useKeybindingHandler(
    "toggle_right_panel",
    useCallback(() => toggleSection({ section: "right" }), [toggleSection]),
  );
  useKeybindingHandler(
    "toggle_bottom_panel",
    useCallback(() => toggleSection({ section: "bottom" }), [toggleSection]),
  );
  useKeybindingHandler("maximize_section", toggleMaximize);
  useKeybindingHandler(
    "next_section",
    useCallback(() => cycleSection(1), [cycleSection]),
  );
  useKeybindingHandler(
    "previous_section",
    useCallback(() => cycleSection(-1), [cycleSection]),
  );
  useKeybindingHandler(
    "next_panel",
    useCallback(() => cyclePanel(1), [cyclePanel]),
  );
  useKeybindingHandler(
    "previous_panel",
    useCallback(() => cyclePanel(-1), [cyclePanel]),
  );
  // New agent always lands in center regardless of the active section.
  useKeybindingHandler("new_agent", createRecentAgent);
  useKeybindingHandler("delete_workspace", beginDeleteWorkspace);
};
