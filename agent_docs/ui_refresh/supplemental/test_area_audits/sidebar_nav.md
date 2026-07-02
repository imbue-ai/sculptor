# Workspace sidebar + navigation (top bar + tabs → sidebar)

> Produced by a parallel deep-audit of the live test suite (the FCC-style exercise). Structural outcomes folded into the core docs; this file keeps the granular per-file dispositions. Grounded in the live suite, not the prototype notes. Canonical decisions are in `user_stories.md` / `goals.md`; some inline "open question / blocked" notes below predate them (closed-workspaces and the Component Gallery are now deleted, not re-homed).

Scope: **~32** in-scope sidebar/nav files (of ~46 that call the `project_layout.py` top-bar/tab API; `test_zen_mode.py` and the terminal-tab files belong to other areas). Stories SIDE-01..15.

**Key live-suite facts:**
- Old surface = top bar + tab strip: `ElementIDs.TOP_BAR`, `BOTTOM_BAR`, `HOME_TAB`, `SETTINGS_TAB`, `WORKSPACE_TAB`, `ADD_WORKSPACE_TAB`/`ADD_WORKSPACE_BUTTON`, `COMPONENT_GALLERY_TAB`, `TAB_CLOSE_BUTTON`, `TAB_CONTEXT_MENU_*`.
- **A `WORKSPACE_ROW` surface already exists** — `pages/home_page.py::PlaywrightHomePage.get_workspace_rows()` + `WORKSPACE_ROW`, `WORKSPACE_ROW_BRANCH`, `WORKSPACE_ROW_CONTEXT_MENU_DELETE`, used by `navigate_to_home_page`. The sidebar's rows are the natural successor; the new `WorkspaceSidebar` POM should mirror `PlaywrightHomePage`, not invent a row model.
- `TAB_CONTEXT_MENU_*` ids are **shared** between workspace tabs (`project_layout.py`) and agent tabs (`elements/agent_tab.py`) — splitting them (workspace-row menu vs panel-tab menu) is the core Sidebar ↔ Agent/terminal coordination point.
- Most route-to-feature files use `get_workspace_tabs()` exactly once, as `.click()` / `.to_have_count()` / `.to_have_attribute("data-has-unread")` — all three collapse onto one sidebar-row helper.

## 1. COVERAGE AUDIT

| Existing file | Functionality | Redesign surface |
|---|---|---|
| `test_home_page_tab.py` | Home opens as a tab; clicking a workspace replaces Home tab; closeable | Home = sidebar **top link**. Tab-model stories DIE. |
| `test_settings_tab.py` | Settings as tab; closeable; singleton; context menu no rename/delete | Settings = sidebar **bottom link**. Singleton/close/menu DIE; "open→return" survives. |
| `test_component_gallery_tab.py` | Gallery opens as tab from Theme Builder; closeable; menu | **Unresolved home** (goals.md silent). BLOCKED. |
| `test_workspace_tab_enhancements.py` | Cmd+T opens Add-Workspace page; Cmd+W closes ws tab; context-menu delete; new-ws-tab "X"/Cmd+W → MRU | Cmd+T → dialog (Workspace creation). Tab close/keyboard + "new-ws tab transition" DIE. Context-menu delete → row delete (SIDE-09). |
| `test_workspace_tab_context_menu_icons.py` | Rename ws via tab context menu; Escape cancels | Workspace **row** context menu (SIDE-08). Survives, re-anchored. |
| `test_workspace_diagnostics_context_menu.py` | Copy ws name/branch/id from tab context menu + Diagnostics submenu | Workspace **row** context menu (SIDE-08). Survives. |
| `test_workspace_peek.py` | Peek popover on **tab hover** (idle/waiting/diff-stats/hover/scrolled-tab) | Hover sidebar **row** (SIDE-07/09). Content survives; **scrolled-tab** test DIES (tab-strip overflow gone). |
| `test_workspace_close_vs_delete.py` | Close-vs-delete via tabs + keyboard; close-all/close-others; reopen-from-list/Home; localStorage migration | Rows / panel close; close-all/others-**tabs** DIE; reopen via closed-workspaces (unresolved). Cross-Agent & terminal panels for panel-close=delete (AGENT-04). |
| `test_closed_workspaces_dropdown.py` | Closed-workspaces **pill** count, dropdown rows, reopen/delete/open-all | **Unresolved home** (pill location unspecified). BLOCKED. |
| `test_optimistic_close.py` | Error toast when closing a ws tab fails | Close = row action. Survives, re-anchored. |
| `test_optimistic_deletion.py` (**workspace half**) | Optimistic ws deletion removes tab; rollback toast; active-index clamp/preserve | Row delete + rollback survive. **Agent half is C.** Active-**index** semantics may change (no strip → no index). |
| `test_command_palette.py` (topbar bits) | Open palette via **topbar button**; "open button visible in topbar" lock | Cmd+K = sidebar **top link** (SIDE-02). Topbar-button test re-anchors; rest is KEEP. |
| `test_read_unread_status.py` (**workspace-level**) | `data-has-unread` on ws tab | Attribute → sidebar **row**. Agent-level is C. |
| `test_mark_unread.py` (**workspace-switch**) | Unread persists across ws switches | Switch via sidebar rows; mark-unread itself is agent-tab (Agent/terminal). |
| ~18 route-to-feature files | Use `get_workspace_tabs()`/`get_add_workspace_button()` only to **reach** another feature | Mechanical swap to shared sidebar-nav helpers. No assertion change. |

