// Shared dnd-kit sensor wiring for the sidebar's two sortable lists (repo groups in
// WorkspaceSidebar, workspace rows in each SidebarRepoGroup). Both lists run a
// PointerSensor AND a KeyboardSensor, and the row/header is itself the focusable
// drag activator, so Playwright drives the real sensor pipeline (focus → Space →
// arrows → Space) — mirroring the panel-tab drag architecture (PanelDndProvider).

import type { SensorDescriptor, SensorOptions } from "@dnd-kit/core";
import { KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToParentElement, restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

import { POINTER_DRAG_ACTIVATION_DISTANCE_PX } from "~/components/sections/panelDnd.ts";

// Both sidebar lists are vertical, so the floating copy is locked to its lane: it
// slides only on the y axis and never leaves the dragged element's container (a
// row stays inside its repo group, a group inside the repo list). This deliberately
// diverges from panel-tab drags, whose overlay must travel freely across sections.
// Drops still resolve by pointer position even when the pointer itself wanders off
// the rail — only the copy is constrained.
export const sidebarDndModifiers = [restrictToVerticalAxis, restrictToParentElement];

// The pointer sensor's distance constraint keeps plain clicks working on the
// activator (navigate / toggle collapse); the keyboard sensor's sortable coordinate
// getter moves the dragged item one slot per arrow press.
export function useSidebarDndSensors(): Array<SensorDescriptor<SensorOptions>> {
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: POINTER_DRAG_ACTIVATION_DISTANCE_PX } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
}
