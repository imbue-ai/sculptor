/**
 * Spotlight color palette — the rotating hues that visually bind a spotlight
 * chip to its line-range highlight (and, later, its gutter bar). These are
 * IDENTITY colors (they distinguish spotlight A from spotlight B), NOT SEMANTIC
 * status colors, so they are deliberately hardcoded here rather than drawn from
 * the theme tokens (goal file Q2). Every value below is meant to be tuned in
 * this one place.
 */

import type { LineRange, SpotlightAnchor } from "./types.ts";

/**
 * Six hues spread across the colour wheel for maximum visual distance — blue,
 * purple, orange, green, gold, and pink — so no two adjacent spotlight colours
 * are confusable. Saturation and lightness are held constant so all six read as
 * equally vibrant; only the hue rotates.
 */
export const SPOTLIGHT_HUES: ReadonlyArray<number> = [215, 270, 25, 145, 50, 320];
export const SPOTLIGHT_SATURATION_PERCENT = 72;
export const SPOTLIGHT_LIGHTNESS_PERCENT = 56;
/** Alpha for the full-row line highlight; the solid gutter bar / chip accent uses no alpha. */
export const SPOTLIGHT_HIGHLIGHT_ALPHA = 0.18;
/** Fixed hover-highlight colour — always blue, not palette-rotated. */
export const SPOTLIGHT_HOVER_HUE = 215;
/** Translucent colour for a spotlight's full-row line highlight. */
export const spotlightHoverHighlightColor = (): string =>
  `hsl(${SPOTLIGHT_HOVER_HUE} ${SPOTLIGHT_SATURATION_PERCENT}% ${SPOTLIGHT_LIGHTNESS_PERCENT}% / ${SPOTLIGHT_HIGHLIGHT_ALPHA})`;

/**
 * Stable string identity of an anchor — the basis for its deterministic color.
 * Keys on the file, both side-ranges, and the scope so two spotlights on the
 * same lines from different panes still read as distinct.
 */
export const anchorIdentity = (anchor: SpotlightAnchor): string => {
  const range = (r: LineRange | null): string => (r ? `${r.firstLine}-${r.lastLine}` : "");
  const commit = anchor.scope.kind === "commit-diff" ? anchor.scope.commitHash : "";
  return `${anchor.file}|${range(anchor.previousFileLines)}|${range(anchor.currentFileLines)}|${anchor.scope.kind}|${commit}`;
};

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
 *
 * When `resolvedMap` is supplied (collision resolution from the full draft
 * anchor set), its entry wins over the raw hash — so two chips that would
 * collide are spread across neighbouring slots, and every consumer that calls
 * this with the same map sees the same resolved colour. Without a map (e.g. a
 * sent-message chip, or a one-off call site), the raw hash index is the
 * fallback.
 */
export const spotlightColorIndex = (anchor: SpotlightAnchor, resolvedMap?: ReadonlyMap<string, number>): number => {
  if (resolvedMap) {
    const resolved = resolvedMap.get(anchorIdentity(anchor));
    if (resolved !== undefined) return resolved;
  }
  return hashString(anchorIdentity(anchor)) % SPOTLIGHT_HUES.length;
};

/**
 * Build a collision-resolved index map for a set of draft anchors. Each anchor
 * is assigned its hash-preferred index; when that slot is already taken by an
 * earlier anchor, the index steps forward (wrapping) until a free slot is found.
 * With 6 palette slots, up to 6 distinct anchors each receive a unique colour
 * before the resolver saturates and falls back to the raw hash. The order in
 * which anchors appear in the array determines priority — draft order (document
 * position) is the natural tiebreaker.
 */
export const resolveColorMap = (anchors: ReadonlyArray<SpotlightAnchor>): Map<string, number> => {
  const result = new Map<string, number>();
  const taken = new Set<number>();
  for (const anchor of anchors) {
    const identity = anchorIdentity(anchor);
    if (result.has(identity)) continue;
    let index = hashString(identity) % SPOTLIGHT_HUES.length;
    let attempts = 0;
    while (taken.has(index) && attempts < SPOTLIGHT_HUES.length) {
      index = (index + 1) % SPOTLIGHT_HUES.length;
      attempts++;
    }
    taken.add(index);
    result.set(identity, index);
  }
  return result;
};

const hueAt = (index: number): number =>
  SPOTLIGHT_HUES[((index % SPOTLIGHT_HUES.length) + SPOTLIGHT_HUES.length) % SPOTLIGHT_HUES.length];

/** Solid color for a spotlight's chip accent (and, later, its gutter bar). */
export const spotlightBarColor = (index: number): string =>
  `hsl(${hueAt(index)} ${SPOTLIGHT_SATURATION_PERCENT}% ${SPOTLIGHT_LIGHTNESS_PERCENT}%)`;
