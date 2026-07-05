// Sidebar width/collapsed are global chrome: writable slices of the consolidated
// globalLayoutAtom so the sidebar reads/writes one global snapshot (persisted,
// shared across workspaces).

import type { WritableAtom } from "jotai";
import { atom } from "jotai";

import { globalLayoutAtom } from "~/components/sections/sectionAtoms.ts";

export const sidebarWidthAtom: WritableAtom<number, [number], void> = atom(
  (get) => get(globalLayoutAtom).sidebarWidthPx,
  (_get, set, width: number) => set(globalLayoutAtom, (prev) => ({ ...prev, sidebarWidthPx: width })),
);

export const sidebarCollapsedAtom: WritableAtom<boolean, [boolean], void> = atom(
  (get) => get(globalLayoutAtom).sidebarCollapsed,
  (_get, set, collapsed: boolean) => set(globalLayoutAtom, (prev) => ({ ...prev, sidebarCollapsed: collapsed })),
);
