// Shared dnd-kit wiring for the sidebar's two sortable lists (repo groups in
// WorkspaceSidebar, workspace rows in each SidebarRepoGroup). Both lists run a
// PointerSensor AND a KeyboardSensor, and the row/header is itself the focusable
// drag activator, so Playwright drives the real sensor pipeline (focus → Space →
// arrows → Space) — mirroring the panel-tab drag architecture (PanelDndProvider).

import type { SensorDescriptor, SensorOptions } from "@dnd-kit/core";
import { KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToParentElement, restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

// Both sidebar lists are vertical: keep drags on the y axis and inside the list, so
// a wild pointer can't carry a row visually out of the rail.
export const sidebarDndModifiers = [restrictToVerticalAxis, restrictToParentElement];

// The pointer sensor's distance constraint keeps plain clicks working on the
// activator (navigate / toggle collapse); the keyboard sensor's sortable coordinate
// getter moves the dragged item one slot per arrow press.
export function useSidebarDndSensors(): Array<SensorDescriptor<SensorOptions>> {
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
}
