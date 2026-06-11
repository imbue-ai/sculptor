import { describe, expect, it } from "vitest";

import type { ZoneRect } from "~/components/panels/paneNavigation.ts";
import { cycleZone, orderZonesForCycle, pickNeighborZone } from "~/components/panels/paneNavigation.ts";
import type { ZoneId } from "~/components/panels/types.ts";

/** Build a ZoneRect from edges (width/height derived). */
const r = (zone: ZoneId, left: number, top: number, right: number, bottom: number): ZoneRect => ({
  zone,
  rect: { left, top, right, bottom, width: right - left, height: bottom - top },
});

// A standard compact layout: [left | center | right] across the top row (y 0–400)
// with a full-width bottom bar (y 400–600).
const LAYOUT: ReadonlyArray<ZoneRect> = [
  r("top-left", 0, 0, 200, 400),
  r("center", 200, 0, 600, 400),
  r("top-right", 600, 0, 800, 400),
  r("bottom", 0, 400, 800, 600),
];

describe("pickNeighborZone", () => {
  it("moves left/right across the top row through the center", () => {
    expect(pickNeighborZone(LAYOUT, "center", "left")).toBe("top-left");
    expect(pickNeighborZone(LAYOUT, "center", "right")).toBe("top-right");
    expect(pickNeighborZone(LAYOUT, "top-left", "right")).toBe("center");
    expect(pickNeighborZone(LAYOUT, "top-right", "left")).toBe("center");
  });

  it("moves down from the top row into the bottom bar, and back up to the aligned section", () => {
    expect(pickNeighborZone(LAYOUT, "center", "down")).toBe("bottom");
    // Bottom is full-width; "up" should pick the horizontally-aligned center.
    expect(pickNeighborZone(LAYOUT, "bottom", "up")).toBe("center");
  });

  it("returns null when there is no pane in the requested direction", () => {
    expect(pickNeighborZone(LAYOUT, "center", "up")).toBeNull();
    expect(pickNeighborZone(LAYOUT, "top-left", "left")).toBeNull();
    expect(pickNeighborZone(LAYOUT, "bottom", "down")).toBeNull();
  });

  it("returns null when the current zone isn't on screen", () => {
    expect(pickNeighborZone(LAYOUT, "center:split", "left")).toBeNull();
  });

  it("prefers the nearer sub-section when a section is split", () => {
    // Center split horizontally into a top half (0–200) and a :split bottom half
    // (200–400), above the bottom bar.
    const split: ReadonlyArray<ZoneRect> = [
      r("top-left", 0, 0, 200, 400),
      r("center", 200, 0, 600, 200),
      r("center:split", 200, 200, 600, 400),
      r("top-right", 600, 0, 800, 400),
      r("bottom", 0, 400, 800, 600),
    ];
    // From the top half, down lands on the nearer split half (not the bottom bar).
    expect(pickNeighborZone(split, "center", "down")).toBe("center:split");
    // From the split half, down continues to the bottom bar.
    expect(pickNeighborZone(split, "center:split", "down")).toBe("bottom");
  });
});

describe("cycleZone / orderZonesForCycle", () => {
  it("orders panes top-to-bottom by row, then left-to-right within a row", () => {
    expect(orderZonesForCycle(LAYOUT)).toEqual(["top-left", "center", "top-right", "bottom"]);
  });

  it("steps forward through every pane and wraps at the end", () => {
    expect(cycleZone(LAYOUT, "top-left", 1)).toBe("center");
    expect(cycleZone(LAYOUT, "center", 1)).toBe("top-right");
    expect(cycleZone(LAYOUT, "top-right", 1)).toBe("bottom");
    // Wrap: the last pane cycles back to the first.
    expect(cycleZone(LAYOUT, "bottom", 1)).toBe("top-left");
  });

  it("steps backward and wraps at the start", () => {
    expect(cycleZone(LAYOUT, "center", -1)).toBe("top-left");
    expect(cycleZone(LAYOUT, "top-left", -1)).toBe("bottom");
  });

  it("returns the same single pane (no-op) and handles an unknown current zone", () => {
    const solo: ReadonlyArray<ZoneRect> = [r("center", 0, 0, 800, 600)];
    expect(cycleZone(solo, "center", 1)).toBe("center");
    // Unknown current zone falls back to the first pane.
    expect(cycleZone(LAYOUT, "center:split", 1)).toBe("top-left");
  });
});
