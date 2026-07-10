import type { CollisionDetection } from "@dnd-kit/core";
import { describe, expect, it } from "vitest";

import { sidebarCollisionDetection } from "./sidebarDnd.ts";

type CollisionArgs = Parameters<CollisionDetection>[0];
type TestRect = { left: number; top: number; width: number; height: number; right: number; bottom: number };

const rect = (left: number, top: number, width: number, height: number): TestRect => ({
  left,
  top,
  width,
  height,
  right: left + width,
  bottom: top + height,
});

// The collision keys off the dragged element's (modifier-clamped) collisionRect, not the
// pointer, so each case passes the rect the dragged item currently occupies and a non-null
// pointer just to select the pointer-drag branch. `rects` is the droppable layout.
const buildArgs = (
  collisionRect: TestRect,
  rects: Map<string, TestRect>,
  pointer: { x: number; y: number } | null = { x: 0, y: 0 },
): CollisionArgs =>
  ({
    active: { id: "active", rect: { current: { initial: null, translated: collisionRect } }, data: { current: {} } },
    collisionRect,
    droppableRects: rects,
    droppableContainers: [...rects.keys()].map((id) => ({ id, rect: { current: rects.get(id) } })),
    pointerCoordinates: pointer,
  }) as unknown as CollisionArgs;

// A tall expanded group (height 400) stacked above a short single-workspace group (height
// 40). restrictToParentElement lets the tall group slide down by at most the short group's
// height (40px) before its bottom hits the list bottom.
const tallOverShort = new Map([
  ["tall", rect(0, 0, 250, 400)],
  ["short", rect(0, 400, 250, 40)],
]);

describe("sidebarCollisionDetection", () => {
  it("keeps a small drag of a tall group on itself (below the crossover)", () => {
    // Dragged down 10px: the tall group still covers almost all of its own slot, far more
    // (as a fraction) than the sliver it covers of the short neighbour. over stays on self,
    // which the drag-end handler treats as a no-op.
    const collisions = sidebarCollisionDetection(buildArgs(rect(0, 10, 250, 400), tallOverShort));
    expect(collisions[0]?.id).toBe("tall");
  });

  it("flips a tall group onto a short neighbour after about one of the neighbour's rows", () => {
    // Dragged down to its clamp limit (40px, one short-row): the short neighbour is fully
    // covered (fraction 1.0) and wins over the tall group's now-vacated slot. closestCenter
    // could never reach this — the tall group's centre never nears the short one's.
    const collisions = sidebarCollisionDetection(buildArgs(rect(0, 40, 250, 400), tallOverShort));
    expect(collisions[0]?.id).toBe("short");
  });

  it("flips equal-height rows at half a row, like closestCenter", () => {
    const rows = new Map([
      ["a", rect(0, 0, 250, 40)],
      ["b", rect(0, 40, 250, 40)],
    ]);
    // Row "a" dragged down 15px (< half): still mostly over its own slot.
    expect(sidebarCollisionDetection(buildArgs(rect(0, 15, 250, 40), rows))[0]?.id).toBe("a");
    // Dragged down 25px (> half): now mostly over "b".
    expect(sidebarCollisionDetection(buildArgs(rect(0, 25, 250, 40), rows))[0]?.id).toBe("b");
  });

  it("never returns empty: a rect dragged clear of every item falls back to nearest centre", () => {
    // Overlapping nothing (e.g. clamped into blank space) must still resolve, or `over` goes
    // null and dnd-kit snaps the dragged item back to its origin. closestCenter resolves to
    // the nearest item — the short group, whose centre is closest to the rect below it.
    const collisions = sidebarCollisionDetection(buildArgs(rect(0, 500, 250, 400), tallOverShort));
    expect(collisions[0]?.id).toBe("short");
  });

  it("resolves a keyboard drag (no pointer) via closestCenter", () => {
    // With no pointer coordinates the sortable keyboard getter has already stepped the
    // dragged rect onto the target slot; closestCenter resolves it by centre distance.
    const collisions = sidebarCollisionDetection(buildArgs(rect(0, 40, 250, 400), tallOverShort, null));
    expect(collisions[0]?.id).toBe("tall");
  });
});
