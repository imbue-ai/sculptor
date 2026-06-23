# E2E test plan — workspace UI refresh

The concrete work to bring the frontend integration suite
(`sculptor/tests/integration/frontend/`, 209 files today) in line with the
redesign. Stories referenced by ID are defined in `user_stories.md`. The
test-harness changes (page objects, ElementIDs, fixtures, the terminology
rename) live in `harness_migration.md` — this doc points at it rather than
repeating it.

## How to read this

- **Actions** applied to each test:
  - **CREATE** — a new test for a new behavior.
  - **DELETE** — remove; the feature is gone.
  - **REWRITE** — the behavior survives but its surface is replaced, so the test
    body is rebuilt against the new surface (a REWRITE is also RENAMEd).
  - **UPDATE** — behavior and assertions are unchanged; only the harness path
    (POM methods / selectors) is swapped to reach the panel in its new home.
  - **RENAME** — behavior and assertions are unchanged; the file, test
    functions, and `@user_story` text are realigned to the new vocabulary.
    Per the project decision, **every test that carries old vocabulary is
    RENAMEd even when nothing else changes.**
- The **story mapping is many-to-many**: a row may list several story IDs, and a
  story ID appears in whatever rows cover it. The Coverage map at the end is the
  authoritative story → test index.
- `[perf]` stories (SWITCH-01/02/05, SEC-18, PERSIST-02) are **not** Playwright
  tests — they map to the `measure-react-renders` skill and a workspace-switch
  profiler. They are listed in the Coverage map but never get a `test_*.py`.
- File counts/lists were derived by grepping the live suite (imports + `@user_story`
  text), not from the prototype branches' notes.
- We deep-analyzed the existing tests for each major area the redesign touches to
  verify all functionality is carried over. Those per-area audits are in
  `supplemental/test_area_audits/`; this doc is the consolidated plan.
- The concrete panel set and ids come from `supplemental/panel_registry.md`; the
  vocabulary/rename map from `supplemental/naming_map.md`. **Registered static
  panels** (single-instance): Files, Changes, Commits, Review All, Actions, Skills,
  Browser, Notes — plus dynamic agent (`agent:<taskId>`) and terminal
  (`terminal:<wsId>:<n>`). There is **no panel enable/disable** anymore (the Panels
  settings page and its enabled/built-in flags are deleted), which reclassifies the
  Notes and Browser tests below.

---

## 1. CREATE — new tests for new behaviors

Proposed new files (names indicative). FakeClaude column notes whether agent
behavior must be controlled or the default response suffices.

