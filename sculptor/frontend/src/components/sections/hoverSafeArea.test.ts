import { describe, expect, it } from "vitest";

import { buildSafeTriangle, isPointInTriangle } from "./hoverSafeArea.ts";

// Minimal DOMRect stub: buildSafeTriangle only reads left/right/top/bottom.
const rect = (over: Partial<DOMRect>): DOMRect => ({
  left: 0,
  right: 0,
  top: 0,
  bottom: 0,
  width: 0,
  height: 0,
  x: 0,
  y: 0,
  toJSON: () => "",
  ...over,
});

describe("buildSafeTriangle", () => {
  it("bases the triangle on the popover's TOP edge when the popover is below the apex", () => {
    const apex = { x: 100, y: 50 };
    const popover = rect({ left: 100, right: 420, top: 60, bottom: 300 });

    const [a, b, c] = buildSafeTriangle(apex, popover);

    expect(a).toEqual(apex);
    expect(b).toEqual({ x: 100, y: 60 });
    expect(c).toEqual({ x: 420, y: 60 });
  });

  it("bases the triangle on the popover's BOTTOM edge when the popover is above the apex (collision flip)", () => {
    const apex = { x: 100, y: 300 };
    const popover = rect({ left: 100, right: 420, top: 40, bottom: 260 });

    const [, b, c] = buildSafeTriangle(apex, popover);

    expect(b).toEqual({ x: 100, y: 260 });
    expect(c).toEqual({ x: 420, y: 260 });
  });

  it("widens the base outward by basePadding at each end (wobble tolerance)", () => {
    const apex = { x: 100, y: 50 };
    const popover = rect({ left: 100, right: 420, top: 60, bottom: 300 });

    const [, b, c] = buildSafeTriangle(apex, popover, 20);

    expect(b).toEqual({ x: 80, y: 60 });
    expect(c).toEqual({ x: 440, y: 60 });
  });
});

describe("isPointInTriangle", () => {
  const triangle = buildSafeTriangle({ x: 0, y: 0 }, rect({ left: -10, right: 10, top: 10, bottom: 20 }));

  it("counts the apex and base corners as inside (edges are inclusive)", () => {
    expect(isPointInTriangle({ x: 0, y: 0 }, triangle)).toBe(true);
    expect(isPointInTriangle({ x: -10, y: 10 }, triangle)).toBe(true);
    expect(isPointInTriangle({ x: 10, y: 10 }, triangle)).toBe(true);
  });

  it("counts a point in the interior as inside", () => {
    expect(isPointInTriangle({ x: 0, y: 5 }, triangle)).toBe(true);
  });

  it("counts a point outside the wedge as outside", () => {
    // Level with the apex but off to the side: the triangle only opens downward.
    expect(isPointInTriangle({ x: 8, y: 0 }, triangle)).toBe(false);
    // Below the base edge, past the popover.
    expect(isPointInTriangle({ x: 0, y: 25 }, triangle)).toBe(false);
  });

  describe("the reported bug scenario: tiny trigger, wide popover below it", () => {
    // A `+` button whose bottom-left is ~(100, 60); the popover is left-aligned
    // to it, 320px wide, and starts 4px below (Radix sideOffset). The pointer
    // leaves the button at its bottom edge.
    const apex = { x: 108, y: 60 };
    const popover = rect({ left: 100, right: 420, top: 64, bottom: 300 });
    const safeArea = buildSafeTriangle(apex, popover);

    // The menu is held open when the pointer is either still crossing the gap
    // (inside the safe triangle) OR already over the popover (where the content's
    // own pointer-enter keeps it open). The triangle only has to bridge the gap;
    // the popover covers the rest. This union is the "no dead zone" region.
    const inPopover = (p: { x: number; y: number }): boolean =>
      p.x >= popover.left && p.x <= popover.right && p.y >= popover.top && p.y <= popover.bottom;
    const isHeldOpen = (p: { x: number; y: number }): boolean => isPointInTriangle(p, safeArea) || inPopover(p);

    it("has no dead zone along a slow straight-down move (bug #1: the 4px gap)", () => {
      // Every step from the button's edge down into the popover keeps it open.
      for (let y = apex.y; y <= 200; y += 1) {
        expect(isHeldOpen({ x: apex.x, y })).toBe(true);
      }
    });

    it("has no dead zone along a lazy diagonal toward the popover's center (bug #2)", () => {
      const center = { x: (popover.left + popover.right) / 2, y: (popover.top + popover.bottom) / 2 };
      for (let t = 0; t <= 1; t += 0.02) {
        const p = { x: apex.x + (center.x - apex.x) * t, y: apex.y + (center.y - apex.y) * t };
        expect(isHeldOpen(p)).toBe(true);
      }
    });

    it("closes on a purely-horizontal move along the header (away from the popover)", () => {
      // Same y as the apex (above the popover's top edge), sliding right toward
      // other header controls — the user is not heading for the popover, so this
      // is neither in the triangle nor over the popover and the menu should close.
      expect(isHeldOpen({ x: 200, y: 60 })).toBe(false);
      expect(isHeldOpen({ x: 300, y: 62 })).toBe(false);
    });
  });
});
