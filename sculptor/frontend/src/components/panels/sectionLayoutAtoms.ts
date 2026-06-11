import type { Atom } from "jotai";
import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";
import type { ZoneId } from "~/components/panels/types.ts";
import { toPrimaryZone, ZONE_IDS } from "~/components/panels/types.ts";

// Global experimental setting: render every section's tab strip at the top or
// bottom (REQ-SET-1). Default top. Stored in localStorage so it is global and
// persistent without a backend user-config field.
export type TabStripPosition = "top" | "bottom";

export const tabStripPositionAtom = atomWithStorage<TabStripPosition>("sculptor-tab-strip-position", "top", undefined, {
  getOnInit: true,
});

// Experimental: whether panel SECTION SIZES are shared across workspaces
// (global, the default) or unique per workspace. The rest of the panel layout
// (positions, visibility, split state) is always per-workspace; only sizes are
// toggleable so a comfortable split can optionally carry across workspaces.
// When false, `sectionSizePercentAtom` is snapshotted/restored per workspace by
// usePerWorkspacePanelLayout; when true it stays in its global storage key.
export const sectionSizesSharedAtom = atomWithStorage<boolean>("sculptor-section-sizes-shared", true, undefined, {
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

// ── Section splitting ────────────────────────────────────────────────
// A section can be split once into two stacked or side-by-side sub-sections.
// "horizontal" = a horizontal divider → sub-sections stacked TOP/BOTTOM;
// "vertical"   = a vertical divider   → sub-sections SIDE-BY-SIDE.
export type SplitAxis = "horizontal" | "vertical";

// One section's split state. `ratio` is the PRIMARY (first) sub-section's
// fraction of the section along the split axis (0..1); the split sub-section
// fills the rest.
export type SectionSplit = {
  axis: SplitAxis;
  ratio: number;
};

export const DEFAULT_SPLIT_RATIO = 0.5;

// Split state keyed by the PRIMARY section zone. An entry means that section is
// split; absence means it is whole. Global (shared across workspaces) and
// persisted, like the section sizes above.
export const sectionSplitAtom = atomWithDebouncedStorage<Partial<Record<ZoneId, SectionSplit>>>(
  "sculptor-section-split",
  {},
  200,
);

// ── Per-zone split slices ────────────────────────────────────────────
// Narrow reads over `sectionSplitAtom` so a split ratio changing in one
// section (every pointer move during a split resize) doesn't re-render
// components that only care about another zone. Entries in the record are
// replaced wholesale on update, so plain Object.is dedupes unaffected zones.

const sectionSplitForZoneAtomMap = new Map<ZoneId, Atom<SectionSplit | undefined>>(
  ZONE_IDS.map((zoneId) => [zoneId, atom<SectionSplit | undefined>((get) => get(sectionSplitAtom)[zoneId])]),
);

export const sectionSplitForZoneAtom = (primaryZone: ZoneId): Atom<SectionSplit | undefined> => {
  return sectionSplitForZoneAtomMap.get(primaryZone)!;
};

// Whether a zone is one half of a split section (its primary zone has split
// state). True for both the primary half and the ":split" half.
const isSplitHalfAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<boolean>((get) => get(sectionSplitAtom)[toPrimaryZone(zoneId)] !== undefined),
  ]),
);

export const isSplitHalfAtom = (zoneId: ZoneId): Atom<boolean> => {
  return isSplitHalfAtomMap.get(zoneId)!;
};