| New file | Stories | FakeClaude | Notes |
|---|---|---|---|
| `test_workspace_sidebar.py` | SIDE-01..07, 10, 11, 12 | default | Core nav: home/Cmd+K/new-workspace links, repo groups (collapse/add-workspace/repo-settings), row click→navigate, Settings link, report-bug, version. Absorbs `test_home_page_tab.py` + `test_settings_tab.py`. |
| `test_sidebar_collapse_resize.py` | SIDE-13, 14, 15 | default | Collapse-to-icon (no collision with OS window controls on home), drag-resize + min-width clamp, toggle hotkey. Net-new (no live coverage). |
| `test_workspace_row_context_menu.py` | SIDE-08 | default | Right-click row → rename / copy name·branch·id / diagnostics / delete. Rebuilds `test_workspace_tab_context_menu_icons.py` + `test_workspace_diagnostics_context_menu.py`. |
| `test_workspace_row_hover_actions.py` | SIDE-07, 09 | default (peek: `text`/`ask_user_question`) | Hover row → delete + menu icons; hover → peek popover. Rebuilds `test_workspace_peek.py` (drops the scrolled-tab test). |
| `test_settings_navigation.py` | SIDE-10 | default | Settings as a full-route sidebar destination: open Settings, then return by clicking a workspace row (SIDE-07). No closeable Settings tab. May fold into `test_workspace_sidebar.py`. |
| `test_section_default_layout.py` | SEC-01..04 | default | Asserts the first-open default arrangement (center agent; left/bottom/right collapsed with their seed panels). |
| `test_section_collapse_expand.py` | SEC-05..08, SEC-20 | default | Per-section collapse/expand hotkeys; center cannot collapse; panel-cycle hotkey; preservation of open/active panels. |
| `test_section_active_and_maximize.py` | SEC-09..16, SEC-21 | default | Active-section selection + ring fade; cycle incl. splits; maximize/restore; maximized header vs workspace header; sidebar-collapsed OS padding; maximize does not persist across reload (SEC-21). |
| `test_section_resize.py` | SEC-17, SEC-22, SEC-18→perf | default | Drag-resize per border; min/max clamps (SEC-22); global-size asserted at e2e only as "size restored across workspaces" (zero-reflow is `[perf]`). Test case: resize is pure-geometry — it does not change the active panel or any collapse/expand state. |
| `test_section_empty_state.py` | SEC-19, SPLIT-04, SPLIT-05 | default | Empty-state add button + ≤5 quick actions (New {recent} agent, New terminal, up-to-3 recent-closed); close-split option. |
| `test_section_splits.py` | SPLIT-01..06 | default | Right-click "Create {direction} split and move panel"; direction set per section; one-split-max; maximize shows one sub-section. |
| `test_panel_add_dropdown.py` (co-owned Sections + Agent/terminal) | PANEL-01..06, PANEL-12, PANEL-15 | controlled (agent types) | Section `+` dropdown contents/order; recent-agent pin + binding; type sub-menu; New terminal; single-instance list; center-targeting of Cmd+Shift+T / Cmd+K. Replaces the prototype's cmd+k-overlay — `goals.md` mandates a **dropdown**. Sections owns dropdown mechanics; Agent/terminal owns the agent/terminal-type assertions (absorbs `test_agent_type_menu.py`). |
| `test_panel_drag_and_drop.py` | PANEL-08, PANEL-09, PANEL-10, PANEL-16 | default | Reorder within a section (PANEL-16: order persists across collapse→expand and switch); drag to another section; collapsed-section dropzone expands on drop; split dropzones only while split exists. Test case: a no-op release outside any dropzone leaves placement unchanged. Driven via the `KeyboardSensor` + drag handle (see `harness_migration.md` §Drag-and-drop testability). |
| `test_panel_rename_and_close.py` | PANEL-07, PANEL-11, PANEL-14 | default | Rename multi-instance panels; single-instance can't rename; close removes from header; per-panel context-menu actions. |
| `test_agent_panel.py` | AGENT-01..04 | controlled | Agent panel preserves chat; zero/one/multiple agents; agent in center + right at once; close = delete-confirmation. Absorbs much of today's `test_multi_agent_workspace.py`. |
| `test_agent_concurrent_streaming.py` | AGENT-05 | controlled (two streaming tasks) | **Regression.** Two agents in different sections streaming at once; assert both update independently, neither blocks/drops the other. |
| `test_terminal_panel.py` | TERM-01, TERM-02, TERM-03 | default | Terminal as a panel; multiple terminals; switch; numbering; close = confirmation (TERM-02 is **new** — today terminal close has no confirm). Absorbs the add/switch/close/number tab-model half of `test_terminal.py`. |
| `test_panel_tab_context_menu.py` | PANEL-07, 11, 14, AGENT-04, AGENT-06, TERM-02 | controlled | The shared panel-tab context menu on agent **and** terminal tabs: rename (multi-instance only), close=delete/close-confirm, diagnostics submenu, mark-unread, copy-id. Consolidates `test_agent_tab_context_menu.py` + `test_agent_diagnostics_context_menu.py` + the rename/context halves of `test_terminal_tab_enhancements.py` / `test_tab_context_menus.py`. |
| `test_panel_optimistic_deletion.py` | AGENT-04, AGENT-08 | controlled / route-intercept | Agent half of `test_optimistic_deletion.py`: optimistic removal, 500→rollback+toast+Retry, and closing the last agent leaves the center empty (AGENT-04 — replaces the old "auto-create new" assertion). Workspace half → `test_workspace_optimistic_deletion.py` (Sidebar). |
| `test_files_panel.py` | FCC-01..07 | controlled (file writes) | Files panel: file tree + its own viewer; shared-width sidebar resize/toggle; always-visible viewer + empty state; triple-dot menu. Migrates Browse/tree assertions from `test_file_browser.py`, `test_file_open_diff_modes.py`, `test_path_tilde_display.py`, `test_file_browser_symlink_replaces_directory.py`. |
| `test_changes_panel.py` | FCC-01..07 | controlled (writes/commits) | Changes panel: changes list + scope picker (All/Uncommitted) + its own viewer; discard + commit-from-changes; clears after commit. Migrates `test_file_browser_uncommitted.py`, `test_commit_from_changes_tab.py`, `test_discard_file.py`, `test_discard_preserves_all_tab.py`, `test_diff_scope_switching.py`, `test_target_branch*.py`. |
| `test_commits_panel.py` | FCC-01..07 | controlled (commits) | Commits panel: history list (terminus, merge spur, metadata, popover) + commit-scoped diffs in its own viewer. Migrates `test_history_panel.py`, `test_history_panel_diffs.py`. |
| `test_diff_viewer.py` (shared) | FCC-02, FCC-06, FCC-07 | controlled | The embedded viewer behavior every panel shares, tested once: file/diff tabs, split/unified + wrap + render toggles (now under the triple-dot menu), find-in-file, line numbers/expansion, moved-file (R) rendering, loading bar only when a file is open, GFM + sanitization, open-from-chat. Migrates `test_diff_refresh_on_branch_change.py`, `test_diff_tab_close_others.py`, `test_diff_loading_bar_no_file.py`, `test_markdown_render_toggle.py`, `test_markdown_gfm.py`, `test_open_in_viewer.py`. |
| `test_review_all_panel.py` | REVIEW-01, REVIEW-02 | controlled | Review-all as a no-default-section single-instance panel; functionality preserved. Absorbs `test_review_all_visibility.py` + `test_workspace_scoped_changes.py` + `test_auto_collapse_combined_diff.py`. |
| `test_new_workspace_dialog.py` | WSC-01..05, 07, 11 | default | Four creation entry points; dialog form (title/prompt/breadcrumb pills/footer); agent-type picker; project/repo selector + MRU; `/ws/new` gone. **Rebuilds** the form/keyboard assertions of `test_add_workspace_page.py` + `test_add_workspace_agent_type.py`; **drops** the tab-model stories (new-workspace tab, tab transition, `/ws/new` draft). Test case: Cmd+Enter inside the repo-path autocomplete must not also create the workspace. |
| `test_new_workspace_creation_modes.py` | WSC-06, 08, 09, 10 | controlled (one `write_file`) | Branch-name pill (sanitize/shuffle/error slot) + collision; mode selector (worktree/clone/in-place); source-branch selection; cleared-vs-kept branch semantics. **Migrates** `test_branch_name_collisions.py`, `test_clone_mode_branch_name.py`, `test_worktree_create_happy_path.py`, `test_worktree_edge_cases.py`, and the source-branch halves of `test_branch_switching_integration.py` / `test_clone_local_only_branch.py` (git-state checks carry over unchanged). |
| `test_empty_first_run.py` | FIRST-01..05 | default | No-workspaces special page + inline form; sidebar repo area states; disabled nav/Cmd+K; `/sculptor:help` prefill; post-create navigation. |
| `test_layout_persistence.py` | PERSIST-01, PERSIST-03, PERSIST-05 | default | Per-workspace independence of visibility/open/active; restart persistence; cross-workspace isolation. Uses the `sculptor_instance_factory_` (restart) fixture. |
| `test_layout_persistence_regression.py` | PERSIST-04 | controlled | **Regression.** Expand right section + add terminal panel → navigate Home → back; agent panel survives. |
| `test_seamless_switch.py` | SWITCH-03, SWITCH-04 | controlled | The e2e-observable parts of switching: no spinner (skeleton/stale-then-update), last-view preserved. The `[perf]` bars (SWITCH-01/02/05) are verified via tooling, not here. |

