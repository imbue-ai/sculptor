/**
 * Spotlight color palette — the rotating hues that visually bind a spotlight
 * chip to its line-range highlight (and, later, its gutter bar). These are
 * IDENTITY colors (they distinguish spotlight A from spotlight B), NOT SEMANTIC
 * status colors, so they are deliberately hardcoded here rather than drawn from
 * the theme tokens (goal file Q2). Every value below is meant to be tuned in
 * this one place.
 */

import type { SpotlightAnchor } from "./types.ts";

/**
 * Eight hues stepping periwinkle-blue → teal (215° → 155°), staying in the
 * blue/teal band well clear of diff red. Saturation and lightness are held
 * constant so all eight read as equally vibrant; only the hue rotates.
 */
export const SPOTLIGHT_HUES: ReadonlyArray<number> = [215, 206, 198, 189, 181, 172, 164, 155];
export const SPOTLIGHT_SATURATION_PERCENT = 72;
export const SPOTLIGHT_LIGHTNESS_PERCENT = 56;
/** Alpha for the full-row line highlight; the solid gutter bar / chip accent uses no alpha. */
export const SPOTLIGHT_HIGHLIGHT_ALPHA = 0.18;

/**
 * Stable string identity of an anchor — the basis for its deterministic color.
 * NOTE: when the two-range representational refactor lands, this becomes
 * `file | previousRange | currentRange | scope.kind | commitHash`; today it
 * keys on the single {file, lineStart, lineEnd} anchor.
 */
const anchorIdentity = (anchor: SpotlightAnchor): string => `${anchor.file}|${anchor.lineStart}-${anchor.lineEnd}`;

/** djb2 string hash → non-negative integer. */
const hashString = (value: string): number => {
  let hash = 5381;
  for (let index = 0; index < value.length; index++) {
    hash = ((hash << 5) + hash + value.charCodeAt(index)) | 0;
  }
  return Math.abs(hash);
};

/**
 * The palette index a spotlight owns. Deterministic in the anchor identity, so
 * the chip and its hover-highlight (and, later, its gutter bar) all resolve to
 * the SAME color with zero threading and nothing stored on the data model — the
 * palette is an identity projection, not a persisted field (represent-reality).
 */
export const spotlightColorIndex = (anchor: SpotlightAnchor): number =>
  hashString(anchorIdentity(anchor)) % SPOTLIGHT_HUES.length;

const hueAt = (index: number): number =>
  SPOTLIGHT_HUES[((index % SPOTLIGHT_HUES.length) + SPOTLIGHT_HUES.length) % SPOTLIGHT_HUES.length];

/** Solid color for a spotlight's chip accent (and, later, its gutter bar). */
export const spotlightBarColor = (index: number): string =>
  `hsl(${hueAt(index)} ${SPOTLIGHT_SATURATION_PERCENT}% ${SPOTLIGHT_LIGHTNESS_PERCENT}%)`;

/** Translucent color for a spotlight's full-row line highlight. */
export const spotlightHighlightColor = (index: number): string =>
  `hsl(${hueAt(index)} ${SPOTLIGHT_SATURATION_PERCENT}% ${SPOTLIGHT_LIGHTNESS_PERCENT}% / ${SPOTLIGHT_HIGHLIGHT_ALPHA})`;
