// Shared dnd-kit sensor wiring for the sidebar's sortable lists: the repo list
// in WorkspaceSidebar, and each repo section's flat children lane (loose rows,
// group header rows, and member rows in ONE SortableContext) in
// SidebarRepoGroup. Every list runs a PointerSensor AND a KeyboardSensor, and
// the row/header is itself the focusable drag activator, so Playwright drives
// the real sensor pipeline (focus → Space → arrows → Space) — mirroring the
// panel-tab drag architecture (PanelDndProvider).

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
 * The sidebar's drag sensors. The pointer sensor's distance constraint keeps
 * plain clicks working on the activator (navigate / toggle collapse); the
 * keyboard sensor's coordinate getter moves the dragged item one droppable
 * slot per Up/Down press.
 *
 * `onDepthKey` (the repo sections' flat lanes only): Left/Right presses don't
 * move the drag — they flip the projected depth at the ambiguous
 * tail-of-group slot (REQ-DND-6), the keyboard mirror of dragging the pointer
 * across the member indent. Read through a ref so the sensor never re-inits
 * when the handler identity changes mid-drag.
 */
export function useSidebarDndSensors(
  onDepthKey?: (intent: SectionDepthIntent) => void,
): Array<SensorDescriptor<SensorOptions>> {
  const onDepthKeyRef = useRef(onDepthKey);
  useEffect(() => {
    onDepthKeyRef.current = onDepthKey;
  });
  const coordinateGetter = useMemo<KeyboardCoordinateGetter>(
    () =>
      (event, args): ReturnType<KeyboardCoordinateGetter> => {
        if (onDepthKeyRef.current !== undefined) {
          if (event.code === "ArrowLeft") {
            onDepthKeyRef.current("outside");
            return undefined;
          }

          if (event.code === "ArrowRight") {
            onDepthKeyRef.current("inside");
            return undefined;
          }
        }
        return sortableKeyboardCoordinates(event, args);
      },
    [],
  );
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: POINTER_DRAG_ACTIVATION_DISTANCE_PX } }),
    useSensor(KeyboardSensor, { coordinateGetter }),
  );
}
