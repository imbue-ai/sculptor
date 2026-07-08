// Shared dnd-kit sensor wiring for the sidebar's sortable lists (repo groups in
// WorkspaceSidebar, and each repo section's mixed children — loose workspace rows,
// group cards, and the member rows inside them — in SidebarRepoGroup). Every list
// runs a PointerSensor AND a KeyboardSensor, and the row/header is itself the
// focusable drag activator, so Playwright drives the real sensor pipeline (focus →
// Space → arrows → Space) — mirroring the panel-tab drag architecture
// (PanelDndProvider).

import type { ClientRect, Modifier, SensorDescriptor, SensorOptions } from "@dnd-kit/core";
import { KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToParentElement, restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import type { RefObject } from "react";

import { POINTER_DRAG_ACTIVATION_DISTANCE_PX } from "~/components/sections/panelDnd.ts";

// The repo LIST is vertical, so a dragged repo group is locked to its lane: it
// slides only on the y axis and never leaves the list. This deliberately diverges
// from panel-tab drags, which must travel freely across sections. Drops still
// resolve by pointer position even when the pointer itself wanders off the rail —
// only the element's movement is constrained.
export const sidebarDndModifiers = [restrictToVerticalAxis, restrictToParentElement];

// Clamp the dragged element to `boundsRef`'s current on-screen rect (measured
// live, so mid-drag layout changes — a drop slot mounting inside a group card —
// move the boundary with the content). A repo section's drag context uses this
// instead of restrictToParentElement: a workspace row must be able to leave its
// immediate container (the loose lane or a group card's member box) to cross
// into another container, but only WITHIN its repo section — cross-repo drops
// stay structurally impossible.
function restrictToRefRect(boundsRef: RefObject<HTMLElement | null>): Modifier {
  return ({ transform, draggingNodeRect }) => {
    const bounds = boundsRef.current;
    if (draggingNodeRect === null || draggingNodeRect === undefined || bounds === null) {
      return transform;
    }
    return clampToRect(transform, draggingNodeRect, bounds.getBoundingClientRect());
  };
}

// The clamp itself (dnd-kit's restrictToBoundingRect is not exported): keep the
// dragged node's initial rect, offset by the transform, inside the bounding rect.
function clampToRect(
  transform: { x: number; y: number; scaleX: number; scaleY: number },
  rect: ClientRect,
  bounds: { top: number; left: number; width: number; height: number },
): { x: number; y: number; scaleX: number; scaleY: number } {
  const clamped = { ...transform };
  if (rect.top + transform.y <= bounds.top) {
    clamped.y = bounds.top - rect.top;
  } else if (rect.bottom + transform.y >= bounds.top + bounds.height) {
    clamped.y = bounds.top + bounds.height - rect.bottom;
  }

  if (rect.left + transform.x <= bounds.left) {
    clamped.x = bounds.left - rect.left;
  } else if (rect.right + transform.x >= bounds.left + bounds.width) {
    clamped.x = bounds.left + bounds.width - rect.right;
  }
  return clamped;
}

/** The modifiers for one repo section's children context: vertical, clamped to the section's children box. */
export function buildRepoSectionDndModifiers(boundsRef: RefObject<HTMLElement | null>): Array<Modifier> {
  return [restrictToVerticalAxis, restrictToRefRect(boundsRef)];
}

// The pointer sensor's distance constraint keeps plain clicks working on the
// activator (navigate / toggle collapse); the keyboard sensor's sortable coordinate
// getter moves the dragged item one droppable slot per arrow press — including
// slots in a different container within the same context, which is what makes
// keyboard membership moves (arrow a row into or out of a group card) work.
export function useSidebarDndSensors(): Array<SensorDescriptor<SensorOptions>> {
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: POINTER_DRAG_ACTIVATION_DISTANCE_PX } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
}

// ---- Repo-section drag classification ----
// A repo section's context mixes several kinds of sortables/droppables. Each
// registers `data` describing what it is, so drop handlers and drop-affordance
// renderers classify by this contract instead of guessing from id prefixes.

/** `containerId` of a workspace row rendered loose in the repo section's mixed lane. */
export const LOOSE_CONTAINER_ID = "loose";

export type SidebarRowDragData = {
  sidebarKind: "workspace";
  // LOOSE_CONTAINER_ID for a loose row, or the group id for a member row.
  containerId: string;
  // The source group's accent color for member rows, so cross-container drop
  // affordances outside the card can tint in the group's color.
  accentColor?: string;
};

export type SidebarGroupCardDragData = {
  sidebarKind: "workspace-group";
};

// Droppable-only zones (drop targets that are not sortable items): the dashed
// "drop to add" slot at the end of a group card's member rows, and the dashed
// "drop to remove from group" slot at the end of the repo section's children.
export type SidebarDropSlotDragData =
  | { sidebarKind: "workspace-group-drop-slot"; groupId: string }
  | { sidebarKind: "release-slot" };

export type SidebarDragData = SidebarRowDragData | SidebarGroupCardDragData | SidebarDropSlotDragData;

/** The registered drag data of the given active/over entry, if it follows the contract. */
export function getSidebarDragData(entry: { data: RefObject<unknown> } | null): SidebarDragData | undefined {
  const data = entry?.data.current;
  if (typeof data === "object" && data !== null && "sidebarKind" in data) {
    return data as SidebarDragData;
  }
  return undefined;
}

// The drop-slot droppables' ids live outside the mixed lane's key space (they
// are zones, not children); classification still goes through the data above.

/** The id of a group card's "drop to add" slot droppable. */
export const workspaceGroupDropSlotId = (groupId: string): string => `workspace-group-drop-slot:${groupId}`;

/** The id of a repo section's "drop to remove from group" slot droppable. */
export const REPO_SECTION_RELEASE_SLOT_ID = "repo-section-release-slot";
