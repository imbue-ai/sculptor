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
// agent/terminal identity (e.g. "agent:<agentId>" / "terminal:<wsId>:<n>").
export type PanelId = string;

// A horizontal divider stacks the halves top/bottom; a vertical divider places
// them side-by-side left/right.
export type SplitAxis = "horizontal" | "vertical";

// `ratio` is the primary half's fraction of the section (0..1).
export type SectionSplit = { axis: SplitAxis; ratio: number };

export const SECTION_IDS: ReadonlyArray<SectionId> = ["left", "center", "right", "bottom"];

const SECONDARY_SUFFIX = ":secondary";

export const isSectionId = (value: unknown): value is SectionId => {
  return value === "left" || value === "center" || value === "right" || value === "bottom";
};

export const toSecondary = (section: SectionId): SubSectionId => {
  return `${section}${SECONDARY_SUFFIX}`;
};

export const toSection = (subSection: SubSectionId): SectionId => {
  const index = subSection.indexOf(SECONDARY_SUFFIX);
  return (index === -1 ? subSection : subSection.slice(0, index)) as SectionId;
};

export const isSecondary = (subSection: SubSectionId): boolean => {
  return subSection.endsWith(SECONDARY_SUFFIX);
};

// The primary sub-section id is the section id itself; provided for symmetry.
export const primaryOf = (section: SectionId): SubSectionId => {
  return section;
};

// Split-direction rules: left/right split top/bottom
// (horizontal divider), bottom splits left/right (vertical divider), center allows
// either direction.
export const allowedSplitAxesForSection = (section: SectionId): ReadonlyArray<SplitAxis> => {
  switch (section) {
    case "left":
    case "right":
      return ["horizontal"];
    case "bottom":
      return ["vertical"];
    case "center":
      return ["horizontal", "vertical"];
  }
};

export const canSplitAxis = (section: SectionId, axis: SplitAxis): boolean => {
  return allowedSplitAxesForSection(section).includes(axis);
};

// The (section, axis) → user-facing direction word that labels the panel right-click
// "Create {direction} split and move panel" option.
//
// A split always moves the chosen panel into the section's SECONDARY sub-section, and
// SplittableSection renders the secondary below the primary for a horizontal divider
// (stacked) or to the right for a vertical divider (side-by-side). So the direction
// word is fixed per axis — "bottom" for horizontal, "right" for vertical — and the
// per-section allowed directions follow allowedSplitAxesForSection (left/right →
// bottom only; bottom → right only; center → both).
export type SplitDirectionOption = { axis: SplitAxis; label: string };

export const splitDirectionLabel = (axis: SplitAxis): string => {
  return axis === "horizontal" ? "bottom" : "right";
};

export const splitDirectionOptionsForSection = (section: SectionId): ReadonlyArray<SplitDirectionOption> => {
  return allowedSplitAxesForSection(section).map((axis) => ({ axis, label: splitDirectionLabel(axis) }));
};
