# Supplemental: prototype → rewrite naming map

Companion to `../state_design.md` and `../component_hierarchy.md`. The
`scu-1474` prototype branch is the reference for *shape*,
but it uses pre-`goals.md` vocabulary ("zone", "focus", "expand") and carries
deprecated/experimental state. The rewrite renames everything to `goals.md`
vocabulary and deletes the cruft (no dead code, no stale files).

## Vocabulary

| `goals.md` term | Prototype term | Notes |
|---|---|---|
| section | zone (the 4 primary ones) | left, center, right, bottom |
| sub-section | `<zone>:split` half | primary + secondary |
| active section / active sub-section | focus / `focusedZone` | last interacted; may be a split half |
| collapsed / expanded | zone visibility | center always expanded |
| maximized | maximize (`maximizedZone`) | name kept; distinct from old "expand" |
| split | section split | axis + ratio |
| open vs. active panel | panels-in-zone vs. active-panel-per-zone | unchanged concept |

## Atoms / types renamed (retained)

| Prototype | Rewrite |
|---|---|
| `ZoneId` | `SectionId` + `SubSectionId` |
| `zoneAssignmentsAtom` | `panelPlacementAtom` (panel → sub-section) |
| `zoneOrderAtom` | `panelOrderAtom` |
| `activePanelPerZoneAtom` | `activePanelPerSubSectionAtom` |
| `zoneVisibilityAtom` | `sectionExpandedAtom` |
| `sectionSizePercentAtom` | `sectionSizesAtom` |
| `sectionSplitAtom` | `sectionSplitAtom` (kept) |
| `focusedZoneAtom` | `activeSubSectionAtom` |
| `focusZoneAtom` (pulse) | `jumpToSectionAtom` |
| `selectZoneAtom` (silent) | `setActiveSectionAtom` |
| `focusRingVisibleAtom` / `focusRingNonceAtom` | `activeSectionRingVisibleAtom` / `activeSectionRingNonceAtom` |
| `maximizedZoneAtom` | `maximizedSectionAtom` |
| `panelsInZoneAtom(z)` | `panelsInSubSectionAtom(s)` |
| `isZoneVisibleAtom(z)` | `isSectionExpandedAtom(s)` |
| `activePanelComponentInZoneAtom(z)` | `activePanelComponentInSubSectionAtom(s)` |
| `isDropTargetAtom(z)` / `ghostPanelIdAtom(z)` | same, keyed by sub-section |
| `switchActiveWorkspaceAtom` | `switchActiveWorkspaceAtom` (kept) |
| `atomWithDebouncedStorage` | folded into `LocalStorageLayoutAdapter` |
| `scopedLayoutStorageFamily` | folded into `workspaceLayoutFamily` (consolidated) |

The prototype's separate per-concern atomFamilies (`zoneAssignmentsFamily`,
`activePanelPerZoneFamily`, `zoneVisibilityFamily`, `zoneOrderFamily`,
`focusedZoneFamily`, …) collapse into **one** consolidated
`workspaceLayoutFamily(workspaceId)` per `state_design.md` → "Consolidated
snapshots". Read-side narrow slices are derived from it (see `state_atoms.md`).

## Explorer scaffold renamed

The shared file-list + diff-viewer scaffold the Files/Changes/Commits panels embed
is renamed away from the prototype's generic "master-detail" pattern name. It is
not itself a registry panel, so the `…Panel` suffix was misleading; the rewrite
calls it `ExplorerLayout`.

| Prototype | Rewrite |
|---|---|
| `MasterDetailPanel` | `ExplorerLayout` |
| `MasterDetailTreeHeader` | `ExplorerTreeHeader` |
| `masterDetailListWidthAtom` | `explorerListWidthAtom` |
| `GlobalLayoutState.masterDetailListWidthPx` | `GlobalLayoutState.explorerListWidthPx` |

## Deleted (not carried forward)

| Prototype | Reason |
|---|---|
| `expandedPanelIdAtom` | legacy docking "review/expand mode"; replaced by maximized section |
| `sectionSizesSharedAtom` | the deprecated "share sizes between workspaces" setting; sizes are always global |
| `tabStripPositionAtom` | top/bottom tab-strip experimental setting; not in `goals.md` |
| `panelEnabledAtom`, `defaultEnabled`, `isBuiltin` | backed the deprecated Panels settings page |
| `zoneSizesAtom` | leftover pixel-sizes atom from the docking layout (compact layout uses percentages) |
| `bottom-left` / `bottom-right` zones | legacy docking sub-splits; the rewrite has clean section + split-sub-section ids only |
| Zen mode, Focus mode, `/btw` atoms | deprecated features (`goals.md` → "Features to deprecate") |

See `../state_design.md` → "Removed state" for the rationale in context.