**Files / Changes / Commits — separate files + shared helpers.** The three panels
embed the *same* master-detail shape (a list sidebar + a diff/file viewer), so the
four files above must **not** duplicate selectors. They share, from
`sculptor/sculptor/testing/elements/` (see `harness_migration.md` §1):
- a **`DiffViewer`** POM (refactor of today's `diff_panel.py`, now embeddable per
  panel) — tabs, scopes, line numbers, and the toggles relocated into the
  triple-dot menu;
- a **`MasterDetailPanel`** POM — resizable list, shared-width sidebar, sidebar
  toggle, empty state;
- helper functions for the common flows (`open_file_in_panel`,
  `toggle_view_option_via_menu`, `assert_diff_shows`).

`test_diff_viewer.py` exercises the shared viewer once (via whichever panel is
convenient); the three panel files assert only their panel-specific sidebar/list
behavior. **The content assertions are migrated, not rewritten** — the proven
checks from today's `test_file_browser*` / `test_history_panel*` / `test_diff_*` /
`test_markdown_*` move across unchanged, and the source files are removed once
migrated (consolidation, not in-place editing).

> **Perf coverage (not e2e):** SWITCH-01, SWITCH-02, SWITCH-05, SEC-18 (zero-reflow
> aspect), PERSIST-02 → `measure-react-renders` skill + the workspace-switch profiler
> (`common/perf/workspaceSwitchProfiler.ts`, carried forward from the SCU-1474
> prototype). Tracked in `harness_migration.md` §Perf tooling.

