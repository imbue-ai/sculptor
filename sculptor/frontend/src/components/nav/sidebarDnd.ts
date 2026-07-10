// Shared dnd-kit sensor wiring for the sidebar's two sortable lists (repo groups in
// WorkspaceSidebar, workspace rows in each SidebarRepoGroup). Both lists run a
// PointerSensor AND a KeyboardSensor, and the row/header is itself the focusable
// drag activator, so Playwright drives the real sensor pipeline (focus → Space →
// arrows → Space) — mirroring the panel-tab drag architecture (PanelDndProvider).

import type { ClientRect, CollisionDetection, SensorDescriptor, SensorOptions } from "@dnd-kit/core";
import { closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToParentElement, restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

import { POINTER_DRAG_ACTIVATION_DISTANCE_PX } from "~/components/sections/panelDnd.ts";

// Both sidebar lists are vertical, so the dragged element is locked to its lane: it
// slides only on the y axis and never leaves its container (a row stays inside its
// group's rows box, a group inside the repo list).
export const sidebarDndModifiers = [restrictToVerticalAxis, restrictToParentElement];

// The fraction of `target`'s OWN area that the dragged rect currently covers. dnd-kit's
// built-in rectIntersection normalises the overlap by the UNION area, so a tall item's own
// slot — which has by far the largest union — always wins and the item can never be dragged
// onto a short neighbour. Normalising by the TARGET's area instead lets a small nudge flip a
// large item onto a small one: a short neighbour is fully covered after roughly one of its
// own rows, while the dragged item's own (equally tall) slot only stays ahead until it has
// been mostly vacated. For equal-height rows the crossover is half a row — the same feel as
// closestCenter.
function coveredFractionOfTarget(dragged: ClientRect, target: ClientRect): number {
  const overlapWidth =
    Math.min(dragged.left + dragged.width, target.left + target.width) - Math.max(dragged.left, target.left);
  const overlapHeight =
    Math.min(dragged.top + dragged.height, target.top + target.height) - Math.max(dragged.top, target.top);
  if (overlapWidth <= 0 || overlapHeight <= 0) {
    return 0;
  }
  const targetArea = target.width * target.height;
  return targetArea > 0 ? (overlapWidth * overlapHeight) / targetArea : 0;
}

// Resolve the drop target from the dragged element's RECTANGLE, scoring each item by the
// fraction of its own area the dragged rect covers (see coveredFractionOfTarget). This
// reorders a tall expanded group after a small drag toward a neighbour, while leaving
// equal-height rows behaving like closestCenter.
//
// It keys off the modifier-clamped collisionRect — restrictToParentElement holds the dragged
// element inside the list, so its rect always overlaps some item — rather than the raw
// pointer. A drag past the container edge therefore stays pinned to the extreme item instead
// of dropping `over`: a null `over` zeroes dnd-kit's active-item transform (it only offsets
// the dragged item while overIndex is a valid index) and snaps the item back to its origin.
// closestCenter — which never returns an empty result — is the final safety net.
//
// Keyboard drags have no pointer: the sortable keyboard getter steps the dragged rect onto
// the target slot, so closestCenter resolves it exactly.
export const sidebarCollisionDetection: CollisionDetection = (args) => {
  if (args.pointerCoordinates === null) {
    return closestCenter(args);
  }
  const { collisionRect, droppableRects, droppableContainers } = args;
  const collisions: ReturnType<CollisionDetection> = [];
  for (const droppableContainer of droppableContainers) {
    const rect = droppableRects.get(droppableContainer.id);
    if (rect === undefined) {
      continue;
    }
    const value = coveredFractionOfTarget(collisionRect, rect);
    if (value > 0) {
      collisions.push({ id: droppableContainer.id, data: { droppableContainer, value } });
    }
  }

  if (collisions.length > 0) {
    return collisions.sort((first, second) => (second.data?.value ?? 0) - (first.data?.value ?? 0));
  }
  return closestCenter(args);
};

// The pointer sensor's distance constraint keeps plain clicks working on the
// activator (navigate / toggle collapse); the keyboard sensor's sortable coordinate
// getter moves the dragged item one slot per arrow press.
export function useSidebarDndSensors(): Array<SensorDescriptor<SensorOptions>> {
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: POINTER_DRAG_ACTIVATION_DISTANCE_PX } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
}
