# Task 2.7: Harness spine — rewrite the base POMs (shim) + sidebar/section POMs + smoke tests

## Goal

Rewrite the test-harness spine so the large body of integration tests survives the
Phase 2 cutover: re-point `project_layout.py` and `task_page.py` to drive the new
sidebar/section surfaces **while keeping their method signatures stable** (a
compatibility shim), add the first `WorkspaceSidebar`/`WorkspaceSection` POMs, and
add smoke e2e tests proving cutover works. This unblocks all later test work.

## Stories addressed

SIDE-01/07 (home link + row navigation, smoke), SEC-01 (center agent renders,
smoke). Foundation for every later test task.

## Background

**Project:** Sculptor integration tests are Playwright + pytest under
`sculptor/tests/integration/frontend/` (~207 files). The harness lives in
`sculptor/sculptor/testing/` — `pages/` (layout shells), `elements/` (component
POMs) — with fixtures in `resources.py` /
`tests/integration/frontend/conftest.py` and shared helpers in `playwright_utils.py`.
Test IDs are the `ElementIDs` `StrEnum` in `sculptor/sculptor/constants.py`.

**Why a shim** (`agent_docs/ui_refresh/plan.md` → "Testing approach";
`harness_migration.md` §1): the new shell (Tasks 2.2–2.6) replaces what nearly
every test touches. `project_layout.py` (base of every workspace page; used by ~22
directly, transitively by ~all) and `task_page.py` (48 tests) are built on the old
top-bar/tab model. We rewrite their **internals** to drive the new
sidebar/section surfaces but **keep method signatures stable** where the audits say
to, so the content-only majority (~120 KEEP + mechanical UPDATE tests) keeps
passing. Surfaces that are genuinely gone (tabs, top bar) get their dedicated tests
deleted in Phase 8 — not patched here.

**Key facts from the audits:**
- `sidebar_nav.md`: a `WORKSPACE_ROW` surface already exists in
  `pages/home_page.py` (`get_workspace_rows()`, `WORKSPACE_ROW`,
  `WORKSPACE_ROW_BRANCH`, `WORKSPACE_ROW_CONTEXT_MENU_DELETE`). The sidebar POM
  should **mirror** it, not invent a new row model. Most route-to-feature tests call
  `get_workspace_tabs().nth(i).click()` once — collapse that onto a single
  `navigate_to_workspace()` helper.
- `harness_migration.md` §1: `project_layout.py` — replace the tab API with a
  sidebar + section API but **keep the cross-cutting survivors** (`press_keyboard_
  shortcut`, command palette, warning banner, git-init/add-repo/project-path dialogs,
  keyboard-shortcuts dialog); the command-palette **open** path moves from the topbar
  button to the sidebar (`open_command_palette`). `task_page.py` — `get_workspace_
  banner()` → workspace header; `get_agent_tab_bar()` → section panel-tab POM (full
  POM in Task 3.7; here a thin accessor is fine).

This task depends on **Tasks 2.2–2.6** (the surfaces + their `data-testid`
ElementIDs already added in those tasks). It does **not** remove old ElementIDs for
surfaces that still render in the not-yet-deleted old shell — those removals are
Phase 7.

## Files to modify/create

- `sculptor/sculptor/testing/pages/project_layout.py` — rewrite internals (shim).
- `sculptor/sculptor/testing/pages/task_page.py` — re-home banner→header,
  agent-tab-bar→panel-tab accessor.
- `sculptor/sculptor/testing/elements/workspace_sidebar.py` — new POM
  (`PlaywrightWorkspaceSidebarElement`).
- `sculptor/sculptor/testing/elements/workspace_section.py` — new POM
  (`PlaywrightWorkspaceSection`, basic: section/header/tabs/add/maximize accessors).
- `sculptor/sculptor/testing/playwright_utils.py` — add shared nav helpers
  (`navigate_to_workspace`, `open_settings`, `open_home`, `open_command_palette`).
- `sculptor/tests/integration/frontend/test_workspace_sidebar_smoke.py` — new smoke
  test (or fold into an existing area file).