---

## 2. DELETE — removed features

| File | Why |
|---|---|
| `test_zen_mode.py` | Zen mode + Focus mode are deprecated. |
| `test_btw.py` | The `/btw` popup is removed. |
| `test_panels_settings.py` | The Panels settings page is removed, along with the panel enable/disable machinery. This cascade pushes `test_browser_panel.py` to REWRITE (§3); `test_notes_panel.py` gets only minimal handling (Notes slated for deprecation). |
| `test_panel_zones.py` | The docking/zone model (top-right / bottom-right zones, auto-hide, zone persistence) is replaced by the section model — superseded by the new `test_section_*` files, not migrated 1:1. |
| `test_side_toggle.py` | The bottom-bar side-toggle buttons are gone; the equivalent behavior (collapse/expand left/right/bottom) is covered by `test_section_collapse_expand.py`. |
| `test_expand_escape.py` | The per-diff "expand"/fullscreen toggle is **deprecated**, not re-homed. There is no diff-specific fullscreen anymore; a user maximizes the section instead, covered generically by `test_section_active_and_maximize.py` (SEC-13/15). `naming_map.md` deletes `expandedPanelIdAtom`. |

Notes:
- `test_alpha_chat_tool_density.py` imports the `zen_mode` POM only incidentally
  (to maximize chat space). It is **UPDATE**, not delete — swap to the
  section-collapse helper.
- No dedicated "share panel sizes" test exists in the suite (verified), so the
  removal of that experimental setting deletes no test; scrub any stray
  share-sizes assertion if one surfaces during the rewrite.

---

## 3. REWRITE — surface replaced (also RENAMEd)

The behavior survives but its surface (top-bar tabs / `/ws/new` page / workspace
tabs) is replaced by the sidebar + dialog model.

