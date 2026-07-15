// Shared dnd-kit sensor wiring for the sidebar's drag surfaces: the repo list
// in WorkspaceSidebar (a plain sortable list), and each repo section's flat
// children lane (loose rows, group header rows, and member rows as draggable
// siblings) in SidebarRepoGroup. Every surface runs a PointerSensor AND a
// KeyboardSensor, and the row/header is itself the focusable drag activator,
// so Playwright drives the real sensor pipeline (focus → Space → arrows →
// Space) — mirroring the panel-tab drag architecture (PanelDndProvider).

import type {
  ClientRect,
  CollisionDetection,
  KeyboardCoordinateGetter,
  SensorDescriptor,
  SensorOptions,
} from "@dnd-kit/core";
import { closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToParentElement, restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { useEffect, useMemo, useRef } from "react";

import { POINTER_DRAG_ACTIVATION_DISTANCE_PX } from "~/components/sections/panelDnd.ts";

import type { SectionDepthIntent } from "./sidebarDropProjection.ts";

// The repo LIST is vertical, so a dragged repo group is locked to its lane: it
// slides only on the y axis and never leaves the list. Repo sections are big
// container lanes, not cards — the free-floating overlay treatment belongs to
// the rows INSIDE a section, whose drags carry no modifiers at all.
export const sidebarDndModifiers = [restrictToVerticalAxis, restrictToParentElement];

/**
 * A repo section's keyboard-drag handlers. Arrow presses never touch dnd-kit's
 * droppable/collision machinery — the section lane registers no droppables, so
 * there is nothing to collide with; both handlers resolve against the lane's
 * projection engine instead, the same authority the pointer path uses.
 */
export type SectionKeyboardHandlers = {
  /**
   * Left/Right: flip the projected depth at the ambiguous tail-of-group slot
   * (REQ-DND-6) — the keyboard mirror of dragging the pointer across the
   * member indent. The press moves nothing.
   */
  onDepthKey: (intent: SectionDepthIntent) => void;
  /**
   * Up/Down: step the drag one lane entry through the projection engine,
   * returning the target slot's viewport y so the DragOverlay rides to it
   * (undefined = the lane's end, a no-op press).
   */
  onStepKey: (direction: "up" | "down") => number | undefined;
};

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

// Resolve the repo list's drop target from the dragged element's RECTANGLE, scoring each
// item by the fraction of its own area the dragged rect covers (see
// coveredFractionOfTarget). This reorders a tall expanded repo group after a small drag
// toward a neighbour, while leaving equal-height items behaving like closestCenter. The
// repo sections' inner lanes never touch this: they register no droppables and resolve
// drops through their own projection engine.
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

/**
 * The sidebar's drag sensors. The pointer sensor's distance constraint keeps
 * plain clicks working on the activator (navigate / toggle collapse); the
 * keyboard sensor's coordinate getter maps arrow presses to movement.
 *
 * With `handlers` (the repo sections' flat lanes only), every arrow press is
 * resolved by the section's projection engine — see SectionKeyboardHandlers.
 * Without them (the repo list), Up/Down falls back to dnd-kit's sortable
 * stepping over the list's droppables. Handlers are read through a ref so the
 * sensor never re-inits when their identities change mid-drag.
 */
export function useSidebarDndSensors(handlers?: SectionKeyboardHandlers): Array<SensorDescriptor<SensorOptions>> {
  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  });
  const coordinateGetter = useMemo<KeyboardCoordinateGetter>(
    () =>
      (event, args): ReturnType<KeyboardCoordinateGetter> => {
        const current = handlersRef.current;
        if (current === undefined) {
          return sortableKeyboardCoordinates(event, args);
        }

        if (event.code === "ArrowLeft") {
          current.onDepthKey("outside");
          return undefined;
        }

        if (event.code === "ArrowRight") {
          current.onDepthKey("inside");
          return undefined;
        }

        if (event.code === "ArrowUp" || event.code === "ArrowDown") {
          const y = current.onStepKey(event.code === "ArrowDown" ? "down" : "up");
          // The x never matters (the overlay is axis-locked), so the pointer's
          // last x rides along unchanged.
          return y === undefined ? undefined : { x: args.currentCoordinates.x, y };
        }
        return undefined;
      },
    [],
  );
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: POINTER_DRAG_ACTIVATION_DISTANCE_PX } }),
    useSensor(KeyboardSensor, { coordinateGetter }),
  );
}
