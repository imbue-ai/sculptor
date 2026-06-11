import type { ZoneId } from "~/components/panels/types.ts";

/** A direction for Ctrl+Alt+Arrow pane focus navigation. */
export type PaneDirection = "left" | "right" | "up" | "down";

/** A section's zone id paired with its on-screen rectangle. */
export type ZoneRect = {
  zone: ZoneId;
  /** Bounding box in viewport coordinates (DOMRect-shaped). */
  rect: { left: number; top: number; right: number; bottom: number; width: number; height: number };
};

const centerOf = (r: ZoneRect["rect"]): { x: number; y: number } => ({
  x: (r.left + r.right) / 2,
  y: (r.top + r.bottom) / 2,
});

/**
 * Pick the best section to move focus to from `currentZone` in `direction`,
 * using each section's geometry. Center-based directional scoring: a candidate
 * must lie predominantly in the requested direction (its dominant axis matches),
 * and among those we pick the nearest, penalising perpendicular offset so the
 * most aligned neighbour wins. Geometry-driven (not a hardcoded grid) so it
 * handles split sub-sections without special cases. Returns null when nothing
 * lies in that direction (the caller leaves focus where it is).
 */
export const pickNeighborZone = (
  rects: ReadonlyArray<ZoneRect>,
  currentZone: ZoneId,
  direction: PaneDirection,
): ZoneId | null => {
  const current = rects.find((r) => r.zone === currentZone);
  if (!current) return null;
  const from = centerOf(current.rect);

  let best: { zone: ZoneId; score: number } | null = null;
  for (const candidate of rects) {
    if (candidate.zone === currentZone) continue;
    const to = centerOf(candidate.rect);
    const dx = to.x - from.x;
    const dy = to.y - from.y;

    // Distance along the travel axis (must be positive in the chosen direction)
    // and the perpendicular offset, which is penalised so aligned panes win.
    let along: number;
    let perpendicular: number;
    switch (direction) {
      case "left":
        along = -dx;
        perpendicular = Math.abs(dy);
        break;
      case "right":
        along = dx;
        perpendicular = Math.abs(dy);
        break;
      case "up":
        along = -dy;
        perpendicular = Math.abs(dx);
        break;
      case "down":
        along = dy;
        perpendicular = Math.abs(dx);
        break;
    }

    // Must move in the requested direction, and do so more along the travel axis
    // than across it (so e.g. a pane mostly below isn't chosen for "left").
    if (along <= 0 || along < perpendicular) continue;

    const score = along + perpendicular * 2;
    if (best === null || score < best.score) {
      best = { zone: candidate.zone, score };
    }
  }

  return best?.zone ?? null;
};

/**
 * All on-screen sections in reading order — top-to-bottom by row, then
 * left-to-right within a row — used for the left/right arrows that cycle linearly
 * through every pane.
 */
export const orderZonesForCycle = (rects: ReadonlyArray<ZoneRect>): ReadonlyArray<ZoneId> =>
  [...rects].sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left).map((z) => z.zone);

/**
 * The next (`delta: 1`) or previous (`delta: -1`) zone from `currentZone` in the
 * cycle order, wrapping around the ends so the left/right arrows step through
 * every pane. Falls back to the first zone when `currentZone` isn't on screen,
 * and returns null when there are no zones.
 */
export const cycleZone = (rects: ReadonlyArray<ZoneRect>, currentZone: ZoneId, delta: 1 | -1): ZoneId | null => {
  const order = orderZonesForCycle(rects);
  if (order.length === 0) return null;
  const index = order.indexOf(currentZone);
  if (index === -1) return order[0];
  return order[(index + delta + order.length) % order.length];
};