| File → new name | Stories | What changes |
|---|---|---|
| `test_add_workspace_page.py` → `test_new_workspace_dialog.py` | WSC-01..07, FIRST-04 | Page → modal. Form-persistence, Cmd+Enter create, Cmd+I focus survive as dialog tests. The "new-workspace **tab** / tab transition / `/ws/new` draft" stories die with the tab model (some move to PERSIST/SWITCH re-entry). |
| `test_add_workspace_agent_type.py` → folded into `test_new_workspace_dialog.py` | WSC-05 | First-agent type picker now lives in the dialog. The bare "Terminal" agent type is **dropped** (raw shell = "New terminal" panel; terminal agents = registered programs), so the picker asserts Claude / pi (gated) / registered only. |
| `test_home_page_tab.py` → covered by `test_workspace_sidebar.py` | SIDE-01 | Home is a sidebar link, not a tab. The "Home tab replace / close" stories are removed. |
| `test_settings_tab.py` → `test_settings_navigation.py` | SIDE-10 | Settings is a sidebar destination. "Only one Settings tab / close tab" stories tied to the tab bar are removed; "open Settings, return to workspace" survives as route nav. |
| `test_component_gallery_tab.py` → **DELETE** | — | The Component Gallery is a dev-only surface slated for removal; drop its tab test and the gallery assertion in `test_theme_builder.py`. The **TanStack devtools panel stays** — `test_tanstack_devtools_panel.py` is **KEPT** (UPDATE only if its nav reach changes). |
| `test_workspace_tab_enhancements.py` → split into sidebar + dialog tests | SIDE-07..09, WSC-02 | "Open Add Workspace page via keyboard" → open dialog; workspace-tab close/keyboard → sidebar-row semantics. |
| `test_workspace_tab_context_menu_icons.py` → `test_workspace_row_context_menu.py` | SIDE-08 | Workspace **tab** context menu → workspace **row** context menu (rename, etc.). |
| `test_workspace_diagnostics_context_menu.py` → REWRITE | SIDE-08 | Same menu, now anchored on the sidebar row. |
| `test_workspace_peek.py` → REWRITE | SIDE-07, SIDE-09 | Hover **tab** → hover sidebar **row**; peek popover behavior preserved. |
| `test_closed_workspaces_dropdown.py` → **DELETE** | — | The open/closed-workspace distinction is removed (see `user_stories.md` Removed behaviors + `goals.md`); all workspaces just appear in the sidebar. The reopen paths in `test_workspace_close_vs_delete.py` are dropped too. |
| `test_workspace_close_vs_delete.py` → REWRITE | AGENT-04, SIDE-09 | Close-vs-delete semantics move from tabs to sidebar rows / panel close; keyboard shortcuts re-mapped. |
| `test_notes_panel.py` → **minimal** | PANEL-01/05/07 | Notes and Actions are slated for deprecation (superseded by plugin support). No special work beyond making the panel appear as a registered panel; the "enable from Panels settings" story dies with the Panels page. `test_custom_actions.py` likewise gets only the harness shim. |
| `test_browser_panel.py` → REWRITE | PANEL-01/05/07, REVIEW-01-style "no default section" | The opt-in/opt-out stories ("keep hidden until I opt in", "opt into the Browser panel and back out") reflect the removed enable model; Browser is a registered panel with no default section. Rewrite those as add/close-panel. The isolation/in-page-state-persistence stories survive (UPDATE). |
| `test_diff_scope_and_fullscreen.py` → split: DELETE half + UPDATE half | (scope assertion unchanged) | The "expand toggle for distraction-free review" half is **deleted** (fullscreen-expand deprecated — see §2). The "scope picker defaults to All from the Changes panel" half is an unchanged UPDATE (scope picker stays on the Changes panel). Rename the file to drop "fullscreen". |

---

## 4. UPDATE — harness-path only (behavior unchanged)

These tests assert behavior that the redesign does not change; they break only
because the **route to the surface** changes. The fix is mechanical and shared —
swap the old POM method for the new one (defined in `harness_migration.md`). No
assertion logic changes. Most will also be RENAMEd (§5) if they carry old vocab.