## Implementation details

1. **`workspace_sidebar.py`** (`harness_migration.md` §1 New POMs; `sidebar_nav.md`
   §3): `get_home_link`, `get_cmdk_link`, `get_new_workspace_button`; repo-group
   getters (`get_repo_groups`, `collapse_repo_group`, `get_repo_add_workspace`,
   `get_repo_settings`); row getters mirroring `PlaywrightHomePage.get_workspace_rows()`
   (`get_workspace_rows`, `get_workspace_row_by_name`, `get_row_delete_icon`,
   `get_row_menu_icon`, `open_row_context_menu`); `get_settings_link`,
   `get_report_bug`, `get_version`, `get_collapse_toggle`, `get_resize_handle`,
   `get_expand_icon`. Target the `SIDEBAR_*` ElementIDs added in Task 2.2.
2. **`workspace_section.py`** (`sections_panel_layout.md` §3): constructed with a
   `SubSectionId`; `get_section`, `get_header`, `get_panel_tabs`,
   `get_panel_tab(panel_id)`, `get_active_tab`, `get_add_panel_button`,
   `get_maximize_button`. (Splits/empty-state/PanelTab sub-POM are Tasks 3.7/4.6.)
3. **`project_layout.py` shim:** remove the tab getters, add `get_workspace_sidebar()`
   + section accessors, keep the cross-cutting survivors, and move `open_command_
   palette` onto the sidebar link. Re-point `navigate_to_home_page` to
   `SIDEBAR_HOME_LINK`.
4. **`task_page.py`:** `get_workspace_banner()` → `get_workspace_header()` (new
   header); `get_agent_tab_bar()` → a thin panel-tab accessor over
   `workspace_section.py` (full `PanelTab` in Task 3.7). Move PR-button + diff-summary
   getters with the header.
5. **`playwright_utils.py` nav helpers** (`sidebar_nav.md` §3): `navigate_to_workspace
   (page, name|index)` (replaces `get_workspace_tabs().nth(i).click()`),
   `open_settings`, `open_home`, `open_command_palette`. These are the
   "swap-not-rewrite" surface the ~18 route-to-feature UPDATE tests use in Phase 8.
6. **Smoke tests** (via `/run-integration-test`, never `pytest` directly): the
   sidebar renders with home/Cmd+K/new-workspace links and at least one workspace
   row; clicking a row navigates to the workspace (SIDE-07); the center section
   renders the active agent's chat (SEC-01/AGENT-01); the workspace header renders.
7. Run `just generate-api` if any ElementID was added here (most were added in
   Tasks 2.2–2.4).

## Testing suggestions

- Use the `/run-integration-test` skill for the smoke tests (run as a background
  process with a Monitor watchdog, per the skill).
- Don't try to make the entire legacy suite green here — that is Phase 8. The goal is
  that the **content-only majority** still passes via the shim, and the new smoke
  tests pass.

## Gotchas

- **Keep signatures stable** where the audits say to (especially the cross-cutting
  survivors and the soon-to-come `create_workspace()` in Task 5.4). Renaming them
  forces edits across hundreds of importers.
- Do **not** delete ElementIDs whose surfaces still render in the old (not-yet-
  removed) shell — Phase 7 removes those. Deleting them now breaks the old shell's
  own (still-present) code and the generated types.
- Mirror the existing `WORKSPACE_ROW` shape for sidebar rows; don't invent a new row
  model.
- Always `just generate-api` after touching `constants.py`.

## Verification checklist

- [ ] `project_layout.py` / `task_page.py` drive the new surfaces with stable
  signatures (shim); cross-cutting survivors kept.
- [ ] `workspace_sidebar.py` + `workspace_section.py` POMs exist and target the new
  `data-testid`s.
- [ ] `navigate_to_workspace`/`open_settings`/`open_home`/`open_command_palette`
  helpers added.
- [ ] Smoke e2e (sidebar + row-navigate + center agent + header) passes via
  `/run-integration-test`.
- [ ] No still-rendered ElementIDs removed; `just generate-api` run if needed;
  `just check` passes.
