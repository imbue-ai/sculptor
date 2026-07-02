# Workspace creation (`/ws/new` page → modal + empty first-run)

> Produced by a parallel deep-audit of the live test suite (the same exercise run for Files/Changes/Commits). The structural outcomes are folded into the core docs (`user_stories.md`, `e2e_test_plan.md`, `harness_migration.md`); this file keeps the granular per-file dispositions. Grounded in the live suite, not the prototype notes. Canonical decisions are in `user_stories.md` / `goals.md`; some inline "open question" notes below predate them (no bare "Terminal" type; branch-collision is a modal-only concern).

## 1. COVERAGE AUDIT

| Existing file | Functionality tested | Redesign surface |
|---|---|---|
| `test_add_workspace_page.py` | Form name-draft persistence across nav; branch/source-branch draft persistence; **multiple new-workspace tabs w/ independent drafts**; **no-extra-tab-flash on create**; create-without-prompt (waiting agent); chat-input focus after create; Cmd+I focuses name input; ArrowUp/Down focus recovery; Cmd+Enter creates; Cmd+Enter in repo autocomplete does NOT create; delete-project-deletes-workspaces | Modal (`new_workspace_dialog`). Form/keyboard assertions migrate; **tab-model stories die**. |
| `test_add_workspace_agent_type.py` | First-agent type picker defaults to Claude; pi gated by flag; Terminal first-agent; **MRU last-used agent type shared across surfaces** | Agent-type picker inside the dialog (WSC-05); MRU feeds WSC-01 direct-create. |
| `test_branch_name_collisions.py` | Branch-name collision inline error + 409 block, worktree + clone modes; no stale worktree metadata on failed submit | Dialog branch-name field (WSC-06) collision behavior. |
| `test_clone_mode_branch_name.py` | Clone-mode optional branch field: cleared→base branch, kept→new branch | Dialog branch-name field + clone mode. |
| `test_worktree_create_happy_path.py` | Worktree create: default auto-fill / custom / random-slug branch name | Dialog branch-name field + worktree (default) mode. |
| `test_worktree_edge_cases.py` | CLONE option hidden unless flag on; setup-command runs; missing-local-repo error | Dialog mode selector + branch field. |
| `test_worktree_deletion_policies.py` | Create worktree (helper), then deletion-policy branch cleanup (`never`/`delete_if_safe`/`always`) | Create via dialog; **deletion-policy assertions belong to sidebar/settings (Sidebar or Settings), not creation.** |
| `test_branch_switching_integration.py` | Create from non-default source branch via `select_branch`; in-place mode badge | Dialog source-branch + mode; mode-badge is workspace-header (Sidebar or Agent/terminal). |
| `test_clone_local_only_branch.py` | Clone from a local-only branch with source remotes present | Dialog source-branch + clone mode. |
| `test_target_branch_local_only.py` | Worktree on local-only repo → "All" scope + uncommitted changes | **Changes panel (FCC)** — only incidentally creates. |
| `test_turn_summary_worktree.py` | Bash-created file in turn footer (worktree) | Chat/turn-footer (KEEP) — only incidentally creates. |
| `test_multi_repo.py` | Create project from form; git-init dialog; project switching; cross-project messaging; **MRU project pre-selected**; duplicate names; empty-repo commit; duplicate-repo error | Project selector inside dialog (WSC-04 pre-select); MRU-project feeds WSC-01. |
| `test_worktree_as_user_repo.py` | Register worktree as repo, clone workspace from it (`select_project_by_name`) | Dialog project selector. |
| `test_migration.py` | Bootstrap when `.format_version` missing → add-workspace page reachable | Post-bootstrap lands on first-run/dialog. |
| `test_restarts.py` | new-workspace **tab** reused (not duplicated) on restart | **Tab-model story — dies.** |
| `test_restart_mru.py` | Restart restores active ws+agent / **`/ws/new` draft** / lands on `/ws/new` when ws deleted / no-MRU → `/ws/new` / legacy `sculptor-tab-order`→`sculptor-tabs` migration | **Tab/MRU/`/ws/new` model — mostly dies**; surviving analog = WSC-01 + FIRST-01. |
| `test_task_page_chatting.py` | Prompt-draft persistence; multi-turn chat; model selection | Chat (KEEP) — incidentally creates. |
| `test_telemetry_opt_out.py` | Telemetry settings + onboarding opt-out; lands on add-workspace page post-signup | Settings + first-run landing assertion. |
| `test_onboarding.py` | Onboarding wizard; post-onboarding lands on add-workspace page | Onboarding (KEEP); landing → empty-first-run (FIRST-01/05). |

