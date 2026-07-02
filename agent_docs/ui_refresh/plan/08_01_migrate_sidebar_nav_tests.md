# Task 8.1: Migrate the sidebar / navigation legacy tests

## Goal

Execute the sidebar/navigation slice of `e2e_test_plan.md`: UPDATE the route-to-
feature long tail to the shared nav helpers, REWRITE the workspace-row/sidebar tests
that replaced tab surfaces, DELETE the tab-model sub-tests, and finish the net-new
sidebar CREATE files. Brings the suite back to green for the sidebar area.

## Stories addressed

SIDE-01..17 (the full sidebar area), via the consolidated/migrated files.

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`. Run
via **`/run-integration-test`**; `just generate-api` after `ElementIDs` changes. The
new sidebar/section surfaces + POMs + the harness shim already exist (Phases 2–7).

**The migration** (`e2e_test_plan.md` §1/§3/§4c; `sidebar_nav.md` §4): the old top
bar + tab strip became the sidebar + workspace header. Most route-to-feature tests
call `get_workspace_tabs().nth(i).click()` once — swap to `navigate_to_workspace()`
(Task 2.7 helper). The workspace-tab context menu / peek / close-vs-delete move to the
workspace **row**. The tab-model stories (home/settings/workspace **tabs**, close/
close-others, new-ws-tab transition) are deleted.

**Work items** (`sidebar_nav.md` §4):
- **UPDATE-in-place (route-to-feature long tail, ~25 files):** swap
  `get_workspace_tabs()`/`get_add_workspace_button()` → `navigate_to_workspace()`/
  `new_workspace()` — e.g. `test_agent_settings`, `test_alpha_chat_intro`,
  `test_alpha_scroll_task_switch`, `test_entity_mention_persistence`,
  `test_keybindings`, `test_multi_agent_workspace`, `test_queued_messages`,
  `test_status_pill`, `test_theme_builder`, `test_workspace_deletion_cleanup`, …
  (the full `project_layout`-method set). `test_command_palette.py` → re-point the
  topbar Cmd+K button to the sidebar link; rest KEEP.
- **REWRITE (+rename):** `test_workspace_row_context_menu.py` (rebuilds
  `test_workspace_tab_context_menu_icons` + `test_workspace_diagnostics_context_menu`),
  `test_workspace_row_hover_actions.py` (rebuilds `test_workspace_peek`, drops the
  scrolled-tab test), `test_settings_navigation.py` (from `test_settings_tab`),
  `test_workspace_optimistic_deletion.py` (workspace half of `test_optimistic_deletion`
  + `test_optimistic_close`), and the row close-vs-delete survivors of
  `test_workspace_close_vs_delete.py`. `test_read_unread_status.py` (ws-level) +
  `test_mark_unread.py` (ws-switch) → re-anchor `data-has-unread` to the sidebar row.
- **CREATE/finish:** `test_workspace_sidebar.py` (SIDE-01..12, absorbs
  `test_home_page_tab` + `test_settings_tab`) and `test_sidebar_collapse_resize.py`
  (SIDE-13/14/15) — if not already created in Task 2.7, complete them here.
- **DELETE:** the tab-model sub-tests inside `test_home_page_tab`, `test_settings_tab`,
  `test_workspace_tab_enhancements`, `test_workspace_close_vs_delete` (close-all/
  others-tabs, new-ws-tab transition). (`test_closed_workspaces_dropdown` +
  Component-Gallery tests were deleted in Phase 7.)

New stories: SIDE-16 (optimistic ws delete + rollback toast) and SIDE-17 (ws-level
unread on the row).

This task depends on **Phases 2–7** (surfaces, POMs, removals).

## Files to modify/create

- The ~25 UPDATE-in-place route-to-feature files (mechanical helper swap).
- `test_workspace_row_context_menu.py`, `test_workspace_row_hover_actions.py`,
  `test_settings_navigation.py`, `test_workspace_optimistic_deletion.py` — REWRITE/new.
- `test_workspace_sidebar.py`, `test_sidebar_collapse_resize.py` — complete if needed.
- `test_command_palette.py`, `test_read_unread_status.py`, `test_mark_unread.py` —
  UPDATE.
- Remove the migrated/obsolete source files (`test_home_page_tab.py`,
  `test_settings_tab.py`, `test_workspace_tab_context_menu_icons.py`,
  `test_workspace_diagnostics_context_menu.py`, `test_workspace_peek.py`,
  `test_optimistic_close.py`) once their assertions land. **Also delete the original
  `test_optimistic_deletion.py` here** — its agent half migrated to
  `test_panel_optimistic_deletion.py` (Task 3.7) and its workspace half to
  `test_workspace_optimistic_deletion.py` (this task); delete it once **both** halves
  are green, so nothing is left asserting the old auto-create-on-last-delete.

## Implementation details

1. Do the **UPDATE** swaps first (mechanical, high-volume): replace tab clicks with
   `navigate_to_workspace()`; replace add-workspace navigation with `new_workspace()`/
   `open_new_workspace_dialog()`. No assertion changes.
2. REWRITE the row context-menu / hover / settings-navigation / optimistic-delete
   tests against the sidebar row (reuse the `workspace_sidebar.py` POM, Task 2.7).
3. Re-anchor `data-has-unread` assertions to `SIDEBAR_WORKSPACE_ROW` (SIDE-17);
   optimistic delete + rollback toast (SIDE-16).
4. DELETE the tab-model sub-tests; remove the obsolete source files after migration.
5. Keep the workspace-row context menu and the panel-tab context menu **distinct**
   (Decision B9 / the `TAB_CONTEXT_MENU_*` split) so the two areas don't collide.

## Testing suggestions

- Run the sidebar area via `/run-integration-test` (background + Monitor). The UPDATE
  long tail should pass with only the helper swap; the REWRITEs need the sidebar POM.

## Gotchas

- The UPDATE swap is mechanical — don't change assertions, only the reach.
- Workspace-row menu vs. panel-tab menu are separate now — don't reintroduce the shared
  tab menu.
- Drop the scrolled-tab peek test (no tab strip to overflow).
- Remove obsolete source files after migrating — no orphans asserting removed surfaces.
- `test_optimistic_deletion.py` is **split** (agent → Task 3.7, workspace → here) and
  **deleted here** after both halves land — it is not an UPDATE target despite the §4a
  POM-importer list.
- `test_theme_builder.py`'s Component-Gallery assertion was already removed in Task 7.3
  — the Phase 8 pass here is only the nav-helper swap (don't re-touch the gallery).

## Verification checklist

- [ ] Route-to-feature long tail swapped to `navigate_to_workspace()`/`new_workspace()`;
  assertions unchanged.
- [ ] Row context-menu / hover / settings-nav / optimistic-delete REWRITTEN against the
  sidebar row; unread re-anchored (SIDE-16/17).
- [ ] `test_workspace_sidebar.py` + `test_sidebar_collapse_resize.py` complete; tab-
  model sub-tests deleted; obsolete sources removed.
- [ ] Sidebar area green via `/run-integration-test`; `just check` passes.
