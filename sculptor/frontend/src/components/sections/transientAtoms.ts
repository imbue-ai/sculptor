// Transient (non-persisted) layout atoms — reset on reload, never routed through
// the persistence adapter. They drive modal-ish / in-flight UI (maximize, drag
// preview, the active-section ring) without touching persisted layout. Components
// subscribe to the narrow per-sub-section slices below so a pointer move during a
// drag, or a ring fade, re-renders only the affected section.

import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { selectAtom } from "jotai/utils";

import { isActiveSubSectionAtom, panelsInSubSectionAtom } from "./sectionAtoms.ts";
import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";

function memoizedAtomByKey<TKey extends string, TValue>(
  factory: (key: TKey) => Atom<TValue>,
): (key: TKey) => Atom<TValue> {
  const cache = new Map<string, Atom<TValue>>();
  return (key) => {
    let cached = cache.get(key);
    if (cached === undefined) {
      cached = factory(key);
      cache.set(key, cached);
    }
    return cached;
  };
}

function shallowArrayEqual<T>(a: ReadonlyArray<T>, b: ReadonlyArray<T>): boolean {
  if (a === b) {
    return true;
  }

  if (a.length !== b.length) {
    return false;
  }
  return a.every((value, index) => value === b[index]);
}

// ── Maximized section ─────────────────────────────────────────────────────────

// One section at a time fills the content area. Plain atom: reload always returns
// to the normal layout, and a stale flag can never strand the app maximized.
export const maximizedSectionAtom: PrimitiveAtom<SectionId | null> = atom<SectionId | null>(null);

// ── Drag preview ──────────────────────────────────────────────────────────────

export type PanelDragState = { panelId: PanelId; from: SubSectionId; to: SubSectionId; index: number };

// Updated continuously during a drag; the real placement state ignores it until drop.
export const panelDragStateAtom: PrimitiveAtom<PanelDragState | null> = atom<PanelDragState | null>(null);

// Stable for the whole drag — reads only the panel id, so it does not change as the
// insertion index moves. PanelDndProvider subscribes to this.
export const draggedPanelIdAtom: Atom<PanelId | null> = selectAtom(panelDragStateAtom, (drag) => drag?.panelId ?? null);

export const isDropTargetAtom = memoizedAtomByKey<SubSectionId, boolean>((subSection) =>
  selectAtom(panelDragStateAtom, (drag) => drag !== null && drag.to === subSection),
);

export const ghostPanelIdAtom = memoizedAtomByKey<SubSectionId, PanelId | null>((subSection) =>
  selectAtom(panelDragStateAtom, (drag) => (drag !== null && drag.to === subSection ? drag.panelId : null)),
);

// The sub-section's open panels with the in-flight ghost spliced in at its
// prospective insertion index, so the live preview shows the panel where it would
// land. Caches the last array to stay reference-stable (no notify when unchanged).
export const displayedPanelIdsAtom = memoizedAtomByKey<SubSectionId, ReadonlyArray<PanelId>>((subSection) => {
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

// ── Active-section ring ───────────────────────────────────────────────────────

export const RING_VISIBLE_MS = 2000;

// Transient visibility layer over the persisted active sub-section. The fade
// timer/effect that flips this to false after RING_VISIBLE_MS is built in Task 4.4.
export const activeSectionRingVisibleAtom: PrimitiveAtom<boolean> = atom<boolean>(false);

// Bumped on a deliberate jump (keyboard cycle / add / drop / workspace entry) to
// (re)start the ring fade timer. jumpToSectionAtom (Task 1.4) increments this.
export const activeSectionRingNonceAtom: PrimitiveAtom<number> = atom<number>(0);

// True only when this sub-section is the active one AND the ring is visible, so the
// fade timer re-renders only the highlighted section.
export const isRingVisibleAtom = memoizedAtomByKey<SubSectionId, boolean>((subSection) =>
  atom((get) => get(isActiveSubSectionAtom(subSection)) && get(activeSectionRingVisibleAtom)),
);
