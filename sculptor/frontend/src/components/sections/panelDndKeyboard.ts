// Keyboard drag support for the panel drag-and-drop DndContext: a directional
// coordinate getter plus a matching collision detection.
//
// dnd-kit's default keyboard getter nudges the dragged item a fixed ~25px per arrow,
// so crossing sections would take many presses — impractical to drive and to test.
// This getter jumps the dragged item to the NEAREST droppable in the pressed
// direction, so one ArrowRight/Left/Up/Down moves the panel to the adjacent section,
// making the keyboard pipeline (focus handle → Space → one arrow per section → Space)
// the reliable, Playwright-drivable drag path (harness_migration.md §3b).
//
// Geometry alone can't resolve `over` reliably for keyboard drags: the thin
// full-height collapsed-section rails abut other droppables, and dnd-kit's keyboard
// scroll-clamping can leave the dragged item short of its target — so closestCenter/
// closestCorners pick the wrong section. Instead the getter records the section it
// stepped to, and the collision detection returns exactly that during a keyboard drag
// (identified by the absence of pointer coordinates); pointer drags fall back to
// closestCenter. The recorded target is reset at the start of every drag so it never
// leaks across drags or into a pointer drag.

import type { CollisionDetection, DroppableContainer, KeyboardCoordinateGetter, UniqueIdentifier } from "@dnd-kit/core";
import { closestCenter, closestCorners, getFirstCollision, KeyboardCode } from "@dnd-kit/core";

const DIRECTIONAL_CODES: ReadonlyArray<string> = [
  KeyboardCode.Down,
  KeyboardCode.Right,
  KeyboardCode.Up,
  KeyboardCode.Left,
];

// The droppable the keyboard getter last stepped to, shared with the collision
// detection below. Only one drag runs at a time; seeded to the source section on drag
// start (so the initial `over` is the source) and cleared on drag end.
let keyboardDropTargetId: UniqueIdentifier | null = null;

export function setKeyboardDropTarget(id: UniqueIdentifier | null): void {
  keyboardDropTargetId = id;
}

export function resetKeyboardDropTarget(): void {
  keyboardDropTargetId = null;
}

export const panelKeyboardCoordinateGetter: KeyboardCoordinateGetter = (
  event,
  { context: { active, droppableRects, droppableContainers, collisionRect } },
) => {
  if (!DIRECTIONAL_CODES.includes(event.code)) {
    return undefined;
  }
  event.preventDefault();
  if (active === null || collisionRect === null) {
    return undefined;
  }

  // Keep only the droppables strictly in the pressed direction from the dragged item.
  const candidates: Array<DroppableContainer> = [];
  for (const container of droppableContainers.getEnabled()) {
    if (container === undefined || container.disabled) {
      continue;
    }
    const rect = droppableRects.get(container.id);
    if (rect === undefined) {
      continue;
    }

    switch (event.code) {
      case KeyboardCode.Down:
        if (collisionRect.top < rect.top) {
          candidates.push(container);
        }
        break;
      case KeyboardCode.Up:
        if (collisionRect.top > rect.top) {
          candidates.push(container);
        }
        break;
      case KeyboardCode.Left:
        if (collisionRect.left >= rect.left + rect.width) {
          candidates.push(container);
        }
        break;
      case KeyboardCode.Right:
        if (collisionRect.left + collisionRect.width <= rect.left) {
          candidates.push(container);
        }
        break;
      default:
        break;
    }
  }

  const collisions = closestCorners({
    active,
    collisionRect,
    droppableRects,
    droppableContainers: candidates,
    pointerCoordinates: null,
  });
  const closestId = getFirstCollision(collisions, "id");
  if (closestId === null) {
    return undefined;
  }
  const targetRect = droppableRects.get(closestId);
  if (targetRect === undefined) {
    return undefined;
  }
  // Record the stepped-to section for the collision detection, and move the dragged
  // item onto the target so dnd-kit fires drag-move (which recomputes `over`).
  keyboardDropTargetId = closestId;
  return {
    x: targetRect.left + targetRect.width / 2 - collisionRect.width / 2,
    y: targetRect.top + targetRect.height / 2 - collisionRect.height / 2,
  };
};

// During a keyboard drag (no pointer coordinates), resolve `over` to the section the
// getter stepped to — bypassing geometry that thin rails and scroll-clamping would
// otherwise get wrong. Before the first arrow (target unset) and for pointer drags,
// fall back to closestCenter.
export const panelCollisionDetection: CollisionDetection = (args) => {
  if (args.pointerCoordinates === null && keyboardDropTargetId !== null) {
    return [{ id: keyboardDropTargetId }];
  }
  return closestCenter(args);
};
