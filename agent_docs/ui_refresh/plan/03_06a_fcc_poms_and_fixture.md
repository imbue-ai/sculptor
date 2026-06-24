# Task 3.6a: FCC test harness — shared POMs + open-a-panel helper

## Goal

Build the shared Files/Changes/Commits test harness that Tasks 3.6b–e consume: the
embeddable `DiffViewer` POM, the `ExplorerLayout` POM, the three per-panel POMs, the
helper functions, and a shared **open-a-panel helper** that opens a panel by clicking
through the UI. **No content tests are migrated here** — only the harness, verified by
a tiny smoke check.

## Stories addressed

FCC-01..07 (harness foundation only — the content assertions land in 3.6b–e).

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`.
Run via the **`/run-integration-test`** skill (never `pytest` directly). New tests
use the **`/write-integration-test`** conventions (FakeClaude). After any
`ElementIDs` change, run `just generate-api`.

**Why a separate harness task.** The FCC migration is large (~19 source files /
~5.7k LOC). Building the POMs + helper **once, up front** de-risks the migration and
lets each panel's tests (3.6b–e) land as a small, independently-runnable, bisectable
slice instead of one big-bang migrate-and-delete pass. 3.6b–e each depend only on this
task.

**POM factoring** (`harness_migration.md` §1): the old single file-browser panel
(All/Changes/History tabs + a shared diff panel) becomes three panels, each with its
own embedded viewer. To avoid triplicating selectors:
- **`DiffViewer`** POM (refactor of today's `diff_panel.py`, now embeddable per
  panel) — tabs, scopes, line numbers, and the toggles relocated under the triple-dot
  menu (`DIFF_FILE_HEADER_MENU_TRIGGER`); **`get_expand_toggle` is removed**
  (fullscreen-expand deprecated).
- **`ExplorerLayout`** POM — resizable list, shared-width sidebar, sidebar toggle,
  empty state.
- Per-panel POMs: `files_panel.py` (refactor of `file_browser.py`, dropping the
  `get_tab_all/changes/history` getters), `changes_panel.py` (re-anchored to its own
  embedded viewer), `commits_panel.py` (rename of `history_panel.py`).
- Helpers: `open_file_in_panel`, `toggle_view_option_via_menu`, `assert_diff_shows`.

**The open-a-panel helper** (`harness_migration.md` §3): the Files/Changes/Commits
panels are not in the default layout at this point in the build, so a content test
brings its panel on screen the way a user does — by clicking the section `+`
add-panel dropdown (reusing the `AddPanelDropdown` POM). One shared helper encapsulates
that open flow so the ~19 migrated content tests don't each re-implement it. The
agent/terminal content tests (Task 3.7) open their panel the same way.

This task depends on **Task 3.2** (components), **Task 3.3** (panels), and **Task 3.5**
(the `AddPanelDropdown` the open helper drives).

## Files to modify/create

- `sculptor/sculptor/testing/elements/diff_viewer.py` — refactor of `diff_panel.py`
  (embeddable; toggles under the triple-dot menu; `get_expand_toggle` removed).
- `sculptor/sculptor/testing/elements/explorer_layout.py` — new shared POM + helpers.
- `sculptor/sculptor/testing/elements/files_panel.py` — refactor of `file_browser.py`
  (drop `get_tab_all/changes/history`).
- `sculptor/sculptor/testing/elements/changes_panel.py` — re-anchor to its own
  embedded viewer.
- `sculptor/sculptor/testing/elements/commits_panel.py` — rename of `history_panel.py`.
- The shared open-a-panel helper in `sculptor/sculptor/testing/` — opens a panel by
  clicking the section `+` add-panel dropdown (reusing the `AddPanelDropdown` POM).
- A tiny smoke check (may live in `test_files_panel.py` from 3.6c, or a throwaway
  `test_fcc_harness_smoke.py` deleted once 3.6c lands).

## Implementation details

1. Build the POMs + helpers per `harness_migration.md` §1; re-anchor the toggle
   getters under `DIFF_FILE_HEADER_MENU_TRIGGER`; remove the expand-toggle getter.
2. Build the open-a-panel helper: click the section `+` to open the `AddPanelDropdown`
   and select the target panel (Files / Changes / Commits), then return its POM. Reuse
   the `AddPanelDropdown` POM rather than re-implementing the dropdown reach.
3. Smoke-test only: open Files via the helper and assert the `ExplorerLayout` list +
   `DiffViewer` render. **No content migration here.**

## Testing suggestions

- Run the smoke check via `/run-integration-test` (background + Monitor watchdog).

## Gotchas

- Open panels **through the UI** (the add-panel dropdown) — do not poke localStorage or
  layout state to arrange them.
- The real default placement (left-collapsed, Files active — SEC-02) is a separate
  concern, tested in `test_section_default_layout.py` (Task 6.3); don't assert it here.
- The expand/fullscreen toggle is gone — don't add a POM alias; section-maximize
  (SEC-13/15) is the generic replacement.
- `FILE_BROWSER_TAB_*` selectors are gone (three separate panels).
- `just generate-api` after any `constants.py`/`ElementIDs` change.

## Verification checklist

- [ ] `diff_viewer.py` (embeddable, menu-anchored toggles, no expand) +
  `explorer_layout.py` + `files/changes/commits_panel.py` + helpers exist.
- [ ] The open-a-panel helper opens a panel via the add-panel dropdown and returns its
  POM.
- [ ] Smoke check passes via `/run-integration-test`.
- [ ] `just generate-api`; `just check` passes.
