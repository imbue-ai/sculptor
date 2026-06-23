# Task 4.6: Section/split/empty-state POMs + section/split/DnD CREATE tests

## Goal

Build the section-interaction POMs (`section_split.py`, `panel_empty_state.py`, and
the section helpers) and the net-new section/split/panel-DnD e2e tests that prove the
Phase-4 interactions. This is mostly **net-new** coverage (the old zone/docking tests
are deleted, not migrated).

## Stories addressed

SEC-01..04 (default layout), SEC-05..08/20 (collapse/expand + center + panel cycle),
SEC-09..16/21 (active/ring/cycle/maximize/SPLIT-06), SEC-17/22 (resize + clamps),
SEC-19 (empty state), SPLIT-01..06 (splits), PANEL-08..10/16 (drag-and-drop),
PANEL-07/11/14 (rename/close/context — co-owned with Task 3.7).

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`. Run
via **`/run-integration-test`**; write via **`/write-integration-test`**;
`just generate-api` after `ElementIDs` changes.

**Net-new area** (`sections_panel_layout.md` §1): no section/split/empty-state/panel-
DnD test or POM exists today — the only adjacent coverage is the old zone/docking
model, which is **deleted, not migrated** (`test_panel_zones.py`,
`test_side_toggle.py` → re-expressed as SEC/SPLIT/PERSIST). This task builds the
foundation POMs the other areas reuse.

**POMs to build** (`sections_panel_layout.md` §3; `harness_migration.md` §1):
- `elements/workspace_section.py` (`PlaywrightWorkspaceSection`) — extend the basic
  version from Task 2.7 with the panel-tab sub-POM, `maximize`/`restore`,
  `collapse`/`expand`, `get_resize_handle`, `get_active_ring`.
- `elements/section_split.py` (`PlaywrightSectionSplit`) — `create_split(panel_id,
  direction)`, `get_subsection(half)`, `close_split_from_empty_state(half)`,
  `assert_split_count`, `assert_directions_available`.
- `elements/panel_empty_state.py` (`PlaywrightEmptySectionState`) —
  `get_add_panel_button`, `get_quick_actions` (≤5), `get_quick_action(label)`,
  `get_close_split_button`, `assert_quick_actions([...])`.
- helper functions (`section_helpers.py`): `collapse_section`/`expand_section`/
  `ensure_section_expanded` (replaces the deleted `panels.py`), `maximize_section`/
  `restore_section`, `set_active_section` (click), `cycle_sections(direction)`
  (hotkey), `split_section`/`close_split`, and **`drag_panel_to_section(panel_id,
  target_subsection_id, index)`** (DnD via the `KeyboardSensor` — Task 4.1).

**Test files to CREATE** (`e2e_test_plan.md` §1; `sections_panel_layout.md` §2):
`test_section_default_layout.py` (SEC-01..04/09), `test_section_collapse_expand.py`
(SEC-05..08/20), `test_section_active_and_maximize.py` (SEC-09..16/21, SPLIT-06),
`test_section_resize.py` (SEC-17/22; SEC-18 restored-size aspect),
`test_section_empty_state.py` (SEC-19, SPLIT-04/05), `test_section_splits.py`
(SPLIT-01..06), `test_panel_drag_and_drop.py` (PANEL-08..10/16),
`test_panel_rename_and_close.py` (PANEL-07/11/14 — coordinate with Task 3.7 so
rename/close aren't double-owned, Decision B9).

This task depends on all of Phase 4 (4.1–4.5) and the Phase-2/3 components + the
default-layout seeding (Task 6.1 finalizes SEC-01..04 defaults — if 6.1 lands after
this, assert the minimal default and tighten in Task 6.3; prefer ordering 6.1 before
this if convenient).

## Files to modify/create

- `elements/workspace_section.py` (extend), `elements/section_split.py` (new),
  `elements/panel_empty_state.py` (new), `elements/section_helpers.py` (new) — plus
  delete `elements/panel_zones.py` and rewrite `elements/panels.py` helpers (the
  delete itself is Phase 7; the helper rewrite happens here so tests use the new
  helpers).
- The eight CREATE test files above.

## Implementation details

1. Build the POMs + helpers per `sections_panel_layout.md` §3. The most-leaned-on
   helpers are `drag_panel_to_section` (DnD), `add_panel_via_dropdown`, and the
   panel-tab close→confirmation.
2. `test_section_default_layout.py`: center is the only expanded section with one
   agent of the recent type; left collapsed with Files/Changes/Commits (Files
   active); bottom collapsed with one terminal; right collapsed + empty (SEC-01..04).
   (These assert the **full** default from Task 6.1.)
3. `test_section_collapse_expand.py`: per-section collapse/expand hotkeys; center
   can't collapse; panel-cycle hotkey wraps + no-ops in single/empty; preservation of
   open/active panels across collapse→expand.
4. `test_section_active_and_maximize.py`: active selection + ring fade; cycle incl.
   splits; maximize/restore; maximized section header vs hidden workspace header;
   sidebar-collapsed OS padding (SEC-16); SPLIT-06; maximize not persisted (SEC-21).
5. `test_section_resize.py`: drag each border; min/max clamps (SEC-22); resize is
   pure-geometry (no active-panel/collapse change); "size restored across workspaces"
   (SEC-18 e2e aspect).
6. `test_section_empty_state.py`: add button + ≤5 quick actions (New {recent} agent,
   New terminal, up-to-3 recent-closed); close-split option (SPLIT-04/05).
7. `test_section_splits.py`: right-click "Create {direction} split and move panel";
   per-section directions; one-split-max; (SPLIT-06 lives in the maximize file).
8. `test_panel_drag_and_drop.py`: reorder within a section; drag to another section;
   collapsed-section dropzone expands on drop; split dropzones only while split; no-op
   release leaves placement unchanged; reorder persists across collapse→expand +
   switch (PANEL-16). Drive via `drag_panel_to_section` (`KeyboardSensor`).
9. `test_panel_rename_and_close.py`: rename multi-instance panels; single-instance
   can't rename; close removes from header; per-panel context-menu actions.

## Testing suggestions

- Run via `/run-integration-test` (background + Monitor). Mostly default FakeClaude;
  the empty-state recent-closed variant needs a closed agent/terminal.
- **Do not** write layout-property-only assertions (`.sculptor/testing.md`); verify
  the ring fade / OS padding visuals with screenshots, assert state attributes for
  behavior.

## Gotchas

- DnD must go through the `KeyboardSensor` helper, not Playwright pointer drags
  (flaky).
- Coordinate PANEL-07/11/14 ownership with Task 3.7 (Decision B9) so rename/close
  aren't asserted twice.
- SEC-01..04 assert the full default layout — ensure Task 6.1 seeding is in place (or
  sequence 6.1 first).
- `just generate-api` if any testid changed.

## Verification checklist

- [ ] `workspace_section.py` (extended) + `section_split.py` + `panel_empty_state.py`
  + `section_helpers.py` (incl. `drag_panel_to_section`) exist; `panels.py` helpers
  rewritten.
- [ ] All eight CREATE test files pass via `/run-integration-test`.
- [ ] SEC-01..22, SPLIT-01..06, PANEL-08..10/16 (+ PANEL-07/11/14) covered; no
  layout-only assertions.
