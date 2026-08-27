// Geometry for a hover "safe area" (a.k.a. the mega-menu "safe triangle").
//
// When a popover opens on hover, the pointer must travel from the trigger to the
// popover — and on the way it crosses empty space: the gap directly below the
// trigger, and (when the popover is wider than the trigger) the band beside it.
// A flat close-delay reads that empty space as "the pointer left the menu" and
// dismisses the popover mid-approach, forcing the user to move in a precise
// straight line.
//
// The safe area is the triangle whose apex is where the pointer left the trigger
// and whose base is the popover's near edge. While the pointer stays inside it,
// the pointer is plausibly still heading for the popover, so the close is held
// off; once it leaves the triangle it is treated as moving away and the popover
// closes. This lets the user cut a lazy diagonal toward the popover's center
// without the popover snapping shut.

export type Point = { x: number; y: number };

// apex → the point where the pointer left the trigger; the other two are the
// corners of the popover's near edge.
export type SafeTriangle = readonly [Point, Point, Point];

// Builds the safe triangle from the apex (the pointer's exit point) to the
// popover's near horizontal edge — its top when the popover sits below the apex,
// its bottom when it sits above (Radix flips the menu to the other side on
// collision). The NEAR edge is used, not the far edge, so the triangle is the
// smallest wedge that still fully spans the approach corridor.
//
// `basePadding` extends the base outward at each end so a slightly wobbly approach
// that drifts just past the popover's width still reads as heading toward it.
export const buildSafeTriangle = (apex: Point, popover: DOMRect, basePadding = 0): SafeTriangle => {
  const nearEdgeY = apex.y <= popover.top ? popover.top : popover.bottom;
  return [apex, { x: popover.left - basePadding, y: nearEdgeY }, { x: popover.right + basePadding, y: nearEdgeY }];
};

// Standard barycentric-sign point-in-triangle test, inclusive of the edges so a
// pointer skimming the boundary still counts as "heading toward the popover".
export const isPointInTriangle = (p: Point, triangle: SafeTriangle): boolean => {
  const [a, b, c] = triangle;
  const cross = (p1: Point, p2: Point, p3: Point): number =>
    (p1.x - p3.x) * (p2.y - p3.y) - (p2.x - p3.x) * (p1.y - p3.y);
  const d1 = cross(p, a, b);
  const d2 = cross(p, b, c);
  const d3 = cross(p, c, a);
  const hasNeg = d1 < 0 || d2 < 0 || d3 < 0;
  const hasPos = d1 > 0 || d2 > 0 || d3 > 0;
  // Inside (or on an edge) iff the cross-products never disagree in sign; a zero
  // means the point lies exactly on that edge, which still counts as inside.
  return !(hasNeg && hasPos);
};
