# Task 4.1: PanelDndProvider — drag-and-drop with a keyboard sensor + drag handle

## Goal

Replace the Phase-2 `PanelDndProvider` stub with the real single app-level
drag-and-drop context: panels drag between sections and reorder within a section,
collapsed sections expand on drop, split dropzones appear only while a split exists,
and a `KeyboardSensor` + drag handle makes the whole thing driveable by Playwright.

## Stories addressed

PANEL-08 (drag to another section + reorder within a section), PANEL-09 (drop on a
collapsed section shows a dropzone and expands on drop, appending), PANEL-10 (split
section shows per-sub-section dropzones only while split), PANEL-16 (reorder persists
across collapse→expand and switch). Non-functional: drag does not cascade re-renders
(SWITCH-05).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`, using
dnd-kit.

**The architecture** (`component_hierarchy.md` → "Drag-and-drop architecture";
`state_design.md` → "Drag preview"): a single app-level `PanelDndProvider` wraps the
whole layout. Each `PanelSection` registers its body as a drop target (keyed by
sub-section id) and each tab as a draggable. During a drag, only the **transient
drag-preview** state updates (`panelDragStateAtom`); the **real placement state
mutates once, on drop** (`movePanelAtom`). The provider subscribes only to the
**stable dragged-panel id** (`draggedPanelIdAtom`), not the moving preview, so it
does not re-render on every pointer move; sections subscribe to **narrow per-section
slices** (`isDropTargetAtom(ss)`, `ghostPanelIdAtom(ss)`), so a pointer move
re-renders only the sections under/around the cursor.

**What to copy** (`design_extraction.md` → "Sections… drag & drop"):
`components/panels/PanelDndProvider.tsx` + `.module.scss` — dnd-kit context, drag-
overlay tab, per-zone droppables (incl. collapsed-section and split sub-section
zones).

**DnD testability — decided** (`harness_migration.md` §3b;
`sections_panel_layout.md` §4): the prototype provider uses only a `PointerSensor`
(5px activation), which Playwright cannot drive faithfully (it dispatches
MouseEvents, not the PointerEvent + `requestAnimationFrame` pipeline dnd-kit needs).
**Add a `KeyboardSensor` + a drag handle** to the provider (also an accessibility
win) so Playwright drives the real sensor pipeline (`Space` → arrows → `Space`).
Wrap it in a `drag_panel_to_section()` helper (Task 4.6) so test bodies stay
affordance-agnostic.

This task depends on **Task 1.4** (`movePanelAtom`, `toggleSectionAtom`), **Task
1.5** (drag-preview atoms + slices), and **Task 2.4** (`PanelSection` drop-target /
tab-draggable seams) and **2.6** (the stub it replaces).

## Files to modify/create

- `sculptor/frontend/src/components/sections/PanelDndProvider.tsx` + `.module.scss` —
  replace the stub with the real provider.
- `sculptor/frontend/src/components/sections/PanelSection.tsx` — modify: register the
  body droppable (keyed by `ss`) and the tab draggables + drag handle.
- `sculptor/sculptor/constants.py` — add a drag-handle id if needed (e.g.
  `PANEL_TAB_DRAG_HANDLE`); `just generate-api`.

## Implementation details

1. Build the provider with `useSensors(useSensor(PointerSensor, {distance:5}),
   useSensor(KeyboardSensor))`. Render a drag handle on each panel tab bound to the
   keyboard sensor.
2. On drag start, set `panelDragStateAtom` (panelId/from); on drag over, update
   `to`/`index` (preview only); on drag end, call `movePanelAtom({panelId, to,
   index})` once and clear the preview.
3. Provider subscribes to `draggedPanelIdAtom` (stable) — not the moving preview.
   Sections read `isDropTargetAtom(ss)`/`ghostPanelIdAtom(ss)`/`displayedPanelIdsAtom(ss)`.
4. **Droppables:** each sub-section body is a droppable keyed by `ss`. **Collapsed
   sections** are also drop targets — dropping on one shows a dropzone and **expands
   the section on drop** (call `toggleSectionAtom` then append) (PANEL-09).
   **Split** sub-section dropzones exist **only while the split exists** (PANEL-10).
5. Reorder within a section updates `order`; cross-section drag updates placement +
   order; a no-op release outside any dropzone leaves placement unchanged.
6. Keep the provider's render cheap (the SWITCH-05 boundary): no subscription to the
   moving preview at the provider level.

## Testing suggestions

- `test_panel_drag_and_drop.py` (PANEL-08/09/10/16) lands in **Task 4.6**, driven via
  the `KeyboardSensor` + `drag_panel_to_section()` helper. Include: reorder within a
  section; drag to another section; drop on a collapsed section expands it; split
  dropzones only while split; a no-op release leaves placement unchanged; reorder
  persists across collapse→expand and switch (PANEL-16).
- SWITCH-05 (memoized re-renders during drag) is verified by `measure-react-renders`
  in Task 9.1.

## Gotchas

- **Add the `KeyboardSensor` + drag handle** — without it the drag tests are
  flaky-to-non-functional.
- Mutate **real placement only on drop**; everything during the drag is the transient
  preview.
- The provider must subscribe to the **stable** dragged id, not the preview, or it
  re-renders on every pointer move.
- Collapsed-section drop must expand-then-append; split dropzones must not appear when
  there is no split.

## Verification checklist

- [ ] Single app-level provider with `PointerSensor` + `KeyboardSensor` + drag
  handle.
- [ ] Drag preview updates transient state only; drop calls `movePanelAtom` once.
- [ ] Collapsed-section drop expands + appends; split dropzones only while split.
- [ ] Provider subscribes to the stable dragged id; sections to narrow slices.
- [ ] `just check` passes (the DnD e2e is in Task 4.6).
