# UI refresh — removed features & changed functionality

Audit of what the ui-refresh branch removes or changes, vs `main`.
Evidence is the branch diff (deleted files, purged ElementIDs, panel registry).
Items I'm not 100% sure of are marked **[verify]**.

> Scope note: this covers the whole branch (the section-shell rebuild), not only
> this session's commits. Some removals landed in earlier Phase-7/8 commits.

---

## 1. Removed UI surfaces

| Feature | What it was | Evidence | Replacement |
|---|---|---|---|
| **Top bar** | Global top bar (Home/Settings/search/start-task buttons) | `TopBar.tsx` deleted; `TOP_BAR`, `HOME_BUTTON`, `SETTINGS_BUTTON`, `START_TASK_BUTTON` purged | Left `WorkspaceSidebar` |
| **Workspace tab strip** | Horizontal workspace tabs | `WorkspaceTabs.tsx` deleted; `WORKSPACE_TAB`, `HOME_TAB`, `SETTINGS_TAB`, `ADD_WORKSPACE_TAB` purged | Sidebar workspace **rows** |
| **Bottom bar** | `BottomBar` chrome | `BottomBar.tsx` deleted; `BOTTOM_BAR` purged | (folded into shell / `WorkspaceHeader`) |
| **Agent tab strip** | `AgentTabs` per-workspace agent tabs | `AgentTabs.tsx` deleted | Agents are center-section **panel tabs** (`PANEL_TAB-agent:<id>`) |
| **Docking / zone layout** | Drag panels into left/right/bottom zones | whole `components/panels/` tree deleted (`DockingLayout`, `LeftSidebar`, `RightSidebar`, `SidebarDropZone`, `ZoneContent`, `PanelContextMenu`, `VerticalSplit`, …); `SIDE_TOGGLE_*`, `PANEL_TOP/BOTTOM/RIGHT_*`, `PANEL_CONTEXT_MENU_MOVE_TO/ZONE_OPTION` purged | Four-section grid (left/center/right/bottom) with the add-panel `+` dropdown |
| **Standalone Add-Workspace page** | `/ws/new` full page + `NewWorkspaceForm` | `AddWorkspacePage.tsx`, `NewWorkspaceForm.tsx`, `BranchNameField.tsx` deleted | New-workspace **modal** (and inline empty-first-run form) |
| **Component Gallery** | Dev-only `/component-gallery` page + Theme-Builder button | `ComponentGalleryPage.tsx` deleted; `COMPONENT_GALLERY_TAB`, `SETTINGS_THEME_BUILDER_COMPONENT_GALLERY` purged | (none — dev-only) |
| **Settings → Panels** | "Enable panel" settings page + layout diagram | `PanelsSettingsSection.tsx`, `PanelsLayoutDiagram.tsx` deleted; `SETTINGS_NAV_PANELS` purged | Panels open on demand via the section `+` dropdown |
| **Multi-tab diff bar** | `DiffTabBar` (multiple open file tabs + close) | `DiffTabBar.tsx`, `DiffPanel.tsx`, `DiffSplitContainer.tsx` deleted | **Single** embedded `DiffViewer` per host panel (your decision) |
| **Diff expand/fullscreen control** | Diff-local expand toggle + escape-to-exit | `test_expand_escape.py` deleted; `DIFF_EXPAND_TOGGLE` unused | Section **maximize** |
| **Debug chat view** | Toggle to a raw "debug" chat view | debug-view test + `switch_to_debug_view`/`get_debug_chat_view` POMs removed | (none) |
| **Agent diagnostics submenu** | `TAB_CONTEXT_MENU_DIAGNOSTICS` copy-id submenu on agent tabs | diagnostics tests removed; ElementID unused | Flat diagnostics **copy items** on the shared panel-tab context menu (copy agent id / name, claude session id, transcript paths) — no submenu (resolved 2026-07-02) |
| **Progressive-collapse banner** | Workspace banner that hid items + inert "…" overflow menu | `test_workspace_banner_overflow.py` deleted | Simpler `WorkspaceHeader` |
| **Review-all gated button** | A button to toggle the combined review-all diff (behind an experimental toggle) | `test_review_all_visibility.py` deleted; experimental toggle deleted | `REVIEW_ALL_PANEL` opened via the `+` dropdown — unconditional (no experimental gate); scope defaults to "All", applied on panel open (resolved 2026-07-02) |
| **History panel** | Standalone History panel | `test_history_panel*.py` deleted; **not** in the panel registry | Folded into Commits view **[verify]** (`historyPanel/HistoryTabContent.tsx` still exists) |
| **Bare "terminal" agent type** | A plain "terminal" agent kind | (decision B2) | "New terminal" (bottom) + registered terminal agents (e.g. Claude CLI) |
| **Zen mode exit button** | `ExitZenModeButton` | `ExitZenModeButton.tsx` + `test_zen_mode.py` deleted | (none — zen mode is fully removed; the last stale comment reference in `CommandPalette/hooks.ts` was cleaned up 2026-07-02) |
| **Tab "Close others" / "Close all"** | Context-menu items to close other/all tabs | `TAB_CONTEXT_MENU_CLOSE_OTHERS` / `TAB_CONTEXT_MENU_CLOSE_ALL` POM getters removed | (none — removed from the product; the panel-tab context menu offers only Rename, Mark as unread, and the diagnostics copy items) (resolved 2026-07-02) |

## 2. Deferred / not-wired (feature exists in spirit but disabled)

- (none — the previously-deferred mark-unread tab action shipped 2026-07-02:
  "Mark as unread" is live on the panel-tab context menu and as a Cmd+K agent
  action, and `test_mark_unread` is unskipped.)

## 3. Changed functionality (behavior, not removal)