## 2. CREATE FILES

| New file | Stories | FakeClaude | Notes |
|---|---|---|---|
| `test_workspace_sidebar.py` | SIDE-01, 02, 03, 04, 05, 06, 07, 10, 11, 12 | default | Core nav: home link, Cmd+K link, new-ws button (SIDE-03 ↔ WSC-01), repo groups (collapse/add-ws/repo-settings), row click → navigate, Settings link, report-bug, version. Absorbs `test_home_page_tab`, `test_settings_tab`. Split if it grows. |
| `test_sidebar_collapse_resize.py` | SIDE-13, 14, 15 | default | Collapse to expand-icon only; no collision with OS window controls on home; drag-resize + min-width clamp; toggle hotkey. (Net-new — no live coverage today.) |
| `test_workspace_row_context_menu.py` | SIDE-08 | default | Right-click row → rename / copy name·branch·id / diagnostics / delete. **Rebuilds** `test_workspace_tab_context_menu_icons` + `test_workspace_diagnostics_context_menu`. |
| `test_workspace_row_hover_actions.py` | SIDE-07, 09 | default (peek: `text`/`ask_user_question`) | Hover row → delete + menu icons (SIDE-09); hover → peek popover (SIDE-07). **Rebuilds** `test_workspace_peek` (drops scrolled-tab). |
| `test_settings_navigation.py` | SIDE-10 | default | Settings as a sidebar destination; open → return via route nav. Replaces surviving half of `test_settings_tab`. (May fold into `test_workspace_sidebar.py`.) |

## 3. SHARED HELPERS / POMs

**New POM — `elements/workspace_sidebar.py` (`PlaywrightWorkspaceSidebarElement`):** `get_home_link`, `get_cmdk_link`, `get_new_workspace_button`; `get_repo_groups`, `collapse_repo_group(repo)`, `get_repo_add_workspace(repo)`, `get_repo_settings(repo)`; `get_workspace_rows`, `get_workspace_row_by_name(name)` (successor to `PlaywrightHomePage.get_workspace_rows()` — reuse shape); `get_row_delete_icon(row)`, `get_row_menu_icon(row)`, `open_row_context_menu(row)`; `get_settings_link`, `get_report_bug`, `get_version`; `get_collapse_toggle`, `get_resize_handle`, `get_expand_icon`.

