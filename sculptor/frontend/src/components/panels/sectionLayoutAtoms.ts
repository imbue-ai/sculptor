import { atomWithStorage } from "jotai/utils";

import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";

// Global experimental setting: render every section's tab strip at the top or
// bottom (REQ-SET-1). Default top. Stored in localStorage so it is global and
// persistent without a backend user-config field.
export type TabStripPosition = "top" | "bottom";

export const tabStripPositionAtom = atomWithStorage<TabStripPosition>("sculptor-tab-strip-position", "top", undefined, {
  getOnInit: true,
});

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

// In-panel master-detail divider, as the detail (diff) pane's percentage of the
// panel width (REQ-DIFF-2). Global so the split carries across file panels and
// workspaces.
export const masterDetailDetailPercentAtom = atomWithDebouncedStorage<number>(
  "sculptor-master-detail-percent",
  60,
  200,
);