**4a. Agent creation/switching via the tab bar → section panel-tabs + `+` dropdown**
(`agent_tab` POM importers, minus those already in DELETE/REWRITE):
`test_agent_diagnostics_context_menu.py`, `test_agent_tab_context_menu.py`,
`test_ci_babysitter.py`, `test_registered_terminal_agent.py`,
`test_terminal_agent_automated_prompts.py`, `test_terminal_agent_basic.py`,
`test_terminal_agent_external_rename.py`, `test_terminal_agent_signals.py`,
`test_optimistic_deletion.py`.

**4b. Workspace creation via the new-workspace surface**
(`add_workspace_page` importers that only create a workspace to reach a feature —
swap to a shared `create_workspace()` helper over the dialog):
`test_branch_name_collisions.py`, `test_branch_switching_integration.py`,
`test_clone_local_only_branch.py`, `test_clone_mode_branch_name.py`,
`test_migration.py`, `test_multi_repo.py`, `test_onboarding.py`,
`test_restart_mru.py`, `test_restarts.py`, `test_target_branch_local_only.py`,
`test_task_page_chatting.py`, `test_telemetry_opt_out.py`,
`test_turn_summary_worktree.py`, `test_worktree_as_user_repo.py`,
`test_worktree_create_happy_path.py`, `test_worktree_deletion_policies.py`,
`test_worktree_edge_cases.py`.

**4c. Navigation via the old top bar / tabs → sidebar destinations**
(uses `project_layout` top-bar/tab methods; the new `project_layout` API covers
them — the long tail here changes only via the POM): e.g.
`test_agent_settings.py`, `test_alpha_chat_intro.py`,
`test_alpha_scroll_task_switch.py`, `test_command_palette.py` (topbar Cmd+K
button → sidebar), `test_entity_mention_persistence.py`, `test_keybindings.py`,
`test_mark_unread.py`, `test_multi_agent_workspace.py`, `test_optimistic_close.py`,
`test_queued_messages.py`, `test_read_unread_status.py`, `test_status_pill.py`,
`test_theme_builder.py`, `test_workspace_deletion_cleanup.py`, plus the rest of
the 44-file `project_layout`-method set.

**4d. Panel-visibility helpers → section collapse/expand helpers**
(`panels.py` helper importers): `test_alpha_scroll_behaviors.py`,
`test_alpha_scroll_padding_agent_switch.py`, `test_alpha_scroll_to_top.py`,
`test_linear_plugin_runtime.py` (also uses `panel_zones` — re-point its plugin
panel to a section). These call `close_bottom_panel` / `ensure_*_visible`; repoint
to the new section helpers.

**4e. Files/Changes/History as tabs → separate Files/Changes/Commits panels
(migrate-and-consolidate, not in-place UPDATE).** Today's single file-browser
panel (All/Changes/History tabs + a shared diff panel) becomes three panels, each
with its own embedded viewer. The diff/content assertions in these files are
**unchanged**, but rather than editing each file in place we **migrate** their
assertions into the four §1 files (`test_files_panel.py`, `test_changes_panel.py`,
`test_commits_panel.py`, `test_diff_viewer.py`) via the shared `DiffViewer` /
`MasterDetailPanel` POMs, then remove the source files. The migration sources:
`test_file_browser.py`, `test_file_browser_tabs.py`,
`test_file_browser_uncommitted.py`, `test_file_browser_symlink_replaces_directory.py`,
`test_file_open_diff_modes.py`, `test_history_panel.py`, `test_history_panel_diffs.py`,
`test_diff_scope_switching.py`, `test_diff_refresh_on_branch_change.py`,
`test_diff_tab_close_others.py`, `test_diff_loading_bar_no_file.py`,
`test_commit_from_changes_tab.py`, `test_discard_file.py`,
`test_discard_preserves_all_tab.py`, `test_target_branch.py`,
`test_markdown_render_toggle.py`, `test_markdown_gfm.py`, `test_open_in_viewer.py`.
(The relocated config icons → triple-dot menu shift selectors under the menu —
FCC-07. The per-diff fullscreen-expand is deprecated: `test_expand_escape.py` is
DELETEd (§2) and the fullscreen half of `test_diff_scope_and_fullscreen.py` is
dropped — users maximize the section instead, covered generically by SEC-13/15.)