## 2. CREATE FILES

| New file | Stories | FakeClaude | Notes |
|---|---|---|---|
| `test_new_workspace_dialog.py` | WSC-01, 02, 03, 04, 05, 07 | default | Modal shell + four entry points (sidebar button=direct create reusing last settings; Cmd/Meta+T=dialog; Cmd+K=dialog; repo-section `+`=dialog pre-selecting repo). Form (WSC-05): title, auto-grow prompt textarea, breadcrumb pills (repo/agent-type/mode/branch), footer (keep-open switch, Cmd+Enter hint, Create). **Rebuilds** form-persistence/Cmd+Enter/Cmd+I/arrow-key/create-without-prompt/focus from `test_add_workspace_page.py`. Agent-type picker (absorbs `test_add_workspace_agent_type.py`): Claude default, pi gated, Terminal option, MRU. |
| `test_new_workspace_creation_modes.py` | WSC-06 + creation-mode/branch (WSC-01 source-branch/init-strategy) | controlled (`write_file` for the local-only assertion only) | Branch-name pill (WSC-06: monospace, sanitization, shuffle, stable error slot) + collision; mode selector (worktree default / clone opt-in / in-place opt-in); source-branch selector; cleared-vs-kept branch semantics; no-stale-worktree-metadata on failed submit. **Migrates real test bodies** from `test_branch_name_collisions`, `test_clone_mode_branch_name`, `test_worktree_create_happy_path`, `test_worktree_edge_cases` (mode/branch halves), and the source-branch half of `test_branch_switching_integration` / `test_clone_local_only_branch`. Filesystem/worktree git checks carry over unchanged. |
| `test_empty_first_run.py` | FIRST-01..05 | default | No-workspaces special page rendering the inline form (FIRST-01); sidebar repo-area states — "Add a repo" / "No workspaces yet" (FIRST-02); disabled nav + Cmd+K + global shortcuts (FIRST-03); `/sculptor:help` prefill (FIRST-04); post-create → full workspace page + navigation (FIRST-05). Replaces the no-MRU/no-ws "lands on `/ws/new`" assertions from `test_restart_mru.py` + the post-onboarding landing assertion. Uses `sculptor_instance_factory_`. |

## 3. SHARED HELPERS / POMs

