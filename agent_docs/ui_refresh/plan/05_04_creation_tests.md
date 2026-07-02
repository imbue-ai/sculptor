# Task 5.4: Creation/first-run POMs + create_workspace() shim + WSC/FIRST tests

## Goal

Build the new-workspace-dialog and empty-first-run POMs, rewrite the load-bearing
`create_workspace()` helper to drive the dialog **while keeping its signature**, and
create the workspace-creation + first-run e2e tests (migrating real bodies from the
old page tests).

## Stories addressed

WSC-01..11 (`test_new_workspace_dialog.py` + `test_new_workspace_creation_modes.py`),
FIRST-01..05 (`test_empty_first_run.py` — FIRST-05 asserts navigation + that the full
workspace page is shown; the SEC-01..04 default-**arrangement** assertion lives in
`test_section_default_layout.py` (Task 6.3), which runs after the 6.1 seed), plus the
autocomplete-Cmd+Enter guard (a negative-path **test case**, not a numbered story).

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`. Run
via **`/run-integration-test`**; write via **`/write-integration-test`**;
`just generate-api` after `ElementIDs` changes.

**The load-bearing helper** (`workspace_creation.md` §3; `harness_migration.md` §1):
`playwright_utils.start_task_and_wait_for_ready` is imported by **~177 tests**. Refactor
it into `create_workspace(...)` **keeping the exact signature** (`prompt`,
`model_name`, `workspace_name`, `mode`, `agent_type`, `wait_for_agent_to_finish`) and
rewrite only the internals: replace `navigate_to_add_workspace_page` +
`START_TASK_BUTTON` with "open dialog → fill → Create". Then the ~17
create-to-reach-a-feature tests swap **zero** call sites. Also rename
`navigate_to_add_workspace_page` (19 importers) → `open_new_workspace_dialog`.

**POMs** (`workspace_creation.md` §3; `harness_migration.md` §1):
- `elements/new_workspace_dialog.py` (`PlaywrightNewWorkspaceDialog`) — replaces
  `pages/add_workspace_page.py`. Port the form getters verbatim (`get_task_input`,
  `get_workspace_name_input`, `get_branch_name_input`, `get_branch_name_collision_error`,
  `get_branch_selector`/`select_branch`, `get_mode_selector`/`select_mode`,
  `get_project_selector`/`select_project_by_name`, `get_open_new_repo_button`,
  `get_submit_button`). **Add** WSC-05/06 getters (`get_prompt_textarea`,
  `get_context_pills`, `get_keep_open_switch`, `get_branch_shuffle_button`,
  `get_create_button`) and openers (`open_via_sidebar_button`, `open_via_shortcut`,
  `open_via_command_palette`, `open_via_repo_plus`). Note: `PlaywrightAddWorkspacePage`
  subclasses `PlaywrightProjectLayoutPage` — the dialog POM should compose the new
  sidebar/section base (Task 2.7 rewrote it).
- `elements/empty_first_run.py` (`PlaywrightEmptyFirstRun`) — the inline form +
  sidebar repo-area getters (`get_add_repo_button`, `get_no_workspaces_hint`).

**Test files to CREATE** (`workspace_creation.md` §2):
- `test_new_workspace_dialog.py` (WSC-01..05/07, FIRST-04) — modal shell + four entry
  points + form; rebuilds form-persistence/Cmd+Enter/Cmd+I/arrow-key/create-without-
  prompt/focus from `test_add_workspace_page.py`; agent-type picker (absorbs
  `test_add_workspace_agent_type.py`: Claude default, pi gated, **no bare Terminal** —
  Decision B2, MRU). Drops the tab-model stories.
- `test_new_workspace_creation_modes.py` (WSC-06/08/09/10) — branch pill
  (sanitize/shuffle/error slot) + collision; mode selector; source-branch; cleared-vs-
  kept branch. Migrates real bodies from `test_branch_name_collisions`,
  `test_clone_mode_branch_name`, `test_worktree_create_happy_path`,
  `test_worktree_edge_cases`, and the source-branch halves of
  `test_branch_switching_integration`/`test_clone_local_only_branch` (git checks
  unchanged).
- `test_empty_first_run.py` (FIRST-01..05) — uses `sculptor_instance_factory_`
  (fresh zero-workspace instance).

This task depends on **Tasks 5.1–5.3** and the Phase-2 harness spine.

## Files to modify/create

- `sculptor/sculptor/testing/elements/new_workspace_dialog.py` — new (from
  `pages/add_workspace_page.py`, which is deleted in Task 7.3).
- `sculptor/sculptor/testing/elements/empty_first_run.py` — new.
- `sculptor/sculptor/testing/playwright_utils.py` — rewrite `create_workspace()`
  internals (keep signature); rename `navigate_to_add_workspace_page` →
  `open_new_workspace_dialog`.
- `test_new_workspace_dialog.py`, `test_new_workspace_creation_modes.py`,
  `test_empty_first_run.py` — new.
- Fixtures (`resources.py`/`conftest.py`): add a **zero-workspace** variant for
  `test_empty_first_run.py` (confirm setup doesn't auto-create a first workspace).

## Implementation details

1. Build `new_workspace_dialog.py` porting the form getters verbatim + the new WSC-05/06
   getters + openers; compose the new sidebar/section base.
2. Rewrite `create_workspace()` internals to open the dialog → fill → Create, keeping
   the signature so the ~177 importers are untouched. Rename
   `navigate_to_add_workspace_page` → `open_new_workspace_dialog` (update its 19
   importers — mechanical).
3. Write the three CREATE files; migrate the real test bodies listed above. **Drop**
   the tab-model stories (multiple new-workspace tabs, no-extra-tab-flash, `/ws/new`
   draft) — they die with the tab model.
4. Autocomplete-Cmd+Enter guard (negative-path test case): Cmd+Enter inside the
   repo-path autocomplete must not create the workspace (port the negative-path test).
5. Add the zero-workspace fixture for `test_empty_first_run.py`.

## Testing suggestions

- Run via `/run-integration-test` (background + Monitor). Mostly default FakeClaude;
  one local-only assertion needs `write_file`. The `enable_clone_workspaces`/
  `enable_in_place_workspaces` flag paths survive.
- Confirm the ~17 create-to-reach-a-feature tests still pass unchanged (the
  `create_workspace()` signature held).

## Gotchas

- **Keep `create_workspace()`'s signature** — renaming/changing it forces edits across
  ~177 importers.
- Drop the tab-model creation stories; they have no successor.
- `test_empty_first_run.py` needs a genuinely zero-workspace instance — verify the
  fixture doesn't auto-create one.
- No bare "Terminal" agent type in the dialog picker (Decision B2).
- `pages/add_workspace_page.py` is deleted in Task 7.3 — its getters live on in the
  dialog POM.

## Verification checklist

- [ ] `new_workspace_dialog.py` + `empty_first_run.py` POMs built;
  `create_workspace()` keeps its signature with rewritten internals;
  `navigate_to_add_workspace_page` → `open_new_workspace_dialog`.
- [ ] `test_new_workspace_dialog.py` / `test_new_workspace_creation_modes.py` /
  `test_empty_first_run.py` pass via `/run-integration-test`.
- [ ] WSC-01..11 + FIRST-01..06 covered; tab-model stories dropped; zero-workspace
  fixture added.
- [ ] The ~17 create-to-reach-a-feature tests still pass unchanged.