Also in this group, the registered side panels move from zone sidebar-icons to
section panels: `test_skills_panel.py` keeps its content and just gets the harness
shim (UPDATE). `test_browser_panel.py` goes to §3 REWRITE (its enable/opt-in stories
are removed). `test_custom_actions.py` and `test_notes_panel.py` get **minimal**
handling only — Actions and Notes are slated for deprecation (superseded by plugin
support); they just need to appear as registered panels.

---

## 5. RENAME-only (behavior + assertions unchanged)

Per the project decision, tests carrying old vocabulary are renamed to the new
terms even when nothing else changes. The full rename map (file/test-fn/
`@user_story`/POM-method) lives in `harness_migration.md` §Terminology rename.
The ~40 files whose filename or `@user_story` text currently carry old vocab
(`zen`, `focus`, `btw`, `panel_zone`, `side_toggle`, `add_workspace`, `topbar`,
`tab` meaning agent/file tab, `docking`) were enumerated by grep and are the
starting RENAME worklist; the subset already handled by §2–§4 inherit their
rename there, and the remainder are RENAME-only.

Rename rules: `zone`/`docking` → `section`; `zen`/`focus` → (removed);
`(agent|file) tab` → `panel` / `panel tab`; `side_toggle` → `section collapse`;
`add_workspace_page` → `new_workspace_dialog`; `top bar` → `sidebar` / `workspace
header`.

---

## 6. KEEP behavior (no test-logic change)

The large remainder (~120 files) assert only on content **inside** a panel and
are unaffected by where the panel lives — chat/alpha rendering, tool pills,
scroll-internals, ask-user-question, markdown, images, `pi_*`, terminal I/O,
PR buttons, settings sub-pages, onboarding, CLI, queued messages, status pill,
keybindings internals, real-agent suites. Rule: **a test is KEEP if it never
reaches a renamed POM method and asserts no removed/changed surface.** It changes
only if (a) the harness shim renames a method it transitively calls — then it is a
trivial UPDATE — or (b) it carries old vocab — then it is RENAME-only (§5).

Representative KEEP examples (not exhaustive): `test_alpha_chat_*` (≈20),
`test_alpha_scroll_*` (the non-panel ones), `test_alpha_tool_pill_*`,
`test_ask_user_question*`, `test_at_mention_*`, `test_image_*`, `test_pi_*`,
`test_markdown_gfm.py`, `test_pr_*`, `test_settings_*` (non-Panels),
`test_onboarding.py` (creation aside), `test_sculpt_cli.py`, `test_keybindings.py`
(recording internals). These get no row above; they ride the harness shim.

The shell-agnostic-content rule that makes this bucket valid is an explicit
architecture constraint (`component_hierarchy.md`/`state_design.md` → "Mobile":
content components never read layout state), so a panel moving sections does not
touch its content assertions. Note the registered side panels are **not** pure
KEEP: `test_skills_panel.py` is UPDATE (panel placement, §4e), `test_browser_panel.py`
is REWRITE (enable/opt-in removed, §3), and `test_custom_actions.py` /
`test_notes_panel.py` get minimal handling (Actions/Notes slated for deprecation).

---

## 7. Coverage map (story → test)

`[perf]`/`[unit]` rows are tooling, not `test_*.py`.