- **`elements/new_workspace_dialog.py`** (`PlaywrightNewWorkspaceDialog`) — replaces `pages/add_workspace_page.py`. Owns the modal form getters ported verbatim: `get_task_input`, `get_workspace_name_input`, `get_branch_name_input`, `get_branch_name_collision_error`, `get_branch_selector`/`select_branch`, `get_mode_selector`/`select_mode`/`get_mode_option_{worktree,in_place,clone}`, `get_project_selector`/`get_project_options`/`select_project_by_name`, `get_open_new_repo_button`/`open_add_repo_dialog`, `get_submit_button`, `submit_and_wait_for_chat_panel`. **Add** WSC-05/06 getters: `get_prompt_textarea`, `get_context_pills`, `get_keep_open_switch`, `get_branch_shuffle_button`, `get_create_button`. **Add** openers: `open_via_sidebar_button`, `open_via_shortcut`, `open_via_command_palette`, `open_via_repo_plus(repo)`.
- **`elements/empty_first_run.py`** (`PlaywrightEmptyFirstRun`) — the no-workspaces inline form + sidebar repo-area state getters (`get_add_repo_button`, `get_no_workspaces_hint`).
- **THE load-bearing `create_workspace(...)` helper** — refactor of `playwright_utils.start_task_and_wait_for_ready` (today **177 importers**; ~7 in-scope incidental files call it directly). **Keep the exact signature** (`prompt`, `model_name`, `workspace_name`, `mode`, `agent_type`, `wait_for_agent_to_finish`) so the ~17 incidental creators swap **zero** call sites — only the internals change: replace `navigate_to_add_workspace_page` + `START_TASK_BUTTON` with "open dialog → fill → Create". Two call patterns:
  - **call-the-helper** (task_page_chatting, telemetry_opt_out, migration, restarts, restart_mru, onboarding, worktree_as_user_repo, multi_repo partial): inherit new internals for free.
  - **drive-the-POM-directly** (branch_name_collisions, clone_mode_branch_name, worktree_create_happy_path/edge_cases/deletion_policies, branch_switching, clone_local_only, target_branch_local_only, turn_summary_worktree, multi_repo): swap `PlaywrightAddWorkspacePage(page)` → `PlaywrightNewWorkspaceDialog(page)` + an `open_dialog()` call; getter names preserved.
- **`navigate_to_add_workspace_page(page)`** (`playwright_utils.py`, 19 importers) → rename/rewrite to `open_new_workspace_dialog(page)`; drops the `ADD_WORKSPACE_TAB`/`ADD_WORKSPACE_BUTTON` tab logic for the sidebar new-workspace button.
- Per-file git helpers in `test_worktree_create_happy_path.py` (`_worktree_paths`, `_git_branch`, `_git_remotes`, `_wait_for_branch_preview`) and `test_clone_mode_branch_name.py` move with the migrated bodies unchanged.

## 4. PER-FILE DISPOSITION

