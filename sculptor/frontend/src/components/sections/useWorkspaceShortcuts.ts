// The new-shell workspace keyboard shortcuts (the section/panel analog of the docking
// shell's usePageLayoutKeyboardShortcuts, which is NOT extended). Every handler registers through the shared keybindings
// registry (useKeybindingHandler), so each binding appears on and is configurable from
// the keybindings settings page.
//
// Mounted once by WorkspaceLayoutShell, which only renders on a workspace page, so the
// empty first-run state (no workspaces) never mounts these handlers, so global
// shortcuts are disabled in the empty state for free.
//
// new_workspace (Meta+T) is intentionally NOT handled here: it is served by the
// surviving page-layout hook (usePageLayoutKeyboardShortcuts), which opens the global
// new-workspace dialog. Registering it here too would fire two openers per press.
// Cycling reads live state through the Jotai store at press time to avoid stale
// closures and per-keystroke re-subscription.

import { useSetAtom, useStore } from "jotai";
import { useCallback } from "react";

import { useKeybindingHandler } from "~/common/keybindings";
import { sidebarCollapsedAtom } from "~/components/layout/sidebarAtoms.ts";

import type { WorkspaceLayoutState } from "./persistence/types.ts";
import { jumpToSectionAtom, setActivePanelAtom, toggleSectionAtom } from "./sectionActions.ts";
import { activePanelIdInSubSectionAtom, panelsInSubSectionAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import type { SubSectionId } from "./sectionTypes.ts";
import { SECTION_IDS, toSecondary, toSection } from "./sectionTypes.ts";
import { maximizedSectionAtom } from "./transientAtoms.ts";
import { useAddPanelActions } from "./useAddPanelActions.ts";

type CycleDirection = 1 | -1;

// The ordered active-able sub-sections: each expanded section's primary (center is
// always expanded), plus its secondary half when split. This is the sequence the
// section-cycle steps through.
function activeableSubSections(layout: WorkspaceLayoutState): ReadonlyArray<SubSectionId> {
  const subSections: Array<SubSectionId> = [];
  for (const section of SECTION_IDS) {
    const isExpanded = section === "center" || (layout.expanded[section] ?? false);
    if (!isExpanded) {
      continue;
    }
    subSections.push(section);
    if (layout.splits[section] !== undefined) {
      subSections.push(toSecondary(section));
    }
  }
  return subSections;
}

function stepIndex(length: number, current: number, direction: CycleDirection): number {
  const base = current === -1 ? 0 : current;
  return (base + direction + length) % length;
}

export const useWorkspaceShortcuts = (): void => {
  const store = useStore();
  const toggleSection = useSetAtom(toggleSectionAtom);
  const jumpToSection = useSetAtom(jumpToSectionAtom);
  const setActivePanel = useSetAtom(setActivePanelAtom);
  const setMaximizedSection = useSetAtom(maximizedSectionAtom);
  const setSidebarCollapsed = useSetAtom(sidebarCollapsedAtom);
  const { createRecentAgent } = useAddPanelActions();

  // Cycle the active section through the expanded sub-sections incl. split halves,
  // pulsing the ring on each step.
  const cycleSection = useCallback(
    (direction: CycleDirection): void => {
      const layout = store.get(workspaceLayoutAtom);
      const order = activeableSubSections(layout);
      if (order.length === 0) {
        return;
      }
      const current = layout.activeSubSection ?? "center";
      const next = order[stepIndex(order.length, order.indexOf(current), direction)];
      jumpToSection({ subSection: next });
    },
    [store, jumpToSection],
  );

  // Cycle the active panel within the active sub-section; wraps at the ends and is a
  // no-op for an empty or single-panel section.
  const cyclePanel = useCallback(
    (direction: CycleDirection): void => {
      const layout = store.get(workspaceLayoutAtom);
      const activeSub = layout.activeSubSection ?? "center";
      const panels = store.get(panelsInSubSectionAtom(activeSub));
      if (panels.length < 2) {
        return;
      }
      const active = store.get(activePanelIdInSubSectionAtom(activeSub));
      const currentIndex = active === undefined ? -1 : panels.indexOf(active);
      const next = panels[stepIndex(panels.length, currentIndex, direction)];
      setActivePanel({ panelId: next, in: activeSub });
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

  const toggleSidebar = useCallback((): void => {
    setSidebarCollapsed(!store.get(sidebarCollapsedAtom));
  }, [store, setSidebarCollapsed]);

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
  useKeybindingHandler("toggle_sidebar", toggleSidebar);
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
};
