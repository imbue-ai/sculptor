import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";

// Section sizes are SHARED (global), stored as a percentage of the screen
// (REQ-PERSIST-2). Visibility is per-workspace (handled elsewhere); only the
// sizes are global so a comfortable split carries across workspaces.
export type SectionSizeKey = "left" | "right" | "bottom";

export const DEFAULT_SECTION_PERCENT: Record<SectionSizeKey, number> = {
  left: 20,
  right: 22,
  bottom: 30,
};

export const sectionSizePercentAtom = atomWithDebouncedStorage<Partial<Record<SectionSizeKey, number>>>(
  "sculptor-section-size-percent",
  {},
  200,
);