| File | Disposition | Reason |
|---|---|---|
| `test_add_workspace_page.py` | **REWRITE → `test_new_workspace_dialog.py`** | Page→modal. Form-persistence, create-without-prompt, Cmd+I, Cmd+Enter, arrow-key focus, autocomplete-Cmd+Enter-guard **migrate**. **DELETE tab-model stories**: `test_multiple_new_workspace_tabs_with_independent_drafts`, `test_no_extra_tab_flash_when_creating_workspace_from_new_tab`, and the navigate-via-tabs round-trip in the draft-persistence tests. `test_deleting_project_also_deletes_its_workspaces` → repo-settings (Sidebar or Settings). |
| `test_add_workspace_agent_type.py` | **MIGRATE → `test_new_workspace_dialog.py`** (WSC-05) | Agent-type picker now in the dialog; Claude-default/pi-gated/Terminal/MRU preserved. Resolve "Terminal" agent-type vs "New terminal" panel question. |
| `test_branch_name_collisions.py` | **MIGRATE → `test_new_workspace_creation_modes.py`** (WSC-06) | Collision behavior preserved against the dialog pill. |
| `test_clone_mode_branch_name.py` | **MIGRATE → `test_new_workspace_creation_modes.py`** | Clone optional-branch semantics preserved. |
| `test_worktree_create_happy_path.py` | **MIGRATE → `test_new_workspace_creation_modes.py`** | Worktree default/custom/random-slug preserved. |
| `test_worktree_edge_cases.py` | **MIGRATE → `test_new_workspace_creation_modes.py`** | Mode-visibility + branch-field/error halves preserved. |
| `test_branch_switching_integration.py` | **SPLIT: MIGRATE source-branch half; UPDATE mode-badge half** | `select_branch` is a dialog assertion; `get_mode_badge` is workspace-header (Sidebar or Agent/terminal). |
| `test_clone_local_only_branch.py` | **MIGRATE → `test_new_workspace_creation_modes.py`** | Source-branch + clone-mode preserved. |
| `test_worktree_deletion_policies.py` | **UPDATE (creation call only)** | Deletion-policy assertions are sidebar/settings, not creation. |
| `test_target_branch_local_only.py` | **UPDATE (creation call only)** | Real subject is the Changes panel (FCC). |
| `test_turn_summary_worktree.py` | **UPDATE (creation call only)** | Turn-footer (KEEP). |
| `test_multi_repo.py` | **SPLIT: MIGRATE project-selector/MRU/git-init bits; KEEP cross-project messaging** | Project selector + MRU + git-init are dialog assertions (WSC-04); messaging tests UPDATE creation path only. |
| `test_worktree_as_user_repo.py` | **UPDATE (creation call only)** | `select_project_by_name` via dialog; unchanged. |
| `test_migration.py` | **UPDATE (landing assertion)** | Post-bootstrap landing → first-run/dialog. |
| `test_restarts.py` | **DELETE `test_restart_reuses_existing_new_workspace_tab`; KEEP rest** | Pseudo-tab dedup dies with the tab model. |
| `test_restart_mru.py` | **REWRITE → folds into `test_empty_first_run.py` + PERSIST/SWITCH** | `sculptor-tabs`/`/ws/new`-draft/tab-order-migration die. Survivors: "no MRU → first-run" (FIRST-01), "deleted-ws → first-run", "restore last ws+agent" → PERSIST/SWITCH (Sidebar). |
| `test_task_page_chatting.py` | **UPDATE (creation call only)** | Chat content (KEEP). |
| `test_telemetry_opt_out.py` | **UPDATE (landing assertion only)** | Settings; post-signup landing → first-run. |
| `test_onboarding.py` | **UPDATE (landing assertion only)** | Onboarding (KEEP); landing → empty-first-run (FIRST-01/05). |
| `pages/add_workspace_page.py` (POM) | **DELETE → `elements/new_workspace_dialog.py`** | `/ws/new` route removed; form getters move. |
| `start_task_and_wait_for_ready` | **REWRITE internals, keep signature → `create_workspace()`** | 177 importers unaffected if signature held. |
| `navigate_to_add_workspace_page` | **REWRITE → `open_new_workspace_dialog`** | Tab/`+`-button logic → sidebar new-workspace button. |

## 5. HARNESS CHANGES

