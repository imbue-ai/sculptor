// Transient (non-persisted) layout atoms — reset on reload, never routed through
// the persistence adapter. They drive modal-ish / in-flight UI (maximize, drag
// preview, the active-section ring) without touching persisted layout. Components
// subscribe to the narrow per-sub-section slices below so a pointer move during a
// drag, or a ring fade, re-renders only the affected section.

import type { Atom, PrimitiveAtom, SetStateAction, WritableAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";

import { activeWorkspaceIdAtom, isActiveSubSectionAtom, panelsInSubSectionAtom } from "./sectionAtoms.ts";
import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";
import { shallowArrayEqual } from "./shallowArrayEqual.ts";

// ── Maximized section ─────────────────────────────────────────────────────────

// One section at a time fills the content area, tracked PER WORKSPACE: each
// workspace remembers its own maximize while the app is open, so switching away
// and back restores it — and a maximize never leaks into a workspace whose own
// layout never set one. Plain non-persisted atoms: reload always returns to the
// normal layout, and a stale flag can never strand the app maximized.
const maximizedSectionFamily = atomFamily((_workspaceId: string) => atom<SectionId | null>(null));

// Read/write proxy for the ACTIVE workspace's maximize — the only view components
// need. Resolves the active workspace on every access (mirroring the
// workspaceLayoutAtom proxy), so a workspace switch is just the one id write.
export const maximizedSectionAtom: WritableAtom<SectionId | null, [SetStateAction<SectionId | null>], void> = atom(
  (get) => {
    const workspaceId = get(activeWorkspaceIdAtom);
    return workspaceId === null ? null : get(maximizedSectionFamily(workspaceId));
  },
  (get, set, update: SetStateAction<SectionId | null>) => {
    const workspaceId = get(activeWorkspaceIdAtom);
    if (workspaceId === null) {
      return;
    }
    set(maximizedSectionFamily(workspaceId), update);
  },
);

// True only when THIS section is the maximized one, so a section subscribes to its
// own flag instead of re-rendering whenever any other section's maximize changes.
export const isMaximizedSectionAtom = atomFamily((section: SectionId) =>
  atom((get) => get(maximizedSectionAtom) === section),
);

// True while any section is maximized — the whole-shell presentation switch
// (e.g. hiding the workspace header). Subscribers re-render only on the
// null ↔ non-null transition, not when the maximize moves between sections.
export const isAnySectionMaximizedAtom: Atom<boolean> = atom((get) => get(maximizedSectionAtom) !== null);

// ── Drag preview ──────────────────────────────────────────────────────────────

export type PanelDragState = { panelId: PanelId; from: SubSectionId; to: SubSectionId; index: number };

// Updated continuously during a drag; the real placement state ignores it until drop.
export const panelDragStateAtom: PrimitiveAtom<PanelDragState | null> = atom<PanelDragState | null>(null);

// Stable for the whole drag — reads only the panel id, so it does not change as the
// insertion index moves. PanelDndProvider subscribes to this.
export const draggedPanelIdAtom: Atom<PanelId | null> = selectAtom(panelDragStateAtom, (drag) => drag?.panelId ?? null);

export const isDropTargetAtom = atomFamily((subSection: SubSectionId) =>
  selectAtom(panelDragStateAtom, (drag) => drag !== null && drag.to === subSection),
);

// ── Drag pointer halves ───────────────────────────────────────────────────────

// Which halves of the window the drag pointer is in (left/right split at the
// horizontal midpoint, bottom below the vertical midpoint). Drives which
// collapsed-section drop overlays are visible. All false for keyboard drags (no
// pointer), where overlay visibility falls back to the drop-target highlight.
export type DragPointerHalves = { left: boolean; right: boolean; bottom: boolean };

export const NO_DRAG_POINTER_HALVES: DragPointerHalves = { left: false, right: false, bottom: false };

const dragPointerHalvesBaseAtom: PrimitiveAtom<DragPointerHalves> = atom<DragPointerHalves>(NO_DRAG_POINTER_HALVES);

// Write-through with an equality guard: the provider writes on every drag move,
// but subscribers only re-render when the pointer actually crosses a midline.
export const dragPointerHalvesAtom = atom(
  (get) => get(dragPointerHalvesBaseAtom),
  (get, set, next: DragPointerHalves): void => {
    const prev = get(dragPointerHalvesBaseAtom);
    if (prev.left === next.left && prev.right === next.right && prev.bottom === next.bottom) {
      return;
    }
    set(dragPointerHalvesBaseAtom, next);
  },
);

// The single half slice a collapsed section's drop overlay watches (a section's
// overlay shows while the pointer is in the same-named window half).
export const isDragPointerInHalfAtom = atomFamily((half: "left" | "right" | "bottom") =>
  selectAtom(dragPointerHalvesBaseAtom, (halves) => halves[half]),
);

export const ghostPanelIdAtom = atomFamily((subSection: SubSectionId) =>
  selectAtom(panelDragStateAtom, (drag): PanelId | null =>
    drag !== null && drag.to === subSection ? drag.panelId : null,
  ),
);

// True while a panel is being reordered WITHIN this sub-section (drag origin and
// target are both this sub-section). In that case the single displayed instance is
// the live draggable shown at its preview slot; in a CROSS-section drag the dragged
// panel appears twice (the real draggable stays in its source while a ghost preview
// shows in the target), so the target must render a non-draggable placeholder to
// avoid registering the same draggable id twice. SectionHeader uses this to decide.
export const isReorderWithinSubSectionAtom = atomFamily((subSection: SubSectionId) =>
  selectAtom(panelDragStateAtom, (drag) => drag !== null && drag.to === subSection && drag.from === subSection),
);

// The sub-section's open panels with the in-flight ghost spliced in at its
// prospective insertion index, so the live preview shows the panel where it would
// land. Caches the last array to stay reference-stable (no notify when unchanged).
export const displayedPanelIdsAtom = atomFamily((subSection: SubSectionId) => {
  let lastResult: ReadonlyArray<PanelId> | undefined;
  return atom((get) => {
    const base = get(panelsInSubSectionAtom(subSection));
    const drag = get(panelDragStateAtom);
    let result: ReadonlyArray<PanelId>;
    if (drag !== null && drag.to === subSection) {
      const withoutDragged = base.filter((id) => id !== drag.panelId);
      const index = Math.max(0, Math.min(drag.index, withoutDragged.length));
      result = [...withoutDragged.slice(0, index), drag.panelId, ...withoutDragged.slice(index)];
    } else {
      result = base;
    }

    if (lastResult !== undefined && shallowArrayEqual(lastResult, result)) {
      return lastResult;
    }
    lastResult = result;
    return result;
  });
});

// ── Recently closed single-instance panels ────────────────────────────────────

// Most-recently-closed single-instance panel ids, newest first. Drives the
// empty-state quick actions: the up-to-three recently-closed panels a
// user can re-open with one click. Transient (reset on reload) and capped — only
// single-instance panels belong here (closing an agent/terminal ends it, so they
// are never re-offered). Maintained by the section close handler, which knows the
// panel is single-instance, rather than the layout reducers.
const RECENTLY_CLOSED_PANELS_CAP = 8;

const recentlyClosedPanelIdsBaseAtom: PrimitiveAtom<ReadonlyArray<PanelId>> = atom<ReadonlyArray<PanelId>>([]);

export const recentlyClosedPanelIdsAtom = atom(
  (get) => get(recentlyClosedPanelIdsBaseAtom),
  (get, set, panelId: PanelId): void => {
    const withoutPanel = get(recentlyClosedPanelIdsBaseAtom).filter((id) => id !== panelId);
    set(recentlyClosedPanelIdsBaseAtom, [panelId, ...withoutPanel].slice(0, RECENTLY_CLOSED_PANELS_CAP));
  },
);

// ── Active-section ring ───────────────────────────────────────────────────────

export const RING_VISIBLE_MS = 2000;

// Transient visibility layer over the persisted active sub-section. A fade
// timer/effect flips this to false after RING_VISIBLE_MS.
export const activeSectionRingVisibleAtom: PrimitiveAtom<boolean> = atom<boolean>(false);

// Bumped on a deliberate jump (keyboard cycle / add / drop / workspace entry) to
// (re)start the ring fade timer. jumpToSectionAtom increments this.
export const activeSectionRingNonceAtom: PrimitiveAtom<number> = atom<number>(0);

// True only when this sub-section is the active one AND the ring is visible, so the
// fade timer re-renders only the highlighted section.
export const isRingVisibleAtom = atomFamily((subSection: SubSectionId) =>
  atom((get) => get(isActiveSubSectionAtom(subSection)) && get(activeSectionRingVisibleAtom)),
);
