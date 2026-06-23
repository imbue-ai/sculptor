# Task 2.4: SplittableSection / PanelSection / SectionHeader / SectionBody + memo boundaries

## Goal

Build the uniform section subtree — `SplittableSection`, `PanelSection`,
`SectionHeader`, `SectionBody` — with the **memoization boundaries** from
`component_hierarchy.md` enforced. This is the heart of the new shell: one uniform
component for left/center/right/bottom and for split halves.

## Stories addressed

SEC-09 (section header = panel tabs + add + maximize), and the structural
foundation for SEC-19 (empty state), PANEL-07 (tabs/close), and the non-functional
SWITCH-02/SWITCH-05 (each panel mounts at most once per switch; memoized re-renders).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**The uniform-section principle** (`component_hierarchy.md` → "Principles" +
"Section subtree"): left/center/right/bottom and any split half are the **same**
component. There is no special-cased chat or terminal area — chat and terminal are
panels. A panel's content component takes data from data atoms and identity from the
registry; it **never reads section/split/size layout state** (this is the rule that
later lets a mobile shell reuse content — keep it even though mobile is out of
scope).

**The subtree** (`component_hierarchy.md` → "Section subtree";
`supplemental/component_tree.md` → "Tree with subscriptions"):
- `SplittableSection(section)` `[memo]` — subscribes to `sectionSplitForSectionAtom(section)`.
  Unsplit → one `PanelSection`; split → primary `PanelSection` + `ResizeHandle` +
  secondary `PanelSection`. Self-heals when the secondary loses its last panel
  (data side handled by Task 1.4's `closePanelAtom`; this component just reflects).
- `PanelSection(subSection)` `[memo]` — subscribes to narrow per-sub-section flags:
  `isDropTargetAtom(ss)`, `isActiveSubSectionAtom(ss)`, `isRingVisibleAtom(ss)`, and
  `maximizedSectionAtom === section`. Renders `SectionHeader` + `SectionBody`.
- `SectionHeader(subSection)` `[memo]` — subscribes to `displayedPanelIdsAtom(ss)`
  (shallow-equal-deduped), `activePanelIdInSubSectionAtom(ss)`, `ghostPanelIdAtom(ss)`.
  Renders panel tabs (active highlighted, close button, rename for multi-instance),
  the add-panel `+` (opens `AddPanelDropdown` — Task 3.5), and the maximize toggle.
- `SectionBody(subSection)` `[memo]` — subscribes to
  `activePanelComponentInSubSectionAtom(ss)` (Task 1.6 — identity cached per panel
  id). Renders the resolved active panel component, or `EmptySectionState(ss)` when
  there are no open panels.

**What to copy** (`design_extraction.md` → "Sections, tabs, splits, empty state…"):
`components/panels/PanelSection.tsx` + `.module.scss` (incl. the active-section ring
CSS `.focused`/`.ringVisible::after`), `components/panels/SectionTabBar.tsx` →
`SectionHeader.tsx` (34px header, pill tabs active = `--gray-4`, always-visible
close, drag drop-edge box-shadows; tab pill styles from
`components/tabs/SortableTab.module.scss`), `components/panels/SplittableSection.tsx`
+ `.module.scss` (stacked/side-by-side, ratio flex-basis, 15–85% clamp). Copy the
**ring CSS** but rebuild the timing in Task 4.4.

This task depends on **Task 1.3/1.5/1.6** (all the slice atoms incl.
`activePanelComponentInSubSectionAtom`), **Task 2.1** (tokens), **Task 2.3**
(`SectionGrid` renders `SplittableSection`; `ResizeHandle` reused for the split
divider). `EmptySectionState` here is a **shell** (centered add button); its full
≤5 quick-actions are Task 3.5. `AddPanelDropdown` is Task 3.5 (here the `+` opens a
placeholder that Task 3.5 fills). Drag wiring is Task 4.1 (here register the
droppable/draggable seams but the provider is a stub until 4.1).

## Files to modify/create

- `sculptor/frontend/src/components/sections/SplittableSection.tsx` + `.module.scss`
  — new.
- `sculptor/frontend/src/components/sections/PanelSection.tsx` + `.module.scss` —
  new.
- `sculptor/frontend/src/components/sections/SectionHeader.tsx` + `.module.scss` —
  new (from `SectionTabBar`).
- `sculptor/frontend/src/components/sections/SectionBody.tsx` — new.
- `sculptor/frontend/src/components/sections/EmptySectionState.tsx` + `.module.scss`
  — new shell (from `EmptyPanelLauncher`; quick actions in Task 3.5).
- `sculptor/sculptor/constants.py` — add `SECTION_HEADER`, `PANEL_TAB`,
  `PANEL_TAB_CLOSE`, `SECTION_ADD_PANEL_BUTTON`, `SECTION_MAXIMIZE_BUTTON`,
  `SECTION_ACTIVE_RING`, `SECTION_EMPTY_STATE`, `SECTION_SPLIT_SUBSECTION` (then
  `just generate-api`).

## Implementation details

1. Implement each component as a `memo` with the **exact** narrow subscriptions in
   `supplemental/component_tree.md` → "Tree with subscriptions". Pass primitive
   props down (`section`, `subSection`) so memo holds.
2. `SplittableSection`: render one `PanelSection(primaryOf(section))` when unsplit;
   when split, primary `PanelSection` + `ResizeHandle` (split axis, writing
   `setSplitRatioAtom`, Task 1.4) + secondary `PanelSection(toSecondary(section))`.
   Use the split axis to choose stacked vs side-by-side and flex-basis from the
   ratio (15–85% clamp).
3. `PanelSection`: render `SectionHeader` + `SectionBody`; apply the active-section
   **ring** CSS when `isRingVisibleAtom(ss)`; apply maximized styling hook when this
   section is maximized (full impl Task 4.3). Register its body as a drop target
   keyed by `ss` (seam for Task 4.1).
4. `SectionHeader`: render a tab per displayed panel id (active highlighted; close
   button; rename affordance only for multi-instance — agent/terminal, via the
   registry `kind`); the `+` button (opens `AddPanelDropdown`, Task 3.5); the
   maximize toggle (writes `maximizedSectionAtom`, Task 1.5). Tab list is the
   shallow-equal-deduped `displayedPanelIdsAtom(ss)` slice; tab drag uses the
   per-section ghost slice.
5. `SectionBody`: render `<ActivePanelComponent />` from
   `activePanelComponentInSubSectionAtom(ss)` (stable identity per panel id →
   **no remount** on registry rebuild or switch — this is the SWITCH-02 boundary),
   or `EmptySectionState(ss)` when there are no open panels.
6. **data-testid keyspace:** suffix the `SubSectionId` at the `data-testid` level
   (e.g. `${SECTION_HEADER}-left:secondary`) rather than minting `*_SECONDARY` enum
   members (`harness_migration.md` §2; `sections_panel_layout.md` §5). Add the
   `ElementIDs` listed above and run `just generate-api`.

## Testing suggestions

- The render-count guarantees (SWITCH-02/05) are verified by the
  `measure-react-renders` skill in Task 9.1 (resize/drag/switch scenarios). Build the
  memo boundaries correctly now so those pass later.
- SEC-09 (header shows tabs + add + maximize) is asserted in Task 4.6
  (`test_section_default_layout.py` / `test_section_active_and_maximize.py`); a smoke
  check (center header renders with add + maximize) lands in Task 2.7.

## Gotchas

- **The memo boundaries are a hard requirement, not an optimization**
  (`goals.md` → "Minimize re-renders"). Each component must subscribe to *only* its
  narrow slice; do not read the whole layout snapshot in `PanelSection`/`SectionBody`.
- `SectionBody` must subscribe to the **resolved component** (identity-cached), not
  the panel id + a lookup in render — otherwise a registry rebuild remounts content.
- Content components must **not** read layout state — keep them behind the registry
  component boundary.
- Copy the ring CSS but do **not** copy the prototype's brittle ring timing (Task
  4.4 rebuilds it).
- `IconButton`s in a `Flex` need `gap="2"`.

## Verification checklist

- [ ] `SplittableSection`/`PanelSection`/`SectionHeader`/`SectionBody` exist, each a
  `memo` subscribing only to its narrow slice per `component_tree.md`.
- [ ] `SectionBody` renders the identity-cached active panel component (no remount on
  rebuild) or the empty-state shell.
- [ ] `SectionHeader` renders tabs (active/close/rename-for-multi-instance), `+`, and
  maximize.
- [ ] Split renders primary + handle + secondary with ratio flex-basis + clamp.
- [ ] data-testids suffix the sub-section id; `ElementIDs` added + `just generate-api`.
- [ ] `just check` passes.
