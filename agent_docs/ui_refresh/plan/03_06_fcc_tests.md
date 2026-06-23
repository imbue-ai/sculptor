# Task 3.6: FCC POMs + Files/Changes/Commits/DiffViewer tests (migrate-and-consolidate)

## Goal

Build the shared Files/Changes/Commits test POMs and the four FCC test files,
migrating the proven diff/file/history assertions from today's suite into them via
the shared `DiffViewer` / `MasterDetailPanel` POMs. The content assertions are
**migrated, not rewritten**; the source files are removed once migrated.

## Stories addressed

FCC-01..07 (the three panels, each with its own viewer; sidebar list; shared global
width; always-visible viewer + empty state; config in the triple-dot menu).

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`.
Run via the **`/run-integration-test`** skill (never `pytest` directly). New tests
are written with the **`/write-integration-test`** skill conventions (FakeClaude for
deterministic agent behavior). After any `ElementIDs` change, run `just generate-api`.

**The plan** (`e2e_test_plan.md` §1 + §4e; `harness_migration.md` §1): the old
single file-browser panel (All/Changes/History tabs + a shared diff panel) becomes
three panels each with its own embedded viewer. To avoid triplicating selectors, the
POMs are factored:
- **`DiffViewer`** POM (refactor of today's `diff_panel.py`, now embeddable per
  panel) — tabs, scopes, line numbers, and the toggles relocated under the
  triple-dot menu (`DIFF_FILE_HEADER_MENU_TRIGGER`); **`get_expand_toggle` is
  deleted** (fullscreen-expand deprecated).
- **`MasterDetailPanel`** POM — resizable list, shared-width sidebar, sidebar
  toggle, empty state.
- helper functions: `open_file_in_panel`, `toggle_view_option_via_menu`,
  `assert_diff_shows`.

`test_diff_viewer.py` exercises the shared viewer once; the three panel files assert
only their panel-specific sidebar/list behavior. The content assertions **move
across unchanged**; source files are removed after migration (consolidation, not
in-place editing).

**Migration sources** (`e2e_test_plan.md` §4e): `test_file_browser.py`,
`test_file_browser_tabs.py`, `test_file_browser_uncommitted.py`,
`test_file_browser_symlink_replaces_directory.py`, `test_file_open_diff_modes.py`,
`test_history_panel.py`, `test_history_panel_diffs.py`, `test_diff_scope_switching.py`,
`test_diff_refresh_on_branch_change.py`, `test_diff_tab_close_others.py`,
`test_diff_loading_bar_no_file.py`, `test_commit_from_changes_tab.py`,
`test_discard_file.py`, `test_discard_preserves_all_tab.py`, `test_target_branch.py`,
`test_markdown_render_toggle.py`, `test_markdown_gfm.py`, `test_open_in_viewer.py`,
`test_path_tilde_display.py`. The per-diff fullscreen half of
`test_diff_scope_and_fullscreen.py` is **dropped** (deprecated); `test_expand_escape.py`
is DELETEd (Phase 7).

This task depends on **Task 3.2** (the components) and **Task 3.3** (the panels).

## Files to modify/create

- `sculptor/sculptor/testing/elements/diff_viewer.py` — refactor of `diff_panel.py`
  (embeddable; toggles under the triple-dot menu; `get_expand_toggle` removed).
- `sculptor/sculptor/testing/elements/master_detail_panel.py` — new shared POM +
  helper functions.
- `sculptor/sculptor/testing/elements/files_panel.py` — refactor of
  `file_browser.py` (drop the `get_tab_all/changes/history` getters).
- `sculptor/sculptor/testing/elements/changes_panel.py` — keep/re-anchor to its own
  embedded viewer.
- `sculptor/sculptor/testing/elements/commits_panel.py` — rename of
  `history_panel.py`.
- `sculptor/tests/integration/frontend/test_files_panel.py`,
  `test_changes_panel.py`, `test_commits_panel.py`, `test_diff_viewer.py` — new
  (migrated content).
- Remove the migrated source `test_*` files once their assertions land.

## Implementation details

1. Build the `DiffViewer` + `MasterDetailPanel` POMs + helpers per
   `harness_migration.md` §1. Re-anchor the toggle getters under
   `DIFF_FILE_HEADER_MENU_TRIGGER`; remove the expand-toggle getter.
2. `test_diff_viewer.py` (FCC-02/06/07): exercise the shared viewer once via whichever
   panel is convenient — file/diff tabs, split/unified + wrap + render toggles (now
   under the menu), find-in-file, line numbers/expansion, moved-file (R) rendering,
   loading bar only when a file is open, GFM + sanitization, open-from-chat. Migrate
   from `test_diff_*`/`test_markdown_*`/`test_open_in_viewer.py`.
3. `test_files_panel.py` (FCC-01..07): file tree + its own viewer; shared-width
   sidebar resize/toggle; always-visible viewer + empty state; triple-dot menu.
   Migrate Browse/tree assertions from `test_file_browser*`/`test_file_open_diff_modes`/
   `test_path_tilde_display`/`test_file_browser_symlink*`.
4. `test_changes_panel.py`: changes list + scope picker (All/Uncommitted) + its own
   viewer; discard + commit-from-changes; clears after commit. Migrate from
   `test_file_browser_uncommitted`/`test_commit_from_changes_tab`/`test_discard_*`/
   `test_diff_scope_switching`/`test_target_branch*`.
5. `test_commits_panel.py`: history list (terminus, merge spur, metadata, popover) +
   commit-scoped diffs. Migrate from `test_history_panel`/`test_history_panel_diffs`.
6. Remove the source `test_*` files after their assertions are migrated.
7. Skip **purely visual** assertions (per `.sculptor/testing.md` — no
   layout-property-only tests; verify those with screenshots).

## Testing suggestions

- Run the four files via `/run-integration-test` (background + Monitor watchdog).
- FakeClaude: controlled for file writes / commits where the audits flag it.
- Confirm no migrated source file is left behind asserting a removed surface.

## Gotchas

- Do **not** rewrite the content assertions — move them across unchanged via the
  shared POMs (the behavior is preserved; only the panel home + toggle location
  changed).
- The expand/fullscreen toggle is gone — don't add a POM alias; section-maximize
  (SEC-13/15) is the generic replacement.
- Three separate panels — `FILE_BROWSER_TAB_*` selectors are gone.
- `just generate-api` if you touch `constants.py`.

## Verification checklist

- [ ] `diff_viewer.py` (embeddable, menu-anchored toggles, no expand) +
  `master_detail_panel.py` + helpers exist.
- [ ] `test_files_panel.py` / `test_changes_panel.py` / `test_commits_panel.py` /
  `test_diff_viewer.py` pass via `/run-integration-test`.
- [ ] Migrated source `test_*` files removed; no orphan asserting a removed surface.
- [ ] FCC-01..07 covered; no layout-only visual assertions.