**Shared nav helpers (the must-swap-not-rewrite surface), in `playwright_utils.py`:** `navigate_to_workspace(page, name|index)` (replaces `get_workspace_tabs().nth(i).click()`, ~18 callers); `open_settings(page)`; `open_home(page)` (re-point existing `navigate_to_home_page` from `HOME_BUTTON` to `SIDEBAR_HOME_LINK`); `open_command_palette(page)` (move from topbar button to sidebar link); `new_workspace(page)` (sidebar button; full dialog is Workspace-creation's `create_workspace()`); `open_workspace_row_context_menu(page, name)`.

**Reused as-is:** command palette, warning banner, git-init/add-repo/project-path dialogs, keyboard-shortcuts dialog.

## 4. PER-FILE DISPOSITION

**REWRITE (+rename):**
- `test_home_page_tab.py` → DELETE-by-absorption into `test_workspace_sidebar.py` (SIDE-01); tab-model tests die, "Home navigates" survives.
- `test_settings_tab.py` → `test_settings_navigation.py` (SIDE-10); singleton/close/menu die.
- `test_workspace_tab_context_menu_icons.py` → `test_workspace_row_context_menu.py` (SIDE-08).
- `test_workspace_diagnostics_context_menu.py` → `test_workspace_row_context_menu.py` (SIDE-08).
- `test_workspace_peek.py` → `test_workspace_row_hover_actions.py` (SIDE-07/09); `test_workspace_peek_popover_on_scrolled_tab` **DELETE**.
- `test_workspace_tab_enhancements.py` → **split**: Cmd+T → Workspace creation's dialog (WSC-02); context-menu-delete → SIDE-09; Cmd+W + "new-ws tab X/Cmd+W → MRU" **DIE**.
- `test_workspace_close_vs_delete.py` → REWRITE (split): row close-vs-delete + reopen survive; close-all/others-**tabs** DIE; reopen-from-list/Home BLOCKED. Cross-Agent & terminal panels for panel-close=delete.
- `test_optimistic_close.py` → REWRITE; re-anchor to row; error-toast unchanged.
- `test_closed_workspaces_dropdown.py` → REWRITE — **BLOCKED** (pill home unspecified).
- `test_component_gallery_tab.py` → REWRITE — **BLOCKED** (gallery home unspecified).

**REWRITE-split across areas:**
- `test_optimistic_deletion.py` → **workspace half** here (`*_workspace_deletion_*`, `*_clamps/preserves_active_index`); **agent half** (3 tests) is C. "Active-index clamp" depends on whether rows retain an index.

**UPDATE-in-place (route-to-feature long tail):** `test_agent_settings`, `test_alpha_chat_intro`, `test_alpha_scroll_task_switch`, `test_ask_user_question_invalid_input`, `test_at_mention_completion`, `test_ci_babysitter`, `test_claude_configuration`, `test_entity_mention_persistence`, `test_error_states`, `test_inline_media_display`, `test_keybindings`, `test_multi_agent_workspace`, `test_multi_repo`, `test_pi_session_resume`, `test_picker_dismissal`, `test_plan_mode`, `test_project_env_vars`, `test_queued_messages`, `test_registered_terminal_agent`, `test_restarts`, `test_shared_instance_validation`, `test_skill_autocomplete`, `test_status_pill`, `test_task_page_chatting`, `test_workspace_deletion_cleanup` — swap `get_workspace_tabs()`/`get_add_workspace_button()` → `navigate_to_workspace()`/`new_workspace()`.
- `test_command_palette.py` → UPDATE: re-point topbar Cmd+K button → sidebar link; rest KEEP.
- `test_read_unread_status.py` → UPDATE (workspace-level): `data-has-unread` → `SIDEBAR_WORKSPACE_ROW`; agent-level is C.
- `test_mark_unread.py` → UPDATE (workspace-switch portion); mark-unread mechanics are C.
- `test_browser_panel.py` → UPDATE for its nav only (panel-enable rewrite is FCC §3).
- `test_theme_builder.py` → BLOCKED-on-`get_component_gallery_tab()`.

**DELETE (surface gone):** `test_workspace_peek_popover_on_scrolled_tab`; the tab-model tests inside `test_home_page_tab`, `test_settings_tab`, `test_workspace_tab_enhancements`, `test_workspace_close_vs_delete`.

**RENAME-only:** all surviving in-scope files carrying "tab"/"topbar" vocab.

## 5. HARNESS CHANGES

**`pages/project_layout.py` rewrite:** Remove tab getters (`get_home_tab`/`close_home_tab`, `get_settings_tab`/`open_settings_tab`/`close_settings_tab`, `get_workspace_tabs`, `get_add_workspace_button`/`get_add_workspace_tabs`, `close_workspace_tab*`, `get_bottom_bar`, `get_component_gallery_tab`, `get_top_bar_locator`, all `get_tab_context_menu_*`, `open_workspace_tab_context_menu`, `open_workspace_diagnostics_submenu`, `rename_workspace_tab`, `delete_workspace_via_context_menu`, `get_copy_*`). Add `get_workspace_sidebar()`; keep cross-cutting survivors; move `open_command_palette` onto the sidebar link.

**New POM:** `elements/workspace_sidebar.py`. **Adjust:** `elements/workspace_peek.py` (tab-hover → row-hover; content getters unchanged). **Delete:** `elements/topbar.py` (only method now on sidebar) and `elements/closed_workspaces_dropdown.py` **iff** closed-workspaces dropped (else re-anchor — BLOCKED).

**ElementIDs (run `just generate-api`):**
- **Remove:** `TOP_BAR`, `BOTTOM_BAR`, `HOME_TAB`, `SETTINGS_TAB`, `WORKSPACE_TAB`, `ADD_WORKSPACE_TAB`, `ADD_WORKSPACE_BUTTON`, `ADD_WORKSPACE_EMPTY_STATE`, `COMPONENT_GALLERY_TAB`* (blocked), `TAB_CLOSE_BUTTON`, the `TAB_CONTEXT_MENU_*` set **as workspace ids** (agent-tab subset re-homes to panel-tab — C), `COMMAND_PALETTE_OPEN_BUTTON`.
- **Add (sidebar):** `WORKSPACE_SIDEBAR`, `SIDEBAR_HOME_LINK`, `SIDEBAR_CMDK_LINK`, `SIDEBAR_NEW_WORKSPACE_BUTTON`, `SIDEBAR_REPO_GROUP`, `SIDEBAR_REPO_ADD_WORKSPACE`, `SIDEBAR_REPO_SETTINGS`, `SIDEBAR_WORKSPACE_ROW`, `SIDEBAR_WORKSPACE_ROW_DELETE`, `SIDEBAR_WORKSPACE_ROW_MENU`, `SIDEBAR_SETTINGS_LINK`, `SIDEBAR_REPORT_BUG`, `SIDEBAR_VERSION`, `SIDEBAR_COLLAPSE_TOGGLE`, `SIDEBAR_RESIZE_HANDLE`, `SIDEBAR_EXPAND_ICON`. **Reuse** existing `WORKSPACE_ROW`/`WORKSPACE_ROW_BRANCH`/`WORKSPACE_ROW_CONTEXT_MENU_DELETE`/`VERSION`/`REPORT_PROBLEM_POPOVER` where the sidebar row matches the home-page row.

**Fixtures:** no FakeClaude additions. Re-point `navigate_to_home_page` / `navigate_to_add_workspace_page` to sidebar links. `start_task_and_wait_for_ready` is Workspace-creation's `create_workspace()`.

## 6. USER STORIES

**Covered:** SIDE-01 (home), SIDE-02 (Cmd+K), SIDE-03 (↔WSC-01), SIDE-07/08/09 (peek + row menu + close-vs-delete), SIDE-10 (Settings), SIDE-11 (report-bug), SIDE-12 (version).
**Net-new (no live coverage, covered by new files):** SIDE-04/05/06 (repo grouping/add-ws/repo-settings), SIDE-13/14/15 (collapse/resize/min-width/toggle).
**PROPOSED new IDs:**
- **SIDE-16** Closing/deleting a workspace **optimistically** updates the sidebar and rolls back on failure with an error toast. *(`test_optimistic_close` + `test_optimistic_deletion` ws half.)*
- **SIDE-17** Workspace-level unread indicator on the sidebar row (`data-has-unread`). *(`test_read_unread_status` ws-level.)*
- **SIDE-18 (BLOCKED)** Reopen a closed workspace. *(`test_closed_workspaces_dropdown` / `test_workspace_close_vs_delete`; pending closed-workspaces home.)*

## 7. OPEN QUESTIONS / CROSS-AREA OVERLAP

**Unresolved homes (goals.md silent):** closed-workspaces pill/dropdown (blocks those rewrites + SIDE-18); Component Gallery / dev tabs (blocks `test_component_gallery_tab` + `test_theme_builder`'s assertion); Home/Settings "close tab and return to MRU" semantics need confirmation.

**Cross-area overlap:**
- **↔ Workspace creation:** SIDE-03/05 are entry points into Workspace-creation's dialog (WSC-01/04); Workspace creation owns the dialog + shared `create_workspace()`. `test_workspace_tab_enhancements`'s Cmd+T moves wholly to Workspace creation.
- **↔ Agent/terminal:** `TAB_CONTEXT_MENU_*` ids are **shared** workspace-tab/agent-tab; redesign must split into a **workspace-row** menu (Sidebar) vs **panel-tab** menu (Agent/terminal) — coordinate so both don't independently rename/remove the same ids.
- **`test_optimistic_deletion.py` split (explicit):** workspace-deletion tests → Sidebar (`test_workspace_optimistic_deletion.py`); agent-deletion tests → Agent/terminal (agent-panel file). One file, two owners.
- **`test_mark_unread.py` / `test_read_unread_status.py` split (explicit):** workspace-level unread → Sidebar (sidebar row); agent-tab-level unread → Agent/terminal (panel tab).
- **↔ Sections:** `test_zen_mode.py`'s `get_bottom_bar`/`get_top_bar_locator` is the section/bottom-bar surface — leave to Sections.
