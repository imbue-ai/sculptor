// Shared drag-and-drop contract between PanelDndProvider (the single app-level
// DndContext), the draggable panel tabs (SectionHeader), and the drop targets (each
// expanded PanelSection body + each collapsed section's in-grid drop rail).
//
// dnd-kit carries our own payloads on `active.data.current` / `over.data.current`,
// so the provider reads these typed shapes instead of parsing ids. Ids only need to
// be unique strings; a tab is both a draggable (id = panelId) and lives next to drop
// targets, so the droppable ids are namespaced to avoid colliding with the panel id.

import type { PanelId, SubSectionId } from "./sectionTypes.ts";

// What a dragged panel tab carries. `from`/`index` seed the initial preview so the
// ghost starts in place before the first drag-over refines the target.
export type PanelDragData = { kind: "panel"; panelId: PanelId; from: SubSectionId; index: number };

// What a drop target carries. Both the in-grid section body (when expanded) and the
// collapsed-section drop rail (when collapsed, during a drag) use this — they share
// one droppable id per sub-section and are never mounted at the same time, so a drop
// onto either lands the panel in that sub-section (a collapsed section expands first).
// There is no per-tab droppable, so reordering is pointer-precise and keyboard drops
// append.
export type PanelDropData = { kind: "section-body"; subSection: SubSectionId };

// Sentinel "insert at the end" index: clamped by displayedPanelIdsAtom for the live
// ghost and mapped to `undefined` (splice at length) for the real move on drop.
export const APPEND_INDEX = Number.MAX_SAFE_INTEGER;

// How far the pointer must travel before a press becomes a drag. Shared by every
// drag pipeline (panel tabs, sidebar rows/groups) so plain clicks keep working on
// drag activators and the click-vs-drag threshold can't drift between surfaces.
export const POINTER_DRAG_ACTIVATION_DISTANCE_PX = 5;

// Droppable id for a sub-section's drop target. The expanded section body and the
// collapsed section's drop rail share this id (never mounted together).
export function sectionBodyDroppableId(subSection: SubSectionId): string {
  return `section-body:${subSection}`;
}
