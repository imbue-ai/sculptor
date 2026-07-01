import type { CollisionDetection } from "@dnd-kit/core";
import { afterEach, describe, expect, it } from "vitest";

import { panelCollisionDetection, resetKeyboardDropTarget, setKeyboardDropTarget } from "./panelDndKeyboard.ts";

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

// A tall left column and a short full-width bottom strip — the layout that made the
// left section's drop zone "bleed" into the bottom section under closestCenter.
const buildArgs = (pointer: { x: number; y: number } | null): CollisionArgs => {
  const rects = new Map([
    ["left", rect(0, 0, 150, 400)],
    ["bottom", rect(0, 400, 600, 100)],
  ]);
  const draggedRect = rect(40, 380, 70, 30);
  return {
    active: { id: "dragged", rect: { current: { initial: null, translated: draggedRect } }, data: { current: {} } },
    collisionRect: draggedRect,
    droppableRects: rects,
    droppableContainers: [
      { id: "left", rect: { current: rects.get("left") } },
      { id: "bottom", rect: { current: rects.get("bottom") } },
    ],
    pointerCoordinates: pointer,
  } as unknown as CollisionArgs;
};

afterEach(() => resetKeyboardDropTarget());

describe("panelCollisionDetection", () => {
  it("resolves a pointer drag to the droppable under the pointer, not the nearest center", () => {
    // The pointer sits inside the bottom strip. The dragged rect's center is actually
    // marginally closer to the tall left column's center, so closestCenter would have
    // picked "left" — leaving you unable to drop until you dragged deep into "bottom".
    // pointerWithin must resolve to "bottom".
    const collisions = panelCollisionDetection(buildArgs({ x: 75, y: 420 }));
    expect(collisions[0]?.id).toBe("bottom");
  });

  it("resolves to the droppable the pointer is over even near a shared edge", () => {
    // Just inside the left column, above the bottom strip.
    const collisions = panelCollisionDetection(buildArgs({ x: 75, y: 380 }));
    expect(collisions[0]?.id).toBe("left");
  });

  it("uses the keyboard-stepped target during a keyboard drag (no pointer)", () => {
    setKeyboardDropTarget("left");
    const collisions = panelCollisionDetection(buildArgs(null));
    expect(collisions[0]?.id).toBe("left");
  });
});
