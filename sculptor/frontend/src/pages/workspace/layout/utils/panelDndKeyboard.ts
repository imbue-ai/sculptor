// Keyboard drag support for the panel drag-and-drop DndContext: a directional
// coordinate getter plus a matching collision detection.
//
// dnd-kit's default keyboard getter nudges the dragged item a fixed ~25px per arrow,
// so crossing sections would take many presses — impractical to drive and to test.
// This getter jumps the dragged item to the NEAREST droppable in the pressed
// direction, so one ArrowRight/Left/Up/Down moves the panel to the adjacent section,
// making the keyboard pipeline (focus handle → Space → one arrow per section → Space)
// the reliable, Playwright-drivable drag path.
//
// Geometry alone can't resolve `over` reliably for keyboard drags: the thin
// full-height collapsed-section rails abut other droppables, and dnd-kit's keyboard
// scroll-clamping can leave the dragged item short of its target — so closestCenter/
// closestCorners pick the wrong section. Instead the getter records the section it
// stepped to, and the collision detection returns exactly that during a keyboard drag
// (identified by the absence of pointer coordinates); pointer drags resolve via
// pointerWithin, falling back to rectIntersection. The recorded target is reset at the
// start of every drag so it never leaks across drags or into a pointer drag.

import type { CollisionDetection, DroppableContainer, KeyboardCoordinateGetter, UniqueIdentifier } from "@dnd-kit/core";
import { closestCorners, getFirstCollision, KeyboardCode, pointerWithin, rectIntersection } from "@dnd-kit/core";

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

export const setKeyboardDropTarget = (id: UniqueIdentifier | null): void => {
  keyboardDropTargetId = id;
};

export const resetKeyboardDropTarget = (): void => {
  keyboardDropTargetId = null;
};

// The pointer's live viewport position during a pointer drag, captured from the
// collision detection below (dnd-kit passes it the raw activation-plus-translate
// coordinates, which stay in viewport space even as scrollable ancestors scroll).
// The provider reads this to compute the insertion slot: activatorEvent.clientX plus
// event.delta.x drifts by the accumulated scroll once the overflowing tab strip
// auto-scrolls mid-drag, because event.delta folds in that scroll adjustment. Null
// during keyboard drags (no pointer) and between drags.
type PointerPosition = { x: number; y: number };
let dragPointerCoordinates: PointerPosition | null = null;

export const getDragPointerCoordinates = (): PointerPosition | null => {
  return dragPointerCoordinates;
};

export const resetDragPointerCoordinates = (): void => {
  dragPointerCoordinates = null;
};

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

    // Never step back into the droppable the drag currently occupies. The dragged item
    // sits centered inside it, so the Up/Down filters (which compare tops only) would
    // re-admit it, and closestCorners can then prefer it over the real neighbor — e.g.
    // a full-width bottom strip beats the top-row sections at narrow content widths —
    // turning the arrow press into a silent no-op. The drag-start seed makes this also
    // exclude the source section on the first press.
    if (container.id === keyboardDropTargetId) {
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
// otherwise get wrong.
//
// For pointer drags, resolve to the droppable the pointer is actually over
// (pointerWithin) rather than the one whose center is nearest (closestCenter).
// closestCenter let a tall section's center "win" well beyond its own bounds — so its
// drop zone bled into a neighbor (you had to drag deep into the target before it
// registered), thin collapsed rails lost to their fat neighbors, and reordering a tab
// in a tall section could resolve to a different section. Fall back to rectIntersection
// when the pointer sits in a gap between droppables so the drag still finds a target.
export const panelCollisionDetection: CollisionDetection = (args) => {
  // dnd-kit recomputes collisions in the same cycle it fires drag-move/over, so
  // stashing the pointer here keeps it in lockstep with the resolved `over`.
  dragPointerCoordinates = args.pointerCoordinates;
  if (args.pointerCoordinates === null && keyboardDropTargetId !== null) {
    return [{ id: keyboardDropTargetId }];
  }
  const pointerCollisions = pointerWithin(args);
  if (pointerCollisions.length > 0) {
    return pointerCollisions;
  }
  return rectIntersection(args);
};
