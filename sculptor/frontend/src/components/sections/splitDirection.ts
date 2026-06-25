// The (section, axis) → user-facing direction word that labels the panel right-click
// "Create {direction} split and move panel" option.
//
// A split always moves the chosen panel into the section's SECONDARY sub-section, and
// SplittableSection renders the secondary below the primary for a horizontal divider
// (stacked) or to the right for a vertical divider (side-by-side). So the direction
// word is fixed per axis — "bottom" for horizontal, "right" for vertical — and the
// per-section allowed directions follow allowedSplitAxesForSection (left/right →
// bottom only; bottom → right only; center → both).

import type { SectionId, SplitAxis } from "./sectionTypes.ts";
import { allowedSplitAxesForSection } from "./sectionTypes.ts";

export type SplitDirectionOption = { axis: SplitAxis; label: string };

export function splitDirectionLabel(axis: SplitAxis): string {
  return axis === "horizontal" ? "bottom" : "right";
}

export function splitDirectionOptionsForSection(section: SectionId): ReadonlyArray<SplitDirectionOption> {
  return allowedSplitAxesForSection(section).map((axis) => ({ axis, label: splitDirectionLabel(axis) }));
}