| Story | Covered by |
|---|---|
| SIDE-01..12, 16, 17 | `test_workspace_sidebar.py` + `test_workspace_row_context_menu.py` + `test_workspace_row_hover_actions.py` + `test_settings_navigation.py` + `test_workspace_optimistic_deletion.py` |
| SIDE-13..15 | `test_sidebar_collapse_resize.py` |
| SEC-01..04 | `test_section_default_layout.py` |
| SEC-05..08, SEC-20 | `test_section_collapse_expand.py` |
| SEC-09..16, SEC-21 | `test_section_active_and_maximize.py` |
| SEC-17, SEC-22 | `test_section_resize.py` |
| SEC-18 | `[perf]` profiler + `test_section_resize.py` (restored-size aspect) |
| SEC-19 | `test_section_empty_state.py` |
| SPLIT-01..06 | `test_section_splits.py` (SPLIT-04/05 also `test_section_empty_state.py`) |
| PANEL-01..06, PANEL-12, PANEL-15 | `test_panel_add_dropdown.py` |
| PANEL-07, PANEL-11, PANEL-14 | `test_panel_rename_and_close.py` |
| PANEL-08..10, PANEL-16 | `test_panel_drag_and_drop.py` |
| PANEL-13 | `[unit]` + `test_keybindings.py` (binding visible) |
| AGENT-01..04 | `test_agent_panel.py` |
| AGENT-05 | `test_agent_concurrent_streaming.py` |
| AGENT-06, 07 | `test_panel_tab_context_menu.py` |
| AGENT-08 | `test_panel_optimistic_deletion.py` |
| AGENT-09 | `test_agent_panel.py` (numbering after delete) |
| TERM-01, TERM-02, TERM-03 | `test_terminal_panel.py` |
| TERM-04 | `test_terminal_close_kills_shell.py` (KEEP content, re-reached via panel) |
| TERM-05 | the terminal-agent suite (UPDATE-in-place) |
| FCC-01..07 | `test_files_panel.py`, `test_changes_panel.py`, `test_commits_panel.py`, `test_diff_viewer.py` (shared) — migrate content from `test_file_browser*`, `test_history_panel*`, `test_diff_*`, `test_markdown_*`, `test_open_in_viewer.py` |
| REVIEW-01, REVIEW-02 | `test_review_all_panel.py` |
| WSC-01..05, 07, 11 | `test_new_workspace_dialog.py` |
| WSC-06, 08, 09, 10 | `test_new_workspace_creation_modes.py` |
| FIRST-01..05 | `test_empty_first_run.py` |
| PERSIST-01, 03, 05 | `test_layout_persistence.py` |
| PERSIST-02 | `[perf]` |
| PERSIST-04 | `test_layout_persistence_regression.py` |
| SWITCH-01, 02, 05 | `[perf]` `measure-react-renders` + profiler |
| SWITCH-03, 04 | `test_seamless_switch.py` |

---

## Summary of file deltas

- **CREATE:** ~30 new files (§1) — the four FCC files, the sidebar/row + creation-modes +
  panel-tab files the area audits added, and the section/panel/persistence files.
- **DELETE:** the deprecated-feature files + several sub-tests (§2) — incl.
  `test_expand_escape.py` (fullscreen-expand deprecated), the closed-workspaces and
  Component-Gallery tests, and the tab-strip/old-chrome sub-tests. (The **TanStack
  devtools panel stays** — `test_tanstack_devtools_panel.py` is KEPT.)
- **REWRITE (+rename):** Browser (enable removed, §3) + the sidebar/row rebuilds.
- **UPDATE (harness-path, in place):** the route-to-feature long tail (§4) + the
  Skills panel + the CONTENT-preserving terminal-agent files.
- **MINIMAL:** Actions and Notes (slated for deprecation) — just appear as panels.
- **MIGRATE-and-consolidate:** the FCC file-browser/diff/history set (§4e) **plus**
  the workspace-tab files → sidebar/row files and the agent/terminal-tab files →
  panel-tab files; assertions preserved, source files removed.
- **RENAME-only:** the old-vocab remainder not already covered above (§5).
- **KEEP:** the content-only majority rides the harness shim (§6).
- Full per-file dispositions per area: `supplemental/test_area_audits/`.
- **Perf/unit (no `test_*.py`):** SWITCH-01/02/05, SEC-18, PERSIST-02.
