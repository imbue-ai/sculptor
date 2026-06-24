// Shared drag-and-drop contract between PanelDndProvider (the single app-level
// DndContext), the draggable panel tabs (SectionHeader), and the drop targets
// (each PanelSection body + each collapsed-section toggle in the workspace header).
//
// dnd-kit carries our own payloads on `active.data.current` / `over.data.current`,
// so the provider reads these typed shapes instead of parsing ids. Ids only need to
// be unique strings; a tab is both a draggable (id = panelId) and lives next to drop
// targets, so the droppable ids are namespaced to avoid colliding with the panel id.

import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";
import { primaryOf } from "./sectionTypes.ts";

// What a dragged panel tab carries. `from`/`index` seed the initial preview so the
// ghost starts in place before the first drag-over refines the target.
export type PanelDragData = { kind: "panel"; panelId: PanelId; from: SubSectionId; index: number };

// What a drop target carries. A section body appends (the exact slot is computed
// from the pointer at drop time); there is no per-tab droppable, so reordering is
// pointer-precise and keyboard drops append.
export type PanelDropData = { kind: "section-body"; subSection: SubSectionId };

// Sentinel "insert at the end" index: clamped by displayedPanelIdsAtom for the live
// ghost and mapped to `undefined` (splice at length) for the real move on drop.
export const APPEND_INDEX = Number.MAX_SAFE_INTEGER;

// Droppable id for a sub-section's body (the in-grid drop target).
export function sectionBodyDroppableId(subSection: SubSectionId): string {
  return `section-body:${subSection}`;
}

// Droppable id for a section's header toggle (the collapsed-section drop target).
// Distinct from the body id so an expanded section can carry both without a clash;
// both resolve to the same move (into the section's primary sub-section).
export function sectionToggleDroppableId(section: SectionId): string {
  return `section-toggle:${section}`;
}

export function sectionToggleDropData(section: SectionId): PanelDropData {
  return { kind: "section-body", subSection: primaryOf(section) };
}