**POMs:** DELETE `pages/add_workspace_page.py`; NEW `elements/new_workspace_dialog.py` + `elements/empty_first_run.py`. Rewrite the two `playwright_utils.py` helpers. NOTE `PlaywrightAddWorkspacePage` subclasses `PlaywrightProjectLayoutPage` — the dialog POM should compose the new sidebar/section base instead (cross-area dependency on Sidebar's `project_layout` rewrite).

**ElementIDs (run `just generate-api` after):**
- **Remove:** `ADD_WORKSPACE_TAB`, `ADD_WORKSPACE_BUTTON`, `ADD_WORKSPACE_EMPTY_STATE`.
- **Reuse inside the dialog:** `TASK_INPUT`, `WORKSPACE_NAME_INPUT`, `START_TASK_BUTTON` (or rename to `NEW_WORKSPACE_CREATE_BUTTON`), `BRANCH_NAME_INPUT`, `BRANCH_NAME_COLLISION_ERROR`, `BRANCH_SELECTOR`, `BRANCH_OPTION`, `MODE_SELECTOR`, `MODE_OPTION_{WORKTREE,CLONE,IN_PLACE,EXISTING}`, `PROJECT_SELECTOR`, `PROJECT_SELECT_ITEM`, `OPEN_NEW_REPO_BUTTON`, `ADD_WORKSPACE_AGENT_TYPE_SELECT`, `AGENT_TYPE_OPTION_{CLAUDE,PI,TERMINAL,REGISTERED}`.
- **Add:** `NEW_WORKSPACE_DIALOG`, `NEW_WORKSPACE_FORM`, `NEW_WORKSPACE_PROMPT_TEXTAREA`, `NEW_WORKSPACE_CONTEXT_PILL`, `NEW_WORKSPACE_KEEP_OPEN_SWITCH`, `BRANCH_NAME_SHUFFLE_BUTTON`, `EMPTY_FIRST_RUN_PAGE`, `SIDEBAR_ADD_REPO_BUTTON`, `SIDEBAR_NO_WORKSPACES_HINT`, `SIDEBAR_NEW_WORKSPACE_BUTTON`, `SIDEBAR_REPO_ADD_WORKSPACE` (last two shared with Sidebar & navigation). WSC-06 shuffle + WSC-05 pills/keep-open/textarea are net-new with no current testid.

**Fixtures / FakeClaude:** No new FakeClaude commands. Dialog/mode tests use default response; only one local-only assertion needs `write_file`. `test_empty_first_run.py` needs a **fresh zero-workspace instance** — confirm `resources.py` setup doesn't auto-create a first workspace; add a zero-workspace variant if it does. The `enable_clone_workspaces` / `enable_in_place_workspaces` flag paths survive.

## 6. USER STORIES

**Covered:** WSC-01..07 → `test_new_workspace_dialog.py` + `test_new_workspace_creation_modes.py`; FIRST-01..05 → `test_empty_first_run.py`.

**PROPOSED new IDs (uncaptured behavior with live tests):**
- **WSC-08** Branch-name **collision** blocked at create with inline error (worktree + clone), no stale worktree metadata. *(`test_branch_name_collisions.py`.)*
- **WSC-09** Creation **mode/init-strategy** selection: worktree default, clone/in-place opt-in (flag-gated), mode-appropriate branch semantics. *(`test_clone_mode_branch_name`/`test_worktree_edge_cases`.)*
- **WSC-10** Creating from a **non-default source branch** via the branch selector. *(`test_branch_switching_integration`/`test_clone_local_only_branch`.)*
- **WSC-11** Dialog **project/repo selector** can register a new repo (git-init/add-repo) and remembers the **MRU project**. *(`test_multi_repo.py`.)*
- **FIRST-06** Negative-path **autocomplete-Cmd+Enter guard**: Cmd+Enter inside repo-path autocomplete must not also create the workspace. *(`test_add_workspace_page::test_cmd_enter_in_repo_autocomplete_does_not_create_workspace`.)*

## 7. OPEN QUESTIONS / CROSS-AREA OVERLAP

- **Sidebar & navigation:** WSC-01 depends on Sidebar's sidebar new-workspace button + repo `+` (shared ids/POM). `test_restart_mru.py`'s "restore last ws+agent on restart" survives only as PERSIST/SWITCH (Sidebar). Deletion assertions (`test_deleting_project...`, `test_worktree_deletion_policies`) belong to Sidebar/settings. The dialog POM's base class is being rewritten by B.
- **Agent & terminal panels:** Agent-type picker (WSC-05) shares `AGENT_TYPE_OPTION_*` ids + MRU machinery with Agent & terminal panels's add-panel dropdown. **Open question:** does the picker keep a bare "Terminal" agent-type, or does "New terminal" move to the panel model — decides `AGENT_TYPE_OPTION_TERMINAL` survival.
- **Sections & panel layout / FCC:** `test_target_branch_local_only` and `test_turn_summary_worktree` only incidentally create.
- **Within-area open questions (block test writing):** WSC-05/06 surfaces (auto-grow textarea, context pills, keep-open switch, branch shuffle) are **net-new with no current `data-testid`**; whether Create reuses `START_TASK_BUTTON` or a new id; `/sculptor:help` prefill observability (FIRST-04); the "keep open" multi-create flow behavior (unspecified in `goals.md`).
