# UI refresh — removed features & changed functionality

Audit of what the `bryden/ui-refresh-2` branch removes or changes, vs `main`.
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
| **Agent diagnostics submenu** | `TAB_CONTEXT_MENU_DIAGNOSTICS` copy-id submenu on agent tabs | diagnostics tests removed; ElementID unused | (none — **[verify]** whether intentional) |
| **Progressive-collapse banner** | Workspace banner that hid items + inert "…" overflow menu | `test_workspace_banner_overflow.py` deleted | Simpler `WorkspaceHeader` |
| **Review-all gated button** | A button to toggle the combined review-all diff | `test_review_all_visibility.py` deleted | `REVIEW_ALL_PANEL` opened via the `+` dropdown |
| **History panel** | Standalone History panel | `test_history_panel*.py` deleted; **not** in the panel registry | Folded into Commits view **[verify]** (`historyPanel/HistoryTabContent.tsx` still exists) |
| **Bare "terminal" agent type** | A plain "terminal" agent kind | (decision B2) | "New terminal" (bottom) + registered terminal agents (e.g. Claude CLI) |
| **Zen mode exit button** | `ExitZenModeButton` | `ExitZenModeButton.tsx` + `test_zen_mode.py` deleted | **[verify]** — zen-mode references still exist in `CommandPalette/hooks.ts`; the button is gone but the command may remain |

## 2. Deferred / not-wired (feature exists in spirit but disabled)

- **AGENT-07 mark-unread tab action** — deferred; `test_mark_unread` skipped.

## 3. Changed functionality (behavior, not removal)

- **Workspace navigation:** tabs → sidebar **rows** (click to open, hover to peek, middle-click to close).
- **Workspace delete:** confirmation dialog **restored & kept** (trash icon / "…" dropdown / right-click → confirm → optimistic delete). Per your mid-session instruction.
- **Workspace peek:** popover now follows the hovered **sidebar row** (was the tab); content unchanged. Preserved per your instruction.
- **Panel opening:** via the section `+` add-panel dropdown; **left/right/bottom sections start collapsed** and must be expanded to reveal a panel.
- **Per-workspace panel layout:** panel visibility/sizes are local per workspace (PERSIST); `usePanelLayoutSync` / `usePerWorkspacePanelLayout` replaced by the section-shell layout atoms.
- **Command palette open:** sidebar **Cmd+K** link (`SIDEBAR_CMDK_LINK`) / shortcut, not the top-bar search button. Disabled in the empty-first-run state (FIRST-03).
- **Agent status:** panel tabs expose `data-dot-status` (`running`/`waiting`/`read`/`unread`/`error`) instead of `data-status=TaskStatus`.
- **Empty / first run:** zero workspaces renders `EmptyFirstRunPage` (inline create form), distinct from the Home list's own empty state.
- **Agent auto-open (new this session):** a newly-created / backend-spawned agent now auto-opens as a center panel tab.
- **Panel-tab rename (new this session):** committing an inline tab rename now persists (`renameWorkspaceAgent`); was a no-op stub.
- **Diff/file open (new this session):** opening a file/diff reveals + renders it in the host panel's single embedded viewer (was wired to a now-dead `diffPanelOpenAtom`).
- **Per-agent chat settings (new this session):** model / fast-mode / effort / draft key on the panel's agent, not the route's.

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
- **Diagnostics submenu** + **debug view** removal — confirm intentional (not deferred).
- **Zen mode** — button removed but command-palette references remain; decide whether to fully remove or restore.
