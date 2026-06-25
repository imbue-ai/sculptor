// Pure geometry for the four-section grid: resolve the global section size
// percentages to pixels, protecting the center's larger minimum width by shrinking
// the sides first (right before left). No React, no Jotai — unit-testable in
// isolation.

import type { GlobalLayoutState } from "./persistence/types.ts";

// The center keeps a larger minimum width; the sides have a smaller floor and give
// way before the center shrinks.
export const CENTER_MIN_WIDTH_PX = 400;
export const SIDE_MIN_WIDTH_PX = 150;
export const BOTTOM_MIN_HEIGHT_PX = 100;
// Each visible vertical resize handle occupies this much width in the top row.
export const RESIZE_HANDLE_PX = 1;

// Section size percentages are clamped to this range when a resize writes them.
export const SECTION_SIZE_MIN_PERCENT = 5;
export const SECTION_SIZE_MAX_PERCENT = 80;

export type SectionPixelSizes = { leftPx: number; rightPx: number; bottomPx: number };

export type ResolveSectionSizesParams = {
  containerWidth: number;
  containerHeight: number;
  sizes: GlobalLayoutState["sectionSizes"];
  isLeftExpanded: boolean;
  isRightExpanded: boolean;
  isBottomExpanded: boolean;
};

export function resolveSectionPixelSizes(params: ResolveSectionSizesParams): SectionPixelSizes {
  const { containerWidth, containerHeight, sizes, isLeftExpanded, isRightExpanded, isBottomExpanded } = params;

  let leftPx = isLeftExpanded ? Math.max(SIDE_MIN_WIDTH_PX, Math.round((sizes.left / 100) * containerWidth)) : 0;
  let rightPx = isRightExpanded ? Math.max(SIDE_MIN_WIDTH_PX, Math.round((sizes.right / 100) * containerWidth)) : 0;

  if (containerWidth > 0) {
    const handleWidth = ((isLeftExpanded ? 1 : 0) + (isRightExpanded ? 1 : 0)) * RESIZE_HANDLE_PX;
    let deficit = leftPx + rightPx + CENTER_MIN_WIDTH_PX + handleWidth - containerWidth;
    // Sides give way before the center shrinks: take it from the right side first.
    if (deficit > 0 && isRightExpanded) {
      const reduction = Math.min(deficit, rightPx - SIDE_MIN_WIDTH_PX);
      rightPx -= reduction;
      deficit -= reduction;
    }

    if (deficit > 0 && isLeftExpanded) {
      const reduction = Math.min(deficit, leftPx - SIDE_MIN_WIDTH_PX);
      leftPx -= reduction;
    }
  }

  const bottomPx = isBottomExpanded
    ? Math.max(BOTTOM_MIN_HEIGHT_PX, Math.round((sizes.bottom / 100) * containerHeight))
    : 0;

  return { leftPx, rightPx, bottomPx };
}

// Convert a dragged pixel size back to a clamped global percentage of its axis.
export function sizeToPercent(px: number, dimension: number): number {
  if (dimension <= 0) {
    return SECTION_SIZE_MIN_PERCENT;
  }
  return Math.max(SECTION_SIZE_MIN_PERCENT, Math.min(SECTION_SIZE_MAX_PERCENT, (px / dimension) * 100));
}
