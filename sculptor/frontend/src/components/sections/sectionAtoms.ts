// Consolidated Jotai layout atoms for the workspace section/panel shell.
//
// One per-workspace snapshot (workspaceLayoutFamily) and one global snapshot
// (globalLayoutAtom), both backed by the persistence adapter. The app
// reads the active workspace through the `workspaceLayoutAtom` proxy, which resolves
// the active scope on every read/write so switching workspaces is a single write to
// `activeWorkspaceIdAtom`. Components subscribe to the narrow, per-key read slices
// below — each memoized into a module-load Map so the same atom instance is reused
// per key (a fresh derived atom per render causes Jotai re-render loops).

import type { Atom, WritableAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";

import { memoizedAtomByKey, shallowArrayEqual } from "./atomCache.ts";
import { layoutPersistenceAdapter } from "./persistence/LocalStorageLayoutAdapter.ts";
import type { GlobalLayoutState, LayoutScope, WorkspaceLayoutState } from "./persistence/types.ts";
import { DEFAULT_GLOBAL_LAYOUT, EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import { SECTION_SIZE_MAX_PERCENT, SECTION_SIZE_MIN_PERCENT } from "./sectionGeometry.ts";
import type { PanelId, SectionId, SectionSplit, SubSectionId } from "./sectionTypes.ts";
import { toSection } from "./sectionTypes.ts";

type WorkspaceLayoutUpdater = WorkspaceLayoutState | ((prev: WorkspaceLayoutState) => WorkspaceLayoutState);
type GlobalLayoutUpdater = GlobalLayoutState | ((prev: GlobalLayoutState) => GlobalLayoutState);

function applyUpdater<T>(prev: T, updater: T | ((prev: T) => T)): T {
  return typeof updater === "function" ? (updater as (p: T) => T)(prev) : updater;
}

// ── Scope atoms ──────────────────────────────────────────────────────────────

export const activeWorkspaceIdAtom = atom<string | null>(null);

export const layoutScopeAtom: Atom<LayoutScope> = atom((get) => {
  const workspaceId = get(activeWorkspaceIdAtom);
  return workspaceId === null ? { kind: "global" } : { kind: "workspace", workspaceId };
});

// ── Consolidated per-workspace layout ─────────────────────────────────────────

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

// ── Consolidated global layout ────────────────────────────────────────────────

const globalBaseAtom = atom<GlobalLayoutState>(
  layoutPersistenceAdapter.read({ kind: "global" }) ?? DEFAULT_GLOBAL_LAYOUT,
);

export const globalLayoutAtom: WritableAtom<GlobalLayoutState, [GlobalLayoutUpdater], void> = atom(
  (get) => get(globalBaseAtom),
  (get, set, updater: GlobalLayoutUpdater) => {
    const next = applyUpdater(get(globalBaseAtom), updater);
    set(globalBaseAtom, next);
    layoutPersistenceAdapter.write({ kind: "global" }, next);
  },
);

// ── Narrow read slices (per-key, memoized) ────────────────────────────────────

// Open panels in a sub-section, ordered. A panel's presence in `placement` is its
// "open" state; `order` gives the tab order. Any placed-but-unordered panel is
// appended so the slice never drops an open panel.
function openPanelsInSubSection(layout: WorkspaceLayoutState, subSection: SubSectionId): ReadonlyArray<PanelId> {
  const placedHere = (Object.keys(layout.placement) as ReadonlyArray<PanelId>).filter(
    (panelId) => layout.placement[panelId] === subSection,
  );
  const placedSet = new Set(placedHere);
  const ordered = (layout.order[subSection] ?? []).filter((panelId) => placedSet.has(panelId));
  const orderedSet = new Set(ordered);
  const rest = placedHere.filter((panelId) => !orderedSet.has(panelId));
  return [...ordered, ...rest];
}

export const panelsInSubSectionAtom = memoizedAtomByKey<SubSectionId, ReadonlyArray<PanelId>>((subSection) =>
  selectAtom(workspaceLayoutAtom, (layout) => openPanelsInSubSection(layout, subSection), shallowArrayEqual),
);

export const activePanelIdInSubSectionAtom = memoizedAtomByKey<SubSectionId, PanelId | undefined>((subSection) =>
  selectAtom(workspaceLayoutAtom, (layout) => {
    const open = openPanelsInSubSection(layout, subSection);
    const stored = layout.activePanel[subSection];
    if (stored !== undefined && open.includes(stored)) {
      return stored;
    }
    return open[0];
  }),
);

export const isSectionExpandedAtom = memoizedAtomByKey<SectionId, boolean>((section) =>
  // Center is always expanded and is never in the collapsed set.
  selectAtom(workspaceLayoutAtom, (layout) => (section === "center" ? true : (layout.expanded[section] ?? false))),
);

export const sectionSplitForSectionAtom = memoizedAtomByKey<SectionId, SectionSplit | undefined>((section) =>
  selectAtom(workspaceLayoutAtom, (layout) => layout.splits[section]),
);

export const isSplitHalfAtom = memoizedAtomByKey<SubSectionId, boolean>((subSection) =>
  selectAtom(workspaceLayoutAtom, (layout) => layout.splits[toSection(subSection)] !== undefined),
);

export const activeSubSectionAtom: Atom<SubSectionId | null> = selectAtom(
  workspaceLayoutAtom,
  (layout) => layout.activeSubSection,
);

export const isActiveSubSectionAtom = memoizedAtomByKey<SubSectionId, boolean>((subSection) =>
  selectAtom(workspaceLayoutAtom, (layout) => layout.activeSubSection === subSection),
);

// ── Global slices ─────────────────────────────────────────────────────────────

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

// ── Scope switching / removal ─────────────────────────────────────────────────

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
