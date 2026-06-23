# Task 1.5: Transient atoms — maximized, drag preview, active-section ring

## Goal

Build the non-persisted transient atoms: the maximized section, the drag-preview
state with its narrow per-sub-section slices, and the active-section ring
visibility. These reset on reload and drive modal-ish / in-flight UI without
touching persisted layout.

## Stories addressed

SEC-11 (ring fade), SEC-13/SEC-21 (maximize is transient, clears on reload),
PANEL-08..10 (drag preview / dropzones), and the narrow drag slices that keep
dragging cheap (SWITCH-05 memoization).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the
workspace shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**Transient state is separate by design** (`state_design.md` → "Maximized section",
"Drag preview", "Active section and the highlight ring"; `supplemental/state_atoms.md`
→ "Transient atoms"):
- **Maximized** is modal-ish — reload always returns to the normal layout, and a
  stale flag must never strand the app maximized. So it is a plain
  non-persisted atom.
- **Drag preview** is updated continuously during a drag, but the *real* placement
  state ignores it until drop. Components subscribe to **narrow per-section slices**
  of it (is-this-the-drop-target, the ghost panel for this section), so a pointer
  move re-renders only the affected sections.
- **The ring is a separate layer from the logical active section.** The logical
  active sub-section persists (Task 1.3); the ring's *visibility* is transient — it
  flashes on a deliberate jump and fades within ~2s. A plain click sets active
  without flashing the ring. One fade timer touches only the highlighted section.

This task depends on **Task 1.1** (`sectionTypes.ts`) and **Task 1.3** (per-ss
slice memoization pattern; `panelsInSubSectionAtom` for `displayedPanelIdsAtom`).

## Files to modify/create

- `sculptor/frontend/src/components/sections/transientAtoms.ts` — new.
- `sculptor/frontend/src/components/sections/transientAtoms.test.ts` — new. Vitest.

## Implementation details

Per `supplemental/state_atoms.md` → "Transient atoms":

1. **Maximized:** `maximizedSectionAtom: PrimitiveAtom<SectionId | null>` — one at
   a time; never persisted (a plain atom — do NOT route through the adapter).
2. **Drag preview:**
   - `type PanelDragState = { panelId: PanelId; from: SubSectionId; to:
     SubSectionId; index: number }`.
   - `panelDragStateAtom: PrimitiveAtom<PanelDragState | null>` — updated
     continuously during a drag.
   - `draggedPanelIdAtom: Atom<PanelId | null>` — derived to be **stable for the
     whole drag** (reads only `panelDragStateAtom?.panelId`, so it does not change
     as the insertion index moves). This is what `PanelDndProvider` subscribes to.
   - `isDropTargetAtom(ss): Atom<boolean>` — true when `panelDragStateAtom.to ===
     ss`. Memoized per `ss` in a Map.
   - `ghostPanelIdAtom(ss): Atom<PanelId | null>` — the dragged panel when it would
     land in `ss`, else null. Memoized per `ss`.
   - `displayedPanelIdsAtom(ss): Atom<readonly PanelId[]>` — `panelsInSubSectionAtom(ss)`
     merged with the in-flight ghost at its insertion index (so the live preview
     shows the panel in its prospective position). Memoized per `ss`; shallow-array
     equality.
3. **Active-section ring:**
   - `activeSectionRingVisibleAtom: PrimitiveAtom<boolean>`.
   - `activeSectionRingNonceAtom: PrimitiveAtom<number>` — bumped to (re)start the
     fade timer; this is what `jumpToSectionAtom` (Task 1.4) increments.
   - `isRingVisibleAtom(ss): Atom<boolean>` — true when `ss` is the active
     sub-section **and** the ring is visible. Memoized per `ss`. (The active
     sub-section comes from `isActiveSubSectionAtom(ss)` in Task 1.3.)
   - `export const RING_VISIBLE_MS = 2000` (`goals.md` → "Active section": fades
     within ~2 seconds). The fade *timer/effect* that flips
     `activeSectionRingVisibleAtom` to false after `RING_VISIBLE_MS` is rebuilt as a
     hook in Task 4.4 — this task only owns the atoms + the constant.

## Testing suggestions

- Vitest: `draggedPanelIdAtom` stays referentially stable while only
  `panelDragStateAtom.index` changes (subscribe + count notifications);
  `isDropTargetAtom(ss)` is true only for the current `to` and false elsewhere;
  `displayedPanelIdsAtom` inserts the ghost at the right index; bumping the ring
  nonce / setting visible flips `isRingVisibleAtom` only for the active ss.
- Run `just test-unit-frontend`.

## Gotchas

- **None of these go through the persistence adapter** — they are plain atoms that
  reset on reload (that is the point for maximize and the ring).
- `draggedPanelIdAtom` must be stable across pointer moves — subscribe to the panel
  id only, never the index — or `PanelDndProvider` re-renders on every move.
- Memoize per-`ss` slice atoms in a module-load `Map` (same re-render-loop caveat
  as Task 1.3).
- Keep the ring **visibility** separate from the **logical** active section so the
  fade timer never re-renders other sections.

## Verification checklist

- [ ] `maximizedSectionAtom`, the drag-preview atoms + per-ss slices, and the ring
  atoms + `RING_VISIBLE_MS` are all present and non-persisted.
- [ ] `draggedPanelIdAtom` is stable across index changes (tested).
- [ ] Per-ss slices are memoized in a Map.
- [ ] Unit tests pass via `just test-unit-frontend`.
