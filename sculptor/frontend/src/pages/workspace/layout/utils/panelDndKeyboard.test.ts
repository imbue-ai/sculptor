import type { CollisionDetection, KeyboardCoordinateGetter } from "@dnd-kit/core";
import { afterEach, describe, expect, it } from "vitest";

import {
  panelCollisionDetection,
  panelKeyboardCoordinateGetter,
  resetKeyboardDropTarget,
  setKeyboardDropTarget,
} from "./panelDndKeyboard.ts";

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

  it("falls back to rectIntersection when the pointer sits in a gap between droppables", () => {
    // Pointer in the empty area right of the left column and above the bottom strip:
    // pointerWithin finds nothing, so the drag still resolves by rect overlap (the
    // dragged rect overlaps the left column more than the bottom strip).
    const collisions = panelCollisionDetection(buildArgs({ x: 300, y: 200 }));
    expect(collisions[0]?.id).toBe("left");
  });

  it("ignores a stale keyboard target once a pointer drag resumes", () => {
    // A leftover keyboard target must not hijack a pointer drag: with pointer coordinates
    // present, resolution goes through pointerWithin, not the recorded keyboard target.
    setKeyboardDropTarget("left");
    const collisions = panelCollisionDetection(buildArgs({ x: 75, y: 420 }));
    expect(collisions[0]?.id).toBe("bottom");
  });
});

describe("panelKeyboardCoordinateGetter", () => {
  // A three-across top row over a full-width bottom strip — the sections the getter
  // steps between. Rects are held by name so tests assert against them without
  // re-deriving the geometry.
  const topLeft = rect(0, 0, 200, 560);
  const topCenter = rect(200, 0, 600, 560);
  const topRight = rect(800, 0, 200, 560);
  const bottomRow = rect(0, 560, 1000, 240);
  const topRowLayout = new Map([
    ["top-left", topLeft],
    ["top-center", topCenter],
    ["top-right", topRight],
    ["bottom", bottomRow],
  ]);

  // Where the getter parks a dragged 70×30 tab pill: centered inside a section.
  const centeredIn = (section: TestRect): TestRect =>
    rect(section.left + section.width / 2 - 35, section.top + section.height / 2 - 15, 70, 30);

  const stepGetter = (code: string, collisionRect: TestRect): ReturnType<typeof panelKeyboardCoordinateGetter> =>
    panelKeyboardCoordinateGetter(
      { code, preventDefault: () => {} } as unknown as KeyboardEvent,
      {
        active: "dragged",
        currentCoordinates: { x: collisionRect.left, y: collisionRect.top },
        context: {
          active: {
            id: "dragged",
            rect: { current: { initial: null, translated: collisionRect } },
            data: { current: {} },
          },
          collisionRect,
          droppableRects: topRowLayout,
          droppableContainers: {
            getEnabled: () => [...topRowLayout.keys()].map((id) => ({ id, disabled: false })),
          },
        },
      } as unknown as Parameters<KeyboardCoordinateGetter>[1],
    );

  it("steps to the section in the pressed direction from a centered start", () => {
    const start = centeredIn(topCenter);
    const cases: ReadonlyArray<[string, string, TestRect]> = [
      ["ArrowLeft", "top-left", topLeft],
      ["ArrowRight", "top-right", topRight],
      ["ArrowDown", "bottom", bottomRow],
    ];
    for (const [code, expectedId, target] of cases) {
      // Reset the recorded target to the occupied section before each press so the
      // getter steps out of "top-center" rather than re-selecting a prior step.
      setKeyboardDropTarget("top-center");
      expect(stepGetter(code, start)).toEqual({ x: centeredIn(target).left, y: centeredIn(target).top });
      // The getter records the section it stepped to for the collision detection.
      expect(panelCollisionDetection(buildArgs(null))[0]?.id).toBe(expectedId);
    }
  });

  it("returns to the top row on a Down-then-Up round trip", () => {
    const topCenterStart = centeredIn(topCenter);
    setKeyboardDropTarget("top-center");

    // Down parks the item in the full-width bottom strip…
    expect(stepGetter("ArrowDown", topCenterStart)).toEqual({
      x: centeredIn(bottomRow).left,
      y: centeredIn(bottomRow).top,
    });
    expect(panelCollisionDetection(buildArgs(null))[0]?.id).toBe("bottom");

    // …and Up steps straight back to the section it came from rather than a no-op.
    expect(stepGetter("ArrowUp", centeredIn(bottomRow))).toEqual({
      x: topCenterStart.left,
      y: topCenterStart.top,
    });
    expect(panelCollisionDetection(buildArgs(null))[0]?.id).toBe("top-center");
  });

  it("steps Up out of the occupied full-width bottom section instead of re-selecting it", () => {
    // A top row (left/center/right) over a full-width bottom strip, at a narrow content
    // width where the occupied bottom strip's closestCorners score beats the top-row
    // sections. The occupied droppable must be excluded from the candidates, otherwise
    // ArrowUp re-selects "bottom" and returns the item's current position — a no-op.
    const rects = new Map([
      ["top-left", rect(0, 0, 200, 560)],
      ["top-center", rect(200, 0, 600, 560)],
      ["top-right", rect(800, 0, 200, 560)],
      ["bottom", rect(0, 560, 1000, 240)],
    ]);
    // The dragged tab pill sits centered inside "bottom", where the getter leaves it
    // after stepping Down.
    const collisionRect = rect(465, 665, 70, 30);
    setKeyboardDropTarget("bottom");

    const coordinates = panelKeyboardCoordinateGetter(
      { code: "ArrowUp", preventDefault: () => {} } as unknown as KeyboardEvent,
      {
        active: "dragged",
        currentCoordinates: { x: collisionRect.left, y: collisionRect.top },
        context: {
          active: {
            id: "dragged",
            rect: { current: { initial: null, translated: collisionRect } },
            data: { current: {} },
          },
          collisionRect,
          droppableRects: rects,
          droppableContainers: {
            getEnabled: () => [...rects.keys()].map((id) => ({ id, disabled: false })),
          },
        },
      } as unknown as Parameters<KeyboardCoordinateGetter>[1],
    );

    // The item lands centered in "top-center" and the recorded keyboard target follows.
    expect(coordinates).toEqual({ x: 465, y: 265 });
    expect(panelCollisionDetection(buildArgs(null))[0]?.id).toBe("top-center");
  });
});
