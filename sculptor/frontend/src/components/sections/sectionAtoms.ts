// Consolidated Jotai layout atoms for the workspace section/panel shell.
//
// One per-workspace snapshot (workspaceLayoutFamily) and one global snapshot
// (globalLayoutAtom), both backed by the persistence adapter. The app
// reads the active workspace through the `workspaceLayoutAtom` proxy, which resolves
// the active scope on every read/write so switching workspaces is a single write to
// `activeWorkspaceIdAtom`. Components subscribe to the narrow, per-key read slices
// below — each an atomFamily so the same atom instance is reused per key (a fresh
// derived atom per render causes Jotai re-render loops).

import type { Atom, WritableAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";

import { isSectionExpanded, openPanelsInSubSection } from "./layoutQueries.ts";
import { layoutPersistenceAdapter } from "./persistence/LocalStorageLayoutAdapter.ts";
import type { GlobalLayoutState, WorkspaceLayoutState } from "./persistence/types.ts";
import { DEFAULT_GLOBAL_LAYOUT, EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import { SECTION_SIZE_MAX_PERCENT, SECTION_SIZE_MIN_PERCENT } from "./sectionGeometry.ts";
import type { PanelId, SectionId, SectionSplit, SubSectionId } from "./sectionTypes.ts";
import { toSection } from "./sectionTypes.ts";
import { shallowArrayEqual } from "./shallowArrayEqual.ts";

type WorkspaceLayoutUpdater = WorkspaceLayoutState | ((prev: WorkspaceLayoutState) => WorkspaceLayoutState);
type GlobalLayoutUpdater = GlobalLayoutState | ((prev: GlobalLayoutState) => GlobalLayoutState);

function applyUpdater<T>(prev: T, updater: T | ((prev: T) => T)): T {
  return typeof updater === "function" ? (updater as (p: T) => T)(prev) : updater;
}

// Scope atoms

export const activeWorkspaceIdAtom = atom<string | null>(null);

// Consolidated per-workspace layout

// One writable, self-persisting atom per workspace. Initial value comes straight
// from the adapter so the first render restores the persisted layout; every write
// updates memory and persists (the adapter debounces the actual storage write).
export const workspaceLayoutFamily = atomFamily((workspaceId: string) => {
  const initial = layoutPersistenceAdapter.read({ kind: "workspace", workspaceId }) ?? EMPTY_WORKSPACE_LAYOUT;
  const baseAtom = atom<WorkspaceLayoutState>(initial);
  return atom(
    (get) => get(baseAtom),
    (get, set, updater: WorkspaceLayoutUpdater) => {
      const next = applyUpdater(get(baseAtom), updater);
      set(baseAtom, next);
      layoutPersistenceAdapter.write({ kind: "workspace", workspaceId }, next);
    },
  );
});

// Backs the proxy when no workspace is active. In-memory only (never persisted) so
// reads never crash and the global route does not pollute storage.
const sentinelWorkspaceLayoutAtom = atom<WorkspaceLayoutState>(EMPTY_WORKSPACE_LAYOUT);

// The proxy the app reads. Resolves the active scope on EACH read/write — switching
// workspaces (a single write to activeWorkspaceIdAtom) flips the whole layout.
export const workspaceLayoutAtom: WritableAtom<WorkspaceLayoutState, [WorkspaceLayoutUpdater], void> = atom(
  (get) => {
    const workspaceId = get(activeWorkspaceIdAtom);
    return workspaceId === null ? get(sentinelWorkspaceLayoutAtom) : get(workspaceLayoutFamily(workspaceId));
  },
  (get, set, updater: WorkspaceLayoutUpdater) => {
    const workspaceId = get(activeWorkspaceIdAtom);
    if (workspaceId === null) {
      set(sentinelWorkspaceLayoutAtom, applyUpdater(get(sentinelWorkspaceLayoutAtom), updater));
    } else {
      set(workspaceLayoutFamily(workspaceId), updater);
    }
  },
);

// Consolidated global layout

// Merge the stored snapshot over the defaults (not `??`): a snapshot written before
// a field existed lacks it, and the merge fills the gap so adding a global field
// never needs a snapshot-version bump.
const globalBaseAtom = atom<GlobalLayoutState>({
  ...DEFAULT_GLOBAL_LAYOUT,
  ...layoutPersistenceAdapter.read({ kind: "global" }),
});

export const globalLayoutAtom: WritableAtom<GlobalLayoutState, [GlobalLayoutUpdater], void> = atom(
  (get) => get(globalBaseAtom),
  (get, set, updater: GlobalLayoutUpdater) => {
    const next = applyUpdater(get(globalBaseAtom), updater);
    set(globalBaseAtom, next);
    layoutPersistenceAdapter.write({ kind: "global" }, next);
  },
);

// Narrow read slices (per-key atom families)

export const panelsInSubSectionAtom = atomFamily((subSection: SubSectionId) =>
  selectAtom(workspaceLayoutAtom, (layout) => openPanelsInSubSection(layout, subSection), shallowArrayEqual),
);

export const activePanelIdInSubSectionAtom = atomFamily((subSection: SubSectionId) =>
  selectAtom(workspaceLayoutAtom, (layout): PanelId | undefined => {
    const open = openPanelsInSubSection(layout, subSection);
    const stored = layout.activePanel[subSection];
    if (stored !== undefined && open.includes(stored)) {
      return stored;
    }
    return open[0];
  }),
);

export const isSectionExpandedAtom = atomFamily((section: SectionId) =>
  selectAtom(workspaceLayoutAtom, (layout) => isSectionExpanded(layout, section)),
);

export const sectionSplitForSectionAtom = atomFamily((section: SectionId) =>
  selectAtom(workspaceLayoutAtom, (layout): SectionSplit | undefined => layout.splits[section]),
);

export const isSplitHalfAtom = atomFamily((subSection: SubSectionId) =>
  selectAtom(workspaceLayoutAtom, (layout) => layout.splits[toSection(subSection)] !== undefined),
);

export const activeSubSectionAtom: Atom<SubSectionId | null> = selectAtom(
  workspaceLayoutAtom,
  (layout) => layout.activeSubSection,
);

export const isActiveSubSectionAtom = atomFamily((subSection: SubSectionId) =>
  selectAtom(workspaceLayoutAtom, (layout) => layout.activeSubSection === subSection),
);

// Global slices

function sectionSizesEqual(a: GlobalLayoutState["sectionSizes"], b: GlobalLayoutState["sectionSizes"]): boolean {
  return a.left === b.left && a.right === b.right && a.bottom === b.bottom;
}

export const sectionSizesAtom: Atom<GlobalLayoutState["sectionSizes"]> = selectAtom(
  globalLayoutAtom,
  (global) => global.sectionSizes,
  sectionSizesEqual,
);

// Write a section's global size percentage (clamped). Resizing in one workspace
// changes the size everywhere.
export const setSectionSizeAtom = atom(
  null,
  (_get, set, params: { side: "left" | "right" | "bottom"; percent: number }) => {
    const clamped = Math.max(SECTION_SIZE_MIN_PERCENT, Math.min(SECTION_SIZE_MAX_PERCENT, params.percent));
    set(globalLayoutAtom, (prev) => ({
      ...prev,
      sectionSizes: { ...prev.sectionSizes, [params.side]: clamped },
    }));
  },
);

// Clamp bounds for the explorer list-pane width. The minimum keeps the list
// usable (file names readable); the maximum keeps the viewer from being starved
// even in a wide section.
export const EXPLORER_LIST_MIN_WIDTH_PX = 180;
export const EXPLORER_LIST_MAX_WIDTH_PX = 480;

// The explorer (Files / Changes / Commits) list-pane width. One global,
// persisted value: dragging the divider in any of the three panels resizes all
// of them, in every workspace. Writes clamp to the bounds above so a drag can
// neither collapse the list nor swallow the viewer.
export const explorerListWidthAtom: WritableAtom<number, [number], void> = atom(
  (get) => get(globalLayoutAtom).explorerListWidthPx,
  (_get, set, widthPx: number) => {
    const clamped = Math.max(EXPLORER_LIST_MIN_WIDTH_PX, Math.min(EXPLORER_LIST_MAX_WIDTH_PX, widthPx));
    set(globalLayoutAtom, (prev) => ({ ...prev, explorerListWidthPx: clamped }));
  },
);

// Scope switching / removal

// A workspace's snapshot is "empty" (never visited / nothing seeded) when no panel is
// placed and no sub-section is active. The bootstrap uses this as the first-visit
// signal to seed the default arrangement + terminal; a restored
// snapshot is never empty, so it is never re-seeded.
export function isEmptyLayout(layout: WorkspaceLayoutState): boolean {
  return Object.keys(layout.placement).length === 0 && layout.activeSubSection === null;
}

// Switch the active workspace in one write. First visit seeds the default layout if
// provided and the family entry is still empty; the full default-layout seeding plus
// registry/dynamic-panel placement are wired in the bootstrap.
export const switchActiveWorkspaceAtom = atom(
  null,
  (get, set, params: { workspaceId: string; defaultLayout?: WorkspaceLayoutState }) => {
    set(activeWorkspaceIdAtom, params.workspaceId);
    if (params.defaultLayout !== undefined && isEmptyLayout(get(workspaceLayoutFamily(params.workspaceId)))) {
      set(workspaceLayoutFamily(params.workspaceId), params.defaultLayout);
    }
  },
);

// Drop a workspace's layout on delete (in-memory family entry + persisted snapshot).
export const removeWorkspaceLayoutAtom = atom(null, (_get, _set, params: { workspaceId: string }) => {
  layoutPersistenceAdapter.remove({ kind: "workspace", workspaceId: params.workspaceId });
  workspaceLayoutFamily.remove(params.workspaceId);
});