- **Workspace navigation:** tabs → sidebar **rows** (click to open, hover to peek, middle-click to close).
- **Workspace delete:** confirmation dialog **restored & kept** (trash icon / "…" dropdown / right-click → confirm → optimistic delete). Per your mid-session instruction.
- **Workspace peek:** popover now follows the hovered **sidebar row** (was the tab); content unchanged. Preserved per your instruction.
- **Panel opening:** via the section `+` add-panel dropdown; **left/right/bottom sections start collapsed** and must be expanded to reveal a panel.
- **Per-workspace panel layout:** panel visibility/sizes are local per workspace (PERSIST); `usePanelLayoutSync` / `usePerWorkspacePanelLayout` replaced by the section-shell layout atoms.
- **Command palette open:** sidebar **Cmd+K** link (`SIDEBAR_CMDK_LINK`) / shortcut, not the top-bar search button. Disabled in the empty-first-run state (FIRST-03).
- **Agent status:** panel tabs render a **visible status dot** (restored 2026-07-02) and expose `data-dot-status` (`running`/`waiting`/`read`/`unread`/`error`) instead of `data-status=TaskStatus`.
- **Empty / first run:** zero workspaces renders `EmptyFirstRunPage` (inline create form), distinct from the Home list's own empty state.
- **Agent auto-open (new this session):** a newly-created / backend-spawned agent now auto-opens as a center panel tab.
- **Panel-tab rename (new this session):** committing an inline tab rename now persists (`renameWorkspaceAgent`); was a no-op stub.
- **Diff/file open (new this session):** opening a file/diff reveals + renders it in the host panel's single embedded viewer (was wired to a now-dead `diffPanelOpenAtom`).
- **Per-agent chat settings (new this session):** model / fast-mode / effort / draft key on the panel's agent, not the route's.
- **Keybindings (resolved 2026-07-02):** `delete_workspace` and `next_tab` / `previous_tab` are live again — the tab pair relabeled as workspace navigation (cycle workspaces); `close_workspace` is removed (there is no close-vs-delete distinction anymore).
- **Splits persist when emptied (resolved 2026-07-02):** the split self-heal is removed — emptying a split half leaves the split in place showing the empty state, with an explicit Close-split action to merge back.
- **Explorer list drag-resize (resolved 2026-07-02):** the Files/Changes/Commits list pane is drag-resizable via the `ExplorerLayout` divider; one shared width persisted across the three panels, clamped to 180–480px.
- **Bare-terminal pinned row normalization (resolved 2026-07-02):** a stored last-used agent type of "terminal" (from the new-workspace form's first-agent select) falls back to Claude for the pinned "New {recent} agent" row — the add-panel model has no bare terminal agent.
- **Maximize is per-workspace (resolved 2026-07-02):** section maximize is tracked per workspace (switching workspaces no longer leaks a maximized section across them) and clears when the section collapses; still transient across reloads.
- **Commit / automated prompts routing (resolved 2026-07-02):** automated prompts (e.g. commit-message generation) route to the workspace's most-recently-focused agent, including prompt-capable registered terminal agents.

## 4. Removed integration-test coverage (deleted test files)

These tested removed surfaces; deleted with their features. Grouped:

- **Old chrome / tabs:** `test_home_page_tab`, `test_settings_tab`, `test_component_gallery_tab`, `test_add_workspace_page`, `test_side_toggle`, `test_panel_zones`, `test_workspace_tab_enhancements`, `test_workspace_tab_context_menu_icons`, `test_tab_context_menus`, `test_closed_workspaces_dropdown`, `test_agent_tab_context_menu`, `test_agent_type_menu`, `test_agent_diagnostics_context_menu`, `test_workspace_diagnostics_context_menu`, `test_terminal_tab_enhancements`, `test_terminal_agent_basic`.
- **Docking / panels-settings:** `test_panels_settings`.
- **Old diff/file-browser model:** `test_file_browser`, `test_file_browser_tabs`, `test_file_browser_uncommitted`, `test_file_browser_symlink_replaces_directory`, `test_file_open_diff_modes`, `test_diff_tab_close_others`, `test_diff_scope_switching`, `test_diff_refresh_on_branch_change`, `test_diff_loading_bar_no_file`, `test_open_in_viewer`, `test_discard_file`, `test_discard_preserves_all_tab`, `test_commit_from_changes_tab`, `test_markdown_gfm`, `test_markdown_render_toggle`, `test_path_tilde_display`, `test_history_panel`, `test_history_panel_diffs`, `test_target_branch`, `test_expand_escape`.
- **Workspace lifecycle (old):** `test_optimistic_close`, `test_optimistic_deletion`, `test_workspace_close_vs_delete`, `test_zen_mode`, `test_review_all_visibility`, `test_workspace_banner_overflow`.
- **Multi-tab diff (this session):** the multi-tab subset of `test_sculpt_ui_open_file` (no-duplicate-tab, distinct-tabs, combined-tab-remains) + the debug-view test.

> Many of these were replaced by equivalent section-shell coverage (e.g. file
> browser → `test_files_panel` / `test_sculpt_ui_open_file`; tab context menus →
> sidebar-row + panel-tab tests). The handoff review should confirm no *behavioral*
> coverage was lost without a replacement — see the integration-review checklist.

## Items flagged for your review
- **History panel** fully gone vs. folded into Commits — confirm intent.
- ~~**Diagnostics submenu** + **debug view** removal~~ — resolved 2026-07-02: both intentional. Diagnostics render as flat copy items on the panel-tab context menu; the debug chat view is deleted outright.
- ~~**Zen mode**~~ — resolved 2026-07-02: fully removed; the stale palette-comment reference is cleaned up.
