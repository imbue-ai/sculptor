import type { Atom } from "jotai";
import { atom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";
import { LAYOUT_SCOPE_GLOBAL, layoutScopeAtom, scopedLayoutStorageFamily } from "~/components/panels/atoms.ts";
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

// Section sizes are SHARED (global) by default, stored as a percentage of the
// screen (REQ-PERSIST-2). Visibility is per-workspace (handled elsewhere); only
// the sizes are global so a comfortable split carries across workspaces. When
// `sectionSizesSharedAtom` is off, sizes resolve per-workspace instead.
export type SectionSizeKey = "left" | "right" | "bottom";

export const DEFAULT_SECTION_PERCENT: Record<SectionSizeKey, number> = {
  left: 20,
  right: 22,
  bottom: 30,
};

const sectionSizePercentFamily = scopedLayoutStorageFamily<Partial<Record<SectionSizeKey, number>>>(
  "sculptor-section-size-percent",
  {},
);

const sectionSizeScopeAtom = atom<string>((get) =>
  get(sectionSizesSharedAtom) ? LAYOUT_SCOPE_GLOBAL : get(layoutScopeAtom),
);

export const sectionSizePercentAtom = atom(
  (get) => get(sectionSizePercentFamily(get(sectionSizeScopeAtom))),
  (
    get,
    set,
    update:
      | Partial<Record<SectionSizeKey, number>>
      | ((prev: Partial<Record<SectionSizeKey, number>>) => Partial<Record<SectionSizeKey, number>>),
  ) => set(sectionSizePercentFamily(get(sectionSizeScopeAtom)), update),
);

// In-panel master-detail layout (REQ-DIFF-2). The file tree (master/list) keeps a
// FIXED pixel width while the viewer (detail) flexes to absorb panel resizes; the
// user can still drag the divider to change the tree width. The width is keyed by
// panel SCOPE ("files" / "changes" / "commits"), not the workspace — so a
// comfortable width carries across workspaces, while each of the three panels
// keeps its own value (independent of the others).
export const MASTER_DETAIL_MIN_LIST_PX = 200;
export const MASTER_DETAIL_DEFAULT_LIST_PX = 240;

export const masterDetailListWidthAtomFamily = atomFamily((scope: string) =>
  atomWithDebouncedStorage<number>(`sculptor-master-detail-list-px-${scope}`, MASTER_DETAIL_DEFAULT_LIST_PX, 200),
);

// Whether the tree pane is collapsed so the viewer fills the panel. Per panel,
// persisted; toggled from the tree header (hide) and the diff header (show).
export const masterDetailTreeHiddenAtomFamily = atomFamily((stateKey: string) =>
  atomWithStorage<boolean>(`sculptor-master-detail-tree-hidden-${stateKey}`, false),
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
// split; absence means it is whole. Per-workspace (layout-scoped) and persisted,
// like the rest of the panel layout.
const sectionSplitFamily = scopedLayoutStorageFamily<Partial<Record<ZoneId, SectionSplit>>>(
  "sculptor-section-split",
  {},
);

export const sectionSplitAtom = atom(
  (get) => get(sectionSplitFamily(get(layoutScopeAtom))),
  (
    get,
    set,
    update:
      | Partial<Record<ZoneId, SectionSplit>>
      | ((prev: Partial<Record<ZoneId, SectionSplit>>) => Partial<Record<ZoneId, SectionSplit>>),
  ) => set(sectionSplitFamily(get(layoutScopeAtom)), update),
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
