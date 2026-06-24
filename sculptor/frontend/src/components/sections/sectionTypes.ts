// Core types and pure helpers for the workspace section/sub-section keyspace.
//
// There are four sections (left | center | right | bottom). Each section may be
// split into exactly two sub-sections. A panel always lives inside a sub-section.
// The keyspace is flat: an unsplit section's single sub-section id IS the section
// id (the "primary"); a split section gains a "secondary" half suffixed with
// `:secondary` (e.g. `left:secondary`). The primary and secondary halves run
// through identical machinery, so there is no `:primary` suffix.
//
// This module is pure: no React, no Jotai, no DOM. It is imported by the layout
// atoms, the registry, and the section components.

export type SectionId = "left" | "center" | "right" | "bottom";

export type SubSectionId = SectionId | `${SectionId}:secondary`;

// A panel id is either a static id (e.g. "files") or a dynamic id embedding the
// task/terminal identity (e.g. "agent:<taskId>" / "terminal:<wsId>:<n>").
export type PanelId = string;

// A horizontal divider stacks the halves top/bottom; a vertical divider places
// them side-by-side left/right.
export type SplitAxis = "horizontal" | "vertical";

// `ratio` is the primary half's fraction of the section (0..1).
export type SectionSplit = { axis: SplitAxis; ratio: number };

export const SECTION_IDS: ReadonlyArray<SectionId> = ["left", "center", "right", "bottom"];

const SECONDARY_SUFFIX = ":secondary";

export function isSectionId(value: unknown): value is SectionId {
  return value === "left" || value === "center" || value === "right" || value === "bottom";
}

export function toSecondary(section: SectionId): SubSectionId {
  return `${section}${SECONDARY_SUFFIX}`;
}

export function toSection(subSection: SubSectionId): SectionId {
  const index = subSection.indexOf(SECONDARY_SUFFIX);
  return (index === -1 ? subSection : subSection.slice(0, index)) as SectionId;
}

export function isSecondary(subSection: SubSectionId): boolean {
  return subSection.endsWith(SECONDARY_SUFFIX);
}

// The primary sub-section id is the section id itself; provided for symmetry.
export function primaryOf(section: SectionId): SubSectionId {
  return section;
}

// Split-direction rules (goals.md → "Split sections"): left/right split top/bottom
// (horizontal divider), bottom splits left/right (vertical divider), center allows
// either direction.
export function allowedSplitAxesForSection(section: SectionId): ReadonlyArray<SplitAxis> {
  switch (section) {
    case "left":
    case "right":
      return ["horizontal"];
    case "bottom":
      return ["vertical"];
    case "center":
      return ["horizontal", "vertical"];
  }
}

export function canSplitAxis(section: SectionId, axis: SplitAxis): boolean {
  return allowedSplitAxesForSection(section).includes(axis);
}
