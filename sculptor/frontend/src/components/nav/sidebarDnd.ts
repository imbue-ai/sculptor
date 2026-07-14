// Shared dnd-kit sensor wiring for the sidebar's drag surfaces: the repo list
// in WorkspaceSidebar (a plain sortable list), and each repo section's flat
// children lane (loose rows, group header rows, and member rows as draggable
// siblings) in SidebarRepoGroup. Every surface runs a PointerSensor AND a
// KeyboardSensor, and the row/header is itself the focusable drag activator,
// so Playwright drives the real sensor pipeline (focus → Space → arrows →
// Space) — mirroring the panel-tab drag architecture (PanelDndProvider).

import type { KeyboardCoordinateGetter, SensorDescriptor, SensorOptions } from "@dnd-kit/core";
import { KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
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
