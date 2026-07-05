# Sculptor — Scenario Test Coverage Report (integration tests only)

This report assesses, for every scenario in [`scenarios.md`](./scenarios.md), whether the
existing **integration** test suite adequately covers it, and names the specific integration
tests to add where coverage is missing or partial.

## Scope of this report

**Only integration tests count as coverage here**, so the report reflects end-to-end coverage that
drives the real UI and asserts user-visible outcomes.

Integration tests considered:

- `sculptor/tests/integration/frontend/test_*.py` — Playwright-driven, FakeClaude-backed UI tests
  (the bulk of deterministic user-visible coverage).
- `sculptor/tests/integration/regression/test_*.py` — regression tests.
- `sculptor/tests/integration/real_claude/` and `real_pi/` — model-backed end-to-end flows.

## Status definitions

- **Complete** — an integration test performs the user action *and* asserts the user-visible
  outcome the scenario describes.
- **Partial** — an integration test exists but misses part of the Given/When/Then (only the happy
  path, only one state of several, drives the action but asserts nothing visible, etc.).
- **Missing** — no integration test meaningfully covers it.

> Note on SET-* : several settings scenarios are umbrella entries covering multiple controls in one
> section; they are Partial when only some controls in that section have an integration test.

## Executive summary

| Area | Complete | Partial | Missing | Total |
|------|---------:|--------:|--------:|------:|
| SHELL | 24 | 12 | 14 | 50 |
| ROUTE | 1 | 1 | 4 | 6 |
| HELP | 0 | 2 | 1 | 3 |
| HOME | 2 | 4 | 14 | 20 |
| ADDWS | 8 | 14 | 3 | 25 |
| ADDREPO | 6 | 5 | 2 | 13 |
| ONB | 11 | 10 | 15 | 36 |
| WS | 41 | 20 | 18 | 79 |
| CHAT | 21 | 16 | 9 | 46 |
| MSG | 15 | 12 | 10 | 37 |
| PANEL | 23 | 20 | 14 | 57 |
| CMDP | 4 | 9 | 18 | 31 |
| SET | 13 | 18 | 10 | 41 |
| DEV | 3 | 1 | 0 | 4 |
| MENT | 5 | 2 | 3 | 10 |
| SKILL | 2 | 1 | 0 | 3 |
| ACT | 2 | 3 | 1 | 6 |
| **Total** | **181** | **150** | **136** | **467** |

**Under the integration-only standard, 39% of scenarios are completely covered, 32% partially, and
29% not at all.** (Counts are derived directly from the two sections below.)

The per-scenario detail is split into two sections: **Coverage gaps — Partial & Missing** (every
scenario needing work, with the test to add) and **Complete coverage** (every scenario already fully
covered, with the test that covers it). Each scenario appears in exactly one.

## Coverage gaps — Partial & Missing

Every scenario that is **not** Complete, grouped by area. **Missing** = no integration coverage (the *to add* column describes a new test to write); **Partial** = some integration coverage exists (the *Existing* column shows what, the *to add* column the assertion still needed).

### SHELL / ROUTE / HELP

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| SHELL-002 | Partial | test_home_page_tab.py::test_home_page_opens_as_tab (uses navigate helper, not the top-bar Home button) | Click the top-bar Home button (and one pressing the Home keybinding); assert a Home tab appears/re-activates with the home page shown. |
| SHELL-004 | Partial | test_home_page_tab.py::test_clicking_workspace_replaces_home_tab (clicks a workspace row, not a non-active tab) | With 2+ open tabs, click a non-active tab and assert it becomes active and its content renders. |
| SHELL-005 | Missing | — | With multiple tabs, press Cmd+] and assert the next tab activates, including wrap from last to first. |
| SHELL-006 | Missing | — | Press Cmd+[ and assert the previous tab activates, including wrap from first to last. |
| SHELL-008 | Missing | — | Middle-click a non-active tab and assert it closes while the active tab is unchanged. |
| SHELL-010 | Missing | — | Drag-reorder one tab past another; assert the drop indicator, the order change on release, and an unchanged active tab. |
| SHELL-011 | Missing | — | Open more tabs than fit; dispatch a wheel event over the tab bar; assert horizontal scroll position changes. |
| SHELL-012 | Missing | — | With overflowing tabs, activate an off-screen tab (keyboard cycle); assert it scrolls into the viewport. |
| SHELL-013 | Missing | — | Long-titled tab at constrained width; assert the label is ellipsis-truncated. |
| SHELL-014 | Partial | test_terminal_agent_signals.py::test_terminal_agent_signals_drive_tab_status_dot | Assert the visual variants: pulsing running vs solid waiting/ready, red error dot, two-dot mixed-status case. |
| SHELL-015 | Partial | test_workspace_tab_context_menu_icons.py::test_workspace_context_menu_rename; test_tab_context_menus.py::test_terminal_tab_context_menu_close_others | Right-click a workspace tab and assert the full menu set (Close, Close others, Close all, Rename, Delete, git actions). |
| SHELL-018 | Partial | test_tab_context_menus.py::test_terminal_tab_context_menu_close_others (terminal tabs only) | On workspace tabs, exercise "Close others" and "Close all"; assert all-others/all close and "Close all" lands on the Add Workspace page. |
| SHELL-019 | Partial | test_restarts.py::test_tasks_persist_on_restart; test_restart_mru.py::test_restart_restores_active_workspace_and_agent | Open 3+ tabs in a specific order with a known active one, restart, assert same tabs/order/active tab. |
| SHELL-026 | Partial | test_keybindings.py::test_help_dialog_reflects_customized_bindings (opens via Cmd+/, not the Help button) | Click the top-bar Help (?) button and assert the keyboard-shortcuts dialog opens. |
| SHELL-027 | Missing | — | Hover a top-bar button and assert a tooltip showing the button name plus its keyboard shortcut. |
| SHELL-033 | Partial | test_regression_terminal_theme_toggle.py::test_terminal_theme_updates_on_toggle (presses Cmd+Shift+D; asserts xterm colors, not the app-level theme) | Press Cmd+Shift+D and assert the app-level light/dark theme flips without a reload. |
| SHELL-034 | Missing | — | Assert the version number is visible bottom-right on a non-workspace page, and hidden in zen mode. |
| SHELL-035 | Partial | test_auto_update_browser.py::test_null_initial_state_version_popover | Assert the opened popover shows the diagnostics fields: platform, uptime, active agents, disk, paths, Claude CLI info. |
| SHELL-038 | Partial | test_auto_update_browser.py::test_ready_status_shows_persistent_toast; test_auto_update_electron.py::test_update_available_and_ready | Click "Install and restart"; assert the button changes to "Restarting…" and the restart path is invoked. |
| SHELL-041 | Partial | test_tanstack_devtools_panel.py::test_tanstack_devtools_panel_mounts_with_content (TanStack Devtools only) | Toggle "React Grab" and "TanStack event log" from the version popover and assert each dev tool appears/disappears. |
| SHELL-042 | Missing | — | Make the backend unresponsive and assert the yellow bottom banner reads "Backend not responding. Please try restarting the app." |
| SHELL-043 | Missing | — | Inject a backend health warning and assert a yellow warning banner with the message (and link if present). |
| SHELL-044 | Partial | test_project_path_monitoring.py::test_project_path_monitoring (currently skipped) | Un-skip/rewrite to assert the "Project folder not found: {name}." banner with a "Learn more" link that opens the dialog. |
| SHELL-045 | Missing | — | Assert the backend loading splash shows the Sculptor logo, "Loading" message, and progress bar until ready. |
| SHELL-047 | Missing | — | In dev/from-source mode, assert the bottom-left dev-mode indicator renders and hovering shows a "Running from source" tooltip with the workspace id. |
| SHELL-048 | Missing | — | Press Cmd+= / Cmd+- / Cmd+0; assert the zoom scales up/down/resets to 100% and persists across restart. |
| ROUTE-002 | Partial | test_restart_mru.py::test_restart_with_no_mru_lands_on_new; test_add_workspace_page.py::test_workspace_form_draft_persists_after_navigation | Navigate to bare `/ws/new` and assert the URL is rewritten to `/ws/new/{draftId}` with the Add Workspace form displayed. |
| ROUTE-003 | Missing | — | Navigate to an unknown route; assert the Not-Found page shows the logo, "The page you are looking for does not exist.", and a home link. |
| ROUTE-004 | Missing | — | Force a loader/component to throw; assert the error page renders a generic message plus error details in a scrollable box. |
| ROUTE-005 | Missing | — | On the route error page, click "Copy Error to Clipboard"; assert the clipboard contains the error text. |
| ROUTE-006 | Missing | — | Set a custom backend command, trigger the error page, click "Clear Custom Backend Command"; assert the button disables and its label changes to the "cleared — restart" state. |
| HELP-001 | Partial | test_keybindings.py::test_help_dialog_reflects_customized_bindings; ::test_help_dialog_hides_unbound | Add opening via the Help button (see SHELL-026) and assert the modal title is "Help" with shortcuts grouped by category. |
| HELP-002 | Missing | — | Open the help dialog and assert a shortcut renders an OS-formatted key badge (e.g. `Cmd+K` on macOS, `Ctrl+K` elsewhere). |
| HELP-003 | Partial | test_keybindings.py::test_help_dialog_reflects_customized_bindings (closes via dialog.close()/Escape) | Assert both the X button and the Escape key close the help dialog. |

### HOME / ADDWS / ADDREPO

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| HOME-001 | Missing | — | Delay the workspace-list fetch and assert the list-area spinner is visible. |
| HOME-003 | Partial | test_home_page.py::test_workspace_search_filters_list (uses get_search_input) | Assert placeholder "Search workspaces…" and that the input is focused on load. |
| HOME-004 | Partial | test_home_page.py::test_workspace_search_filters_list (filters by name only) | Extend to assert filtering by branch and project, plus case-insensitivity. |
| HOME-005 | Missing | — | Type a non-matching query; assert centered `No results for "{query}"`. |
| HOME-006 | Missing | — | Fill search, press Escape; assert query cleared, full list back, focus returns to the search input. |
| HOME-007 | Missing | — | Create 3+ workspaces with distinct activity; assert most-recent-first row order. |
| HOME-008 | Missing | — | Create >25 workspaces; assert 25 rows + "Show more (N remaining)"; click reveals next 25. |
| HOME-009 | Missing | — | After "Show more", type a query; assert visible count resets to first 25 filtered. |
| HOME-010 | Partial | test_home_page.py::test_workspace_row_shows_current_branch_not_source_branch; test_backend_pr_polling.py::test_home_page_shows_pr_badge | Add row assertions for status dot, name, project name on hover, relative last-activity time, hover-revealed delete button. |
| HOME-011 | Missing | — | Hover/focus a row; assert background change and project name + delete button become visible. |
| HOME-012 | Missing | — | From the search box, ArrowDown focuses first row (scrolled into view); ArrowUp from first row returns to search box. |
| HOME-014 | Missing | — | Cmd/Ctrl-click a row (and "Open in New Tab" via context menu) opens it in a new tab with Home still visible. |
| HOME-015 | Missing | — | Right-click a row; assert "Open in New Tab" and a red "Delete Workspace" entry. |
| HOME-016 | Missing | — | Hover-click the trash icon (and via context menu) opens the delete-confirmation dialog. |
| HOME-017 | Missing | — | Assert "Delete workspace?" title, warning naming the workspace, Cancel, and a red default-focused Delete button. |
| HOME-018 | Missing | — | Open dialog, click Cancel / press Escape; assert dialog closes and row remains. |
| HOME-019 | Missing | — | Open dialog from a home row, click Delete; assert dialog closes and row disappears. (test_optimistic_deletion.py covers the tab menu, not the home-row dialog.) |
| HOME-020 | Partial | test_backend_pr_polling.py::test_home_page_shows_pr_badge; ::test_multiple_workspaces_independent_pr_status | Add home-row assertions for "Checking PR…", "Create PR", merged/closed badge, "Assign PR", error button. |
| ADDWS-001 | Partial | test_add_workspace_page.py (asserts form/submit button) | Delay project fetch; assert the centered spinner before the form. |
| ADDWS-002 | Partial | test_multi_repo.py::test_mru_project_updates_after_creating_workspace | Add the no-MRU case (first project pre-selected). |
| ADDWS-003 | Partial | test_add_workspace_page.py::test_cmd_i_focuses_prompt_input | Assert placeholder "Untitled workspace (optional)" and autofocus on initial load. |
| ADDWS-004 | Partial | test_worktree_create_happy_path.py::test_worktree_create_with_empty_workspace_name_random_slug | Assert created workspace named "Untitled workspace" (+ whitespace-only case). |
| ADDWS-006 | Partial | test_multi_repo.py::test_create_new_project_from_add_workspace_page; ::test_adding_duplicate_repo_shows_error | Open selector; assert all projects plus an "Add Repository" entry. |
| ADDWS-007 | Partial | test_multi_repo.py::test_create_workspaces_in_multiple_projects_and_switch | Assert selecting another project reloads the branch selector and clears any branch-name override. |
| ADDWS-008 | Partial | test_multi_repo.py::test_create_new_project_from_add_workspace_page (adds via Settings UI) | Trigger "Add Repository" from the repo-selector dropdown; assert the new project is auto-selected. |
| ADDWS-009 | Missing | — | Assert the branch control shows spinner + "Loading …" and is disabled while branch info loads. |
| ADDWS-010 | Partial | test_worktree_create_happy_path.py::test_worktree_create_with_default_branch_name | Open the branch selector; assert recent branches + "Fetch more branches"; selecting one updates the source branch and clears the override. |
| ADDWS-011 | Missing | — | In-place mode: assert the branch selector is disabled with the in-place tooltip. |
| ADDWS-012 | Partial | test_clone_mode_branch_name.py; test_worktree_create_happy_path.py | Assert branch-name field across all three modes (Worktree required / Clone optional / In-place absent). |
| ADDWS-014 | Partial | test_worktree_create_happy_path.py::test_worktree_create_with_custom_branch_name | Assert auto-fill stops, a reset link appears, and clicking reset restores the preview. |
| ADDWS-018 | Partial | test_worktree_edge_cases.py::test_clone_mode_hidden_when_flag_off | Add the neither-experimental-mode case: selector hidden, defaults to Worktree. |
| ADDWS-019 | Partial | test_clone_mode_branch_name.py; test_worktree_edge_cases.py::test_clone_mode_hidden_when_flag_off | Switch modes and assert branch fields update live (Clone optional; In-place removes field + disables selector). |
| ADDWS-020 | Partial | test_branch_name_collisions.py::test_worktree_mode_collision_blocks_creation | Assert the Create button's explanatory disabled tooltips and the "Cmd/Ctrl+↵" ready tooltip. |
| ADDWS-023 | Partial | test_branch_name_collisions.py::test_worktree_mode_collision_blocks_creation (pre-submit) | Force a submit-time 409; assert toast "Branch '{name}' already exists" and the form stays open. |
| ADDWS-024 | Missing | — | Force creation to fail; assert "Failed to create workspace"/"Failed to create agent" toast with details. |
| ADDREPO-001 | Partial | test_multi_repo.py::test_adding_duplicate_repo_shows_error; test_regression_settings_delete_repo_stays_on_page.py::test_adding_repo_stays_on_settings_page; test_add_repo_remote_picker.py (dialog opens on GitHub source) | Assert the source picker defaults to GitHub with a Local Folder option, and that Local Folder shows a focused path input + a Browse button on desktop. |
| ADDREPO-002 | Missing | — | Open the dialog, click Cancel / Escape / overlay; assert it closes with no changes. |
| ADDREPO-003 | Partial | test_path_autocomplete_keyboard.py::test_cmd_enter_submits_path | While validation is in progress, attempt to close; assert the dialog stays open. |
| ADDREPO-004 | Partial | test_multi_repo.py::test_create_new_project_from_add_workspace_page (adds via Settings UI) | Focused dialog test: enter a valid path, click "Add Repository"; assert it closes and the new repo is selected in the dropdown. |
| ADDREPO-005 | Missing | — | Type a path, close the dialog, reopen it; assert the path input is empty. |
| ADDREPO-006 | Partial | test_path_autocomplete_keyboard.py::test_autocomplete_shows_submit_hint; test_files_panel.py::test_path_autocomplete_shows_tilde_for_home_directory | Assert the debounce spinner before results and the "No matching directories" message when empty. |
| ADDREPO-008 | Partial | test_path_autocomplete_keyboard.py::test_autocomplete_shows_submit_hint; ::test_cmd_enter_submits_path | Assert all three footer hints verbatim ("Esc: close", "↵: open", "{Meta}↵: add") and the Enter-with-dropdown-closed submit path. |

### ONB / MENT / SKILL / ACT

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| ONB-001 | Missing | — | Assert the step indicator renders 3 dots, current distinct, past clickable, future disabled. |
| ONB-003 | Missing | — | From the Email step, click the Installation/Add-Repo dots; assert the wizard does NOT advance. |
| ONB-004 | Partial | test_telemetry_opt_out.py::test_onboarding_email_with_telemetry_opt_out | Assert full-name autofocus, marketing checkbox unchecked, terms/privacy links, and the "Your code is yours…" message. |
| ONB-005 | Missing | — | Type empty / no-`@` email; assert Get Started disabled. |
| ONB-006 | Partial | test_onboarding.py::test_full_onboarding_flow (implicitly) | Explicit test: typing an email with `@` flips Get Started to enabled. |
| ONB-007 | Partial | test_onboarding.py::test_full_onboarding_flow | Assert the button shows a spinner / is disabled while the email request is in flight. |
| ONB-010 | Partial | test_telemetry_opt_out.py::test_onboarding_email_with_telemetry_opt_out (asserts persisted flags) | Add a direct UI assertion that clicking the marketing/telemetry checkboxes toggles their checked state. |
| ONB-011 | Missing | — | Assert "Let's get you set up" / "The following are required to use Sculptor" headers. |
| ONB-012 | Missing | — | Drive a `loading` dependency state; assert spinner + "—" path/version. |
| ONB-015 | Missing | — | Stub a wrong version; assert red error + (expanded) current/required versions. |
| ONB-017 | Partial | test_onboarding.py::test_claude_not_authenticated | Assert the visible "authenticating" spinner + the `claude auth login` help message during the in-progress window. |
| ONB-018 | Missing | test_claude_binary_installation.py::test_onboarding_managed_mode_auto_installs_claude (SKIPPED — SCU-355) | Add a hermetic managed-install test asserting "installing" with a circular progress percentage. |
| ONB-019 | Missing | — | Add an onboarding-card install-failure test asserting error + retry/re-check. |
| ONB-020 | Partial | test_onboarding.py::test_dependency_path_and_version_display / test_onboarding_without_claude_installed | Assert the chevron flips and mode controls appear on expand. |
| ONB-021 | Missing | — | Open the Install affordance; assert popover shows the install command (e.g. `brew install …`) and a docs link. |
| ONB-023 | Missing | — | Expand a card, click "Use System PATH" / "Use Managed"; assert the mode switches and UI updates. |
| ONB-025 | Missing | — | Click "check again"; assert text flips to "Checking…" briefly and cards refresh. |
| ONB-027 | Partial | test_onboarding.py::test_full_onboarding_flow | Assert "Add your first repo" header, the GitHub-default source picker with a Local Folder option, and the `~/path/to/repo` placeholder under Local Folder. |
| ONB-028 | Missing | — | On desktop with Local Folder selected, click "Or browse for a folder", select a folder; assert the path input is populated. |
| ONB-035 | Missing | — | On the optional GitHub CLI card, click "Sign in"; assert a one-time code, an "Open verification page" link, and a waiting state; once gh reports authenticated assert the card flips to signed-in. |
| ONB-036 | Missing | — | On the onboarding Add-Repo step's GitHub source, select a repo (or paste a URL) and submit; assert the clone-progress view, then the repo is added and the wizard completes. |
| ONB-029 | Missing | — | Assert Add disabled + tooltip "Enter a repository path above" when empty; enabled after typing; spinner while validating. |
| ONB-031 | Partial | test_multi_repo.py::test_git_init_dialog_for_non_git_directories (via Add Workspace page, not onboarding) | Add the same flow on the onboarding Add-Repo step; assert "Setting up repository…" and Cancel-returns. |
| ONB-032 | Partial | test_multi_repo.py::test_empty_repo_initial_commit_dialog (via Settings, not onboarding) | Cover the empty-repo prompt on the onboarding Add-Repo step incl. Cancel-returns. |
| ONB-033 | Partial | test_multi_repo.py::test_adding_duplicate_repo_shows_error (via Settings) | Add an onboarding-step test for a nonexistent/inaccessible path → error dialog with a Close button. |
| MENT-001 | Partial | test_at_mention_file_chip_click_opens_tab.py::test_file_chip_click_opens_file_view_tab; ::test_nested_file_chip_click_opens_correct_tab | Add coverage that hovering a file mention chip shows the full-path popover + action hint. |
| MENT-002 | Missing | — | Hover a skill mention chip; assert a popover with type badge, skill id, description; chip not clickable. |
| MENT-003 | Missing | — | Drive an entity mention chip: workspace/agent click navigates; repository/deleted not clickable + strike-through; hover shows detail popover. |
| MENT-004 | Missing | — | Open agent/workspace/repository detail popovers; assert icon/title/badge/body/meta footer and the deleted "no longer exists" note. |
| MENT-009 | Partial | test_image_upload.py (file input, not the `+` picker Images category) | Selecting the Images category from the `+` picker fires the image-upload trigger; row hidden when unsupported. |
| SKILL-002 | Partial | test_skill_autocomplete.py::test_plugin_skill_appears_in_autocomplete_with_sculptor_badge; test_pseudo_skills.py::test_builtin_skills_appear_in_autocomplete_with_badges (badge text only) | Hover chip A then chip B; assert popover content swaps instantly; scrolling suppresses flapping. |
| ACT-002 | Partial | test_custom_actions.py::test_builtin_chips (built-in group exposes no delete) | Right-click a regular action chip; assert "Queue message" (run-only), "Edit action", "Move to group…" (current disabled), red "Delete action". |
| ACT-003 | Partial | test_custom_actions.py::test_create_action_from_settings; ::test_edit_action_from_settings; ::test_action_with_skill_mention_displays_cleanly_in_settings | Assert Save disabled until Name+Prompt non-empty, and `Cmd+Enter` submits when valid. |
| ACT-005 | Partial | test_custom_actions.py::test_create_group_from_settings; ::test_builtin_chips | Add inline rename (Enter/blur confirm, Escape cancel, no collapse-toggle) and header-click collapse/expand (chevron + count badge). |
| ACT-006 | Missing | — | Drag-simulation: drop indicators before/after, drop into group moves action, drop outside removes; built-ins not draggable. |

### WS

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| WS-001 | Partial | test_queued_messages.py::test_queued_message_bar_appears_and_shows_content (editor clears) | Assert the attachments preview clears after sending a message that had an image attached. |
| WS-002 | Partial | test_queued_messages.py::test_chat_input_disabled_while_message_queued | Assert Send disabled when editor empty and a hover tooltip shows the disabled reason. |
| WS-005 | Missing | — | Drag files over chat input → "Drop to attach images" overlay; on drop files appear in preview list. |
| WS-009 | Partial | test_regression_model_selection.py::test_new_agent_inherits_model_from_existing_agent | Open model selector, pick a model; assert it is highlighted and applied to the next sent message. |
| WS-013 | Missing | — | Shift+Enter inserts a line break and editor grows; sending submits the whole multiline text as one message. |
| WS-022 | Missing | — | While PR status loads, assert spinner with "Checking PR…". |
| WS-023 | Partial | test_pr_button_errors.py::test_github_happy_paths (Create PR visible) | Click Create PR; assert the default PR-creation prompt (incl. target branch) is sent to the agent. |
| WS-024 | Missing | — | Open Create-PR chevron, click "Edit prompt…", edit and Save; assert prompt updated and dialog closes. |
| WS-025 | Partial | test_pr_button_errors.py::test_github_happy_paths ("PR #42") | Assert pipeline and review status dots render on the open-PR button. |
| WS-026 | Missing | — | Click the PR number; assert the PR opens in browser (intercept window.open / browser-open RPC). |
| WS-027 | Missing | — | Open chevron popover; assert title/link, checks/pipeline status, approvals with reviewer names, unresolved comments. |
| WS-029 | Partial | test_backend_pr_polling.py::test_closed_not_merged_pr_shows_closed_state | Add the merged-PR case: merge icon + "merged" text; clicking opens browser. |
| WS-030 | Missing | — | Hover pipeline/review dots; assert tooltip text ("Pipeline running/passed/failed/No pipeline", "Approved/Review pending/No reviewers"). |
| WS-031 | Missing | — | PR with different target shows "Assign PR"; opening offers "Create PR → {target}" and "switch target to {target}". |
| WS-032 | Partial | test_pr_button_errors.py::test_github_cli_error_variants; ::test_gitlab_cli_error_variants | Assert warning-triangle vs info icon distinction and the remediation-command copy icon turning to a checkmark briefly. |
| WS-033 | Partial | test_changes_panel.py::test_switching_to_all_scope_shows_target_branch_diff; test_pr_management.py::test_banner_shows_target_branch_selector_for_non_github_gitlab_origin | Click the selector; assert the dropdown lists branches; select one; assert target updates. |
| WS-034 | Missing | — | Target differs from PR target → warning color; hover "PR #N targets {branch}"; selecting matching branch updates target. |
| WS-035 | Missing | — | Click repo segment; assert menu (Open folder, Copy path, Copy relative path, Open in installed apps); each action fires; chosen app remembered. |
| WS-038 | Partial | test_workspace_banner_overflow.py::test_collapsed_banner_has_no_inert_overflow_menu | Assert collapse priority order at successive widths: PR button → diff summary → repo segment. |
| WS-039 | Partial | test_regression_copy_branch_name.py::test_copy_branch_name_copies_workspace_branch | Assert the "Copied!" tooltip appears briefly after clicking the banner branch name. |
| WS-042 | Partial | test_multi_agent_workspace.py::test_workspaces_have_isolated_agent_tabs (click switches) | Add a next/previous-agent keybinding test asserting the view switches. |
| WS-043 | Missing | — | Hover agent status dot; assert tooltip shows status label + time-since-activity/creation. |
| WS-046 | Partial | test_agent_tab_context_menu.py::test_agent_context_menu_rename | Add double-click-to-rename + Enter; add Escape-cancels-rename. |
| WS-050 | Missing | — | Drag an agent tab to a new position; assert the tab order updates. |
| WS-057 | Partial | test_ask_user_question.py::test_ask_user_question_navigation_state; ::test_ask_user_question_next_button | Add Tab/Shift+Tab and arrow-key navigation; assert progress dots show answered/unanswered/current. |
| WS-060 | Missing | — | Agent errored + workspace deleted → input shows "deleted / cannot be restored" with no restore link. |
| WS-061 | Partial | test_workspace_peek.py::test_workspace_peek_popover_idle_state; ::test_workspace_peek_popover_waiting_state; ::test_peek_popover_shows_diff_stats | Assert a single popover surfaces status, agent list, PR info, branch, and diff stats together. |
| WS-062 | Partial | test_workspace_peek.py::test_workspace_peek_popover_hover_mechanics; test_regression_workspace_peek_stuck_on_close.py::test_workspace_peek_dismissed_on_middle_click_close | Assert content swaps instantly within grace period and close-after-delay on leaving all tabs. |
| WS-063 | Missing | — | Workspace with >5 agents shows only 5 + "+N more agents" button that reveals the rest. |
| WS-064 | Missing | — | Click peek agent row/header closes popover and opens workspace/agent; click branch copies it with "Copied!". |
| WS-065 | Partial | test_side_toggle.py::test_right_side_toggle_hides_and_shows_panels; test_zen_mode.py::test_focus_mode_hides_panels_but_keeps_chrome | Assert left, bottom, right toggle buttons + focus-mode button all present (and hidden in zen mode). |
| WS-067 | Missing | — | Empty panel toggle is disabled, shows "Panel is empty" tooltip, does nothing on click. |
| WS-068 | Missing | — | Hover a panel toggle; assert tooltip shows the panel name and its keybinding. |
| WS-069 | Partial | test_panel_zones.py::test_inner_vertical_split_height_persists_after_navigation | Assert the expand outcome (the cited fullscreen test only clicks, asserts nothing); add divider-drag-collapses-diff and expand-maximizes-diff+collapses-chat. |
| WS-071 | Partial | test_chat_search_bar.py::test_cmd_f_enter_advances_through_all_matches; ::test_search_bar_does_not_flash_red_while_typing_matching_query | Assert the "0/0" counter with the input turning red when there are no matches. |
| WS-072 | Partial | test_chat_search_bar.py::test_cmd_f_enter_advances_through_all_matches (Enter nav) | Add Shift+Enter (previous) and up/down arrow navigation. |
| WS-073 | Missing | — | Press Escape or click close → search bar closes and highlights clear. |
| WS-077 | Partial | test_ci_babysitter.py::test_plain_terminal_mru_shows_disabled_reason | Assert that a *persistent* disabled reason also forces the dropdown switch off and greys it out (inert). |

### CHAT

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| CHAT-001 | Partial | test_alpha_chat_intro.py::test_alpha_chat_intro_shows_names_and_reacts_to_renames; ::test_intro_text_renders_above_first_message | Assert intro also shows project/branch, creation time, source-branch info, shared-code warning, and the `/sculptor:help` hint. |
| CHAT-002 | Missing | — | Assert intro wording per workspace type: "Working directly in {branch}", "Branched off {branch}", "Cloned {branch} from {project}". |
| CHAT-003 | Partial | test_workspace_setup_status.py::test_setup_card_shows_succeeded | Assert the card's setup-step label, progress indicator, and elapsed-time fields specifically. |
| CHAT-006 | Partial | test_status_pill.py::test_status_pill_shows_animation; test_status_pill_background_wait.py::test_status_pill_shows_waiting_during_background_task; test_regression_auto_compact_indicator.py::test_auto_compaction_indicator_lifecycle | Assert "Thinking…"/"Streaming…"/"Calling Tools…" label text and the frozen-vs-live elapsed counter. |
| CHAT-007 | Missing | — | Assert the pill shows "X / N · {task subject}" while the agent is active with a plan (existing tests cover only the post-turn "X of N done" summary). |
| CHAT-009 | Partial | test_status_pill.py::test_status_pill_shows_stop_button; test_status_pill_plan_mode_stop.py::test_status_pill_disappears_after_single_stop_post_plan_approval | Assert "Stop (Ctrl+C)" tooltip; assert Ctrl+C interrupts; assert disabled-with-tooltip when interruption unsupported. |
| CHAT-012 | Partial | test_task_page_plan_tab.py::test_plans_update_with_completion; test_status_pill_tasks_widget.py::test_hover_opens_tasks_popover | Assert in-progress bar / pending box glyphs and green/blue/outline colors; assert description text. |
| CHAT-013 | Missing | — | Assert downstream pending tasks fade with distance. |
| CHAT-015 | Partial | test_status_pill_tasks_widget.py::test_large_dag_scale_rules (60 nodes render) | Assert compact (small-node) vs normal rendering at the 15-task threshold. |
| CHAT-017 | Partial | test_chat_search_bar.py::test_cmd_f_enter_advances_through_all_matches; test_alpha_scroll_search.py::test_alpha_search_flow | Assert the input is focused AND its text selected on open. |
| CHAT-018 | Partial | test_chat_search_bar.py::test_cmd_f_enter_advances_through_all_matches; test_alpha_scroll_search.py::test_alpha_search_flow | Assert a visible highlight element wraps the active/all matches and the active match scrolls into view. |
| CHAT-020 | Partial | test_alpha_scroll_search.py::test_alpha_search_flow (Escape → bar hidden) | Assert focus returns to chat and highlights clear; assert the close-button click path. |
| CHAT-021 | Missing | — | Switching agent/task while search is open auto-closes the search bar. |
| CHAT-022 | Missing | — | Assert auto-scroll is suppressed while search is open during streaming. |
| CHAT-024 | Partial | test_alpha_scroll_auto_scroll.py::test_user_can_scroll_during_streaming; test_alpha_scroll_behaviors.py::test_jump_button_appears_and_works | Assert the down-arrow icon and bottom-right positioning of the button. |
| CHAT-029 | Partial | test_alpha_scroll_padding_agent_switch.py::test_dynamic_padding_survives_agent_switch | Exercise window resize and the tool-density toggle, asserting the viewed message stays anchored. |
| CHAT-033 | Missing | — | "+N" collapsed-rail indicator: clicking expands the rail, clicking outside collapses it. |
| CHAT-037 | Missing | — | Click a subagent pill to open the popover; assert prompt text, nested tool pills, rendered-markdown response; Escape closes it. |
| CHAT-038 | Missing | — | Arrow-key navigation in the subagent popover (left/right through nested tool pills, up/down between rows). |
| CHAT-039 | Partial | test_stopped_turn_footer.py::test_stopped_turn_footer_shows_duration_after_content_streamed; ::test_turn_footer_shows_metrics_after_completed_turn; test_turn_summary.py::test_turn_footer_shows_file_count_after_write_file | Assert context-usage % in the footer. |
| CHAT-040 | Partial | test_turn_footer_interactions.py::test_token_popover_shows_breakdown_on_click | Assert the reasoning-tokens line and the context current/threshold values in the popover. |
| CHAT-043 | Partial | test_alpha_ask_user_question.py::test_alpha_auq_pill_dismissed_state | Assert the dimmed-options styling on the dismissed block. |
| CHAT-044 | Partial | test_alpha_chat_view.py::test_debug_view_displays_blocks | Assert role, id, timestamp, and tool_use/tool_result names per message. |
| CHAT-045 | Missing | — | Clicking a debug-view timestamp toggles between relative and absolute formats. |
| CHAT-046 | Partial | test_pi_capability_gating.py::test_pi_model_switcher_offers_pi_models_and_accepts_a_pick; ::test_fresh_pi_agent_switcher_shows_pi_models_without_a_message | Assert the picker is disabled (with the current model) for a terminal agent; that two-or-more providers cascade into per-provider submenus while a single provider stays flat; that a Pi agent with no authenticated providers shows the "Authenticate a provider" prompt; and that a harness-rejected Pi switch leaves the selection unchanged and shows an error toast. |

### MSG

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| MSG-003 | Partial | test_alpha_chat_view.py::test_alpha_view_displays_messages (text only, no timestamp) | Assert a user message renders a human-readable timestamp below the text. |
| MSG-004 | Partial | test_alpha_chat_view.py::test_alpha_copy_button (button attached only); test_regression_copy_user_message_html.py::test_copy_user_message_with_mention_copies_plain_text | Assert the checkmark-icon feedback (~1.5s) after clicking copy on a user message. |
| MSG-005 | Partial | test_inline_media_display.py::test_assistant_img_tag_renders_file_preview; test_alpha_chat_chip_rendering.py | Assert the "via {method}" badge for a `sentVia` user message, and a file-attachment preview on a user message. |
| MSG-006 | Partial | test_markdown_gfm.py::test_markdown_renders_gfm_and_neutralises_unsafe; test_alpha_nested_list_rendering.py::test_nested_ordered_list_round_trip; test_alpha_ordered_list_numbering.py::test_non_sequential_ordered_list_preserves_markers | Add assertions for blockquote and emoji rendering. |
| MSG-010 | Missing | — | Hover a blockquote, click copy; assert the quoted text (with "> " prefixes) is copied + checkmark feedback. |
| MSG-011 | Missing | — (no integration test asserts the plain→highlighted token swap) | Assert a fenced code block first renders plain monospace then swaps to colored syntax tokens. |
| MSG-012 | Missing | — | Hover a code block, click copy; assert the trimmed code is copied + checkmark for ~1.5s. |
| MSG-013 | Missing | — | Drive chat search; assert `<mark>` overlays syntax-highlighted code in the live chat view. |
| MSG-015 | Missing | — | Hover a table, click copy; assert it is copied as markdown + checkmark. |
| MSG-016 | Partial | test_alpha_tool_pill_*.py (pills render with Read/Grep labels) | Assert the per-tool icon mapping (Bash terminal / Read file / Edit pencil / Grep search + wrench fallback). |
| MSG-017 | Missing | — | Assert a running Bash/Monitor pill shows a pulsing dot in place of the icon. |
| MSG-018 | Partial | test_alpha_chat_bash_block.py::test_bash_block_shows_error_badge (error pill renders) | Assert the red error styling/class on an errored tool pill. |
| MSG-022 | Partial | test_alpha_tool_pill_hover.py::test_hover_opens_pill_popover (Read popover shows file path) | Assert line-count meta, copy-path action, open-in-Sculptor action, and the outside-workspace icon+tooltip. |
| MSG-024 | Partial | test_alpha_tool_pill_hover.py::test_hover_sibling_swaps_popover_content (Grep popover shows the pattern) | Assert the Grep popover shows the quoted pattern, search path, and match-count meta. |
| MSG-025 | Missing | — (test_alpha_chat_bash_block.py::test_bash_block_shows_error_badge asserts the pill, not the badge states) | Assert BashStatusBadge states: running=elapsed+spinner, success=duration+checkmark, error=duration+X, background=arrow icon. |
| MSG-027 | Missing | — | Assert a running file chip shows "Writing…"/"Editing…" (disabled) and an errored chip shows error styling. |
| MSG-029 | Partial | test_error_states.py::test_api_error_shows_error_block_and_agent_stays_running; ::test_usage_limit_clears_thinking_indicator_and_shows_error; test_claude_errors.py | Click an error block; assert the traceback expands. |
| MSG-031 | Missing | — (test_missing_claude_binary.py only asserts the retry button is absent for that error) | Error as last message in a non-terminal state: assert "Retry Request" shows, clicking retries, then the button disables with an "already retried" tooltip. |
| MSG-032 | Partial | test_alpha_chat_view.py::test_alpha_warning_block; test_regression_streaming_warning.py::test_simple_followup_does_not_produce_warning_block | Assert the orange badge type/message, click-to-expand traceback when present, non-clickable when none. |
| MSG-033 | Partial | test_regression_compaction_message_position.py::test_post_compaction_message_appears_after_context_summary; test_regression_auto_compact_indicator.py::test_auto_compaction_indicator_lifecycle; ::test_auto_compaction_summary_ordering | Click the context-summary pill; assert the popover opens with the full summary as scrollable markdown. |
| MSG-035 | Missing | — | Assert the folder-output icon + "Path outside of the workspace" tooltip for a tool-result path outside the workspace. |
| MSG-036 | Partial | test_chat_search_bar.py::test_cmd_f_enter_advances_through_all_matches; test_alpha_scroll_search.py::test_alpha_search_flow | Assert all matches render as highlights and the active occurrence is styled distinctly. |

### PANEL

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| PANEL-003 | Missing | — | Click the tree/list toggle; assert the same file list renders nested vs flat. |
| PANEL-005 | Partial | test_file_browser.py::test_refresh_button_reflects_file_operations; ::test_refresh_button_updates_uncommitted_tab_for_external_changes | Assert the refresh icon shows the animated/spinning state while re-fetching. |
| PANEL-009 | Missing | — | Focus tree; Up/Down moves selection, Right/Left expand/collapse, Enter opens the focused file. |
| PANEL-010 | Partial | test_file_browser.py::test_file_tree_shows_status_indicators (A); ::test_moved_file_shows_r_status_without_rename_label (R); test_changes_panel.py::test_diff_header_line_stats_reflect_uncommitted_only (M) | Assert D status + strike-through, per-row +/− stats, folder change-count badge, processing-error badge. |
| PANEL-011 | Missing | — | Agent edits a nested file; assert tree auto-scrolls, expands ancestors, applies highlight/focus styling. |
| PANEL-012 | Partial | test_file_browser.py::test_copy_file_path_for_absolute_path_file; test_regression_copy_file_path.py::test_copy_file_path_uses_workspace_code_path; test_diff_tab_close_others.py::test_diff_tab_close_others | Assert each menu item acts: Open diff view, View file, Copy relative path, Open in OS, folder Expand all/Collapse all. |
| PANEL-013 | Partial | test_file_browser.py::test_file_browser_populates_after_workspace_created_without_prompt | Assert the "No files yet" empty state and the animated skeleton/loading rows. |
| PANEL-016 | Partial | test_changes_panel.py::test_commit_button_sends_commit_message (enabled) | Assert the button is disabled (label reflects 0) when no changes exist. |
| PANEL-018 | Missing | — | Right-click commit button → "Edit prompt…", edit, Save; assert prompt persists and dialog closes. |
| PANEL-019 | Partial | test_commits_panel.py::test_history_panel_shows_commits; ::test_terminus_visible_with_no_commits | Assert the "Loading history…" and error-message states. |
| PANEL-022 | Partial | test_commits_panel.py::test_commit_hover_popover_shows_details; ::test_click_dismisses_popover | Click the copy-hash button; assert the hash is copied and the "Copied" indicator shows. |
| PANEL-025 | Partial | test_file_browser.py::test_multiple_tabs_and_close; ::test_clicking_tab_switches_displayed_file; ::test_cmd_w_closes_active_diff_tab; test_diff_tab_close_others.py::test_diff_tab_close_others | Assert tab drag-reorder, MRU-vs-adjacent close per setting, "Close all" menu item, full-path tooltip on hover. |
| PANEL-026 | Partial | test_file_browser.py::test_split_view_toggle; ::test_line_wrap_toggle; ::test_in_file_search_bar; ::test_close_diff_panel_button; test_diff_scope_and_fullscreen.py::test_expand_toggle_expands_and_collapses; test_expand_escape.py::test_escape_exits_expand_mode | Assert expand/fullscreen hides the file browser (current tests assert chat-panel hide). |
| PANEL-027 | Partial | test_file_browser.py::test_diff_file_header_shows_line_stats; test_changes_panel.py::test_diff_header_line_stats_reflect_uncommitted_only; test_commits_panel.py::test_commit_diff_file_header_shows_line_counts | Assert the breadcrumb path and the three-dot file-operations menu in the diff header. |
| PANEL-028 | Partial | test_commits_panel.py::test_clicking_renamed_file_in_commits_shows_rename_banner | Assert the "Deleted" banner and the "Binary file (cannot display)" message. |
| PANEL-029 | Missing | — (test_regression_large_diff_crash.py checks no-crash only) | Open a diff over the threshold; assert truncated diff + "Show full diff" button; click → full diff renders. |
| PANEL-030 | Partial | test_file_browser.py::test_in_file_search_bar; ::test_in_file_search_works_in_file_view | Assert the "X of Y" counter, Enter/Shift+Enter (or arrows) navigation, Escape closing. |
| PANEL-036 | Partial | test_terminal_agent_basic.py::test_terminal_agent_basic; test_registered_terminal_agent.py (tab data-dot-status read/unread) | Produce output in a non-active tab; assert a pulsing unread dot appears, then clears after switching to it. |
| PANEL-037 | Missing | — (test_terminal.py references "Starting terminal…" only incidentally in an .or_(), not as a deterministic assertion) | Assert the "Starting terminal…" message renders while a terminal is starting. |
| PANEL-038 | Partial | test_notes_panel.py::test_enable_notes_panel_reveals_icon_and_renders_editor; ::test_notes_content_is_scoped_per_workspace | Type notes, switch to another panel/tab and back; assert content preserved. |
| PANEL-039 | Missing | — | Click "Add notes to prompt"; assert notes inserted; with existing prompt text, assert the merge-conflict dialog appears. |
| PANEL-040 | Missing | — | Copy copies notes when populated, disabled when empty; "Add to prompt" disabled with no notes / no task. |
| PANEL-041 | Missing | — | Assert skills grouped into Custom/Sculptor/Built-in collapsible headers with a count badge when collapsed. |
| PANEL-042 | Missing | — | Hover a skill chip → description popover; hover another → swaps; mouse-leave closes after delay. |
| PANEL-044 | Missing | — | Open a custom/sculptor skill popover, click "open in Sculptor"; assert a file-view tab opens; built-in skills lack the option. |
| PANEL-045 | Partial | test_skills_panel.py::test_skills_panel_search_filters_list; ::test_skills_panel_keyboard_navigation_inserts_chip; ::test_skills_panel_click_inserts_mention_chip | Assert selection auto-scroll, Escape closing search, and the type-filter popover toggling which types show. |
| PANEL-046 | Missing | — | Assert Loading / error / "No skills found" / "Skills unavailable" states and chips disabled while the agent is running. |
| PANEL-047 | Partial | test_custom_actions.py::test_builtin_chips (Sculptor group first; no delete on builtin) | Assert collapsible group headers with count badges when collapsed and ungrouped actions at the bottom. |
| PANEL-048 | Partial | test_custom_actions.py::test_draft_action_populates_and_focuses_chat_input; ::test_builtin_chips | Assert an auto-submit action sends immediately and chips are disabled while the agent runs. |
| PANEL-049 | Missing | — | Agent running, action chip context menu → "Queue message"; assert prompt queued (not auto-submitted). |
| PANEL-051 | Partial | test_custom_actions.py::test_create_group_from_settings; ::test_delete_group_deletes_actions_from_settings; ::test_delete_group_deletes_actions_from_panel | Assert inline group rename (Enter/blur confirms) and Escape-cancel on group create. |
| PANEL-052 | Missing | — | Drag an action/group → drop indicator + order updates; move action between groups; built-in items not draggable. |
| PANEL-056 | Partial | test_file_browser.py::test_split_view_toggle_persists_across_panel_reopen; ::test_line_wrap_toggle_persists_across_panel_reopen; test_panel_zones.py::test_inner_vertical_split_height_persists_after_navigation | Assert folder-expansion, scroll position, active-tab, view-mode (tree/flat), and diff-scope restored after switching tabs/files and returning. |
| PANEL-057 | Partial | test_bundled_linear_plugin.py::test_bundled_linear_plugin_loads_and_renders | Assert the plugin-contributed panel is listed with a "plugin" badge in the Panels list (not just that it renders). |

### CMDP

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| CMDP-001 | Partial | test_command_palette.py::test_open_command_palette_via_sidebar_cmdk_link; ::test_open_command_palette_via_keyboard_shortcut (palette visible + input focused only) | Assert group headers render in spec order (Workspaces → Navigation → Theme & Layout → Chat → Terminal → Help) with the first row selected on open. |
| CMDP-002 | Missing | — | Press Cmd+P; assert the palette opens on the "Go to workspace" sub-page (breadcrumb + "Find a workspace…" placeholder). |
| CMDP-003 | Missing | — | Open via Cmd+K, press Cmd+K again; assert the palette closes and no command ran. |
| CMDP-005 | Partial | test_command_palette.py::test_command_palette_filters_on_input (empty-state element only) | Assert the exact `No matches for '{query}'` copy including the typed query string. |
| CMDP-006 | Missing | — (test_command_palette_filters_on_input clears search with no post-assert) | Clear input; assert all commands reappear in group order with the first row re-selected. |
| CMDP-007 | Partial | test_command_palette.py::test_command_palette_escape_closes (empty-root close only) | Add: (a) non-empty search: Escape clears search first, second Escape closes; (b) sub-page: Escape returns to root without closing. |
| CMDP-008 | Missing | — | Open palette (no pending command), click the overlay/backdrop; assert the palette closes. |
| CMDP-009 | Missing | — | Press Down/Up; assert selection moves, scrolls into view, and wraps at both ends. |
| CMDP-013 | Partial | test_command_palette.py::test_command_palette_subpage_push_pop (breadcrumb visible/absent only) | Assert the breadcrumb shows the page title and its X control returns to root. |
| CMDP-014 | Missing | — | Surface a context-disabled command; assert the row is greyed out and shows its reason as subtitle/tooltip. |
| CMDP-015 | Missing | — | Assert the trailing area shows a kbd-badge shortcut / right chevron on page-openers / group label during search per case. |
| CMDP-016 | Missing | — | Run an async command; assert the row shows a spinner and the palette refuses to close until it completes. |
| CMDP-017 | Partial | test_command_palette.py::test_command_palette_navigates_to_settings; ::test_command_palette_creates_new_agent | Add Open home navigates home, New workspace opens add-workspace, and assert New agent disabled/hidden off a workspace. |
| CMDP-018 | Partial | test_command_palette.py::test_command_palette_keep_open_command (runs theme.toggle but does NOT assert the appearance changed); ::test_command_palette_subpage_push_pop | Assert running a theme command actually changes the applied appearance. |
| CMDP-019 | Missing | — | On a workspace, run panel/mode toggles; assert the panel/mode visibly toggled (focus/zen close palette; zone toggles keep it open). |
| CMDP-020 | Missing | — | On a chat workspace: focus input / open chat search / jump-to-bottom / tool-density toggle with visible outcomes; chat commands hidden without a chat panel. |
| CMDP-021 | Partial | test_command_palette.py::test_command_palette_report_problem_opens_popover | Add Clear terminal clears the active terminal; Show keyboard shortcuts opens the dialog; terminal command hidden without a terminal panel. |
| CMDP-022 | Missing | — | With 2+ workspaces, open "Go to workspace…"; assert status dots + current disabled; select another to navigate. |
| CMDP-023 | Missing | — | With 2+ tabs, run Next/Previous workspace tab; assert the active tab changes. |
| CMDP-024 | Missing | — | Open "Workspace actions…"; assert the labeled actions list; run one (e.g. Rename) end-to-end. |
| CMDP-025 | Missing | — | On a local backend, open "Open in…"; assert ordering (preferred first) + a disabled-on-remote case + an app launching. |
| CMDP-026 | Missing | — | In a multi-agent workspace, open "Go to agent…"; assert current disabled; select another to navigate; opener disabled with one agent. |
| CMDP-027 | Missing | — | Open "Agent actions…" and run each (rename dialog / marked unread / delete confirmation) from the palette. |
| CMDP-028 | Partial | test_command_palette.py::test_command_palette_cross_page_reveal_finds_subpage_item (visibility only) | Open "Go to settings…", select a section (e.g. Keybindings); assert that section is shown. |
| CMDP-029 | Missing | — | Under real pointer events, assert the first pointer move is ignored (keyboard selection stays) and a subsequent hover selects the hovered row. |
| CMDP-030 | Partial | test_command_palette.py::test_command_palette_top_result_is_not_scrolled_past; ::test_command_palette_list_does_not_animate_scrolls | Assert the list scroll position resets to top on each open and the first row is selected. |
| CMDP-031 | Missing | — | Render a very long agent/workspace title in the palette; assert it truncates with "…". |

### SET / DEV

| Scenario | Status | Existing integration test(s) | Integration tests to add |
|----------|--------|------------------------------|--------------------------|
| SET-001 | Partial | test_settings_tab.py::test_settings_opens_as_tab; piecemeal section-clicks across test_settings_integration.py, test_agent_settings.py, test_keybindings.py, test_panels_settings.py, test_claude_binary_installation.py, test_pi_managed_install.py, test_telemetry_opt_out.py, test_theme_builder.py, test_custom_actions.py | One nav test clicking every sidebar item (all 15 sections) asserting active content; cover the mobile dropdown; CI, File Browser, Git, Env-Vars, Experimental are never opened-and-asserted as a nav target. |
| SET-002 | Missing | — | Load `/#/settings?section=<x>` and assert it opens directly to that section. |
| SET-003 | Missing | — | View a non-default section, reopen Settings; assert the last-viewed section is restored. |
| SET-004 | Partial | test_settings_integration.py::test_env_vars_override_toggle_saves_setting; test_agent_settings.py; test_keybindings.py; test_custom_actions.py (success toast broadly) | Assert the "Failed to update setting" error-toast path (induce a save failure). |
| SET-005 | Missing | — | In General, pick Light/Dark/System; assert app appearance changes immediately. |
| SET-006 | Partial | test_auto_update_browser.py::test_channel_switch_calls_ipc_and_shows_pending; ::test_check_for_updates_button; ::test_disabled_status_grays_out_settings_controls; test_auto_update_electron.py::test_channel_switch_stable_to_rc; test_auto_update_disabled_electron.py | Assert the channel-change confirmation toast and the "Install and restart"/"Restarting…" button state from within General. |
| SET-012 | Partial | test_panels_settings.py::test_zone_select_moves_panel; ::test_diagram_drag_moves_panel; ::test_shortcut_round_trip_panels_to_keybindings; ::test_disabled_panel_shortcut_is_inert | Assert panel-hotkey conflict checking; assert the zone select disabled where rules/enabled-state prevent it. |
| SET-015 | Partial | test_claude_binary_installation.py::test_settings_install_managed_binary; ::test_onboarding_claude_override_invalid_path | Add a Settings-page custom-path entry + Apply + active-path display test; assert the running progress-bar UI. |
| SET-018 | Partial | test_pi_managed_install.py::test_pi_settings_managed_shows_managed_controls_and_no_manual_install; ::test_pi_settings_custom_shows_binary_path_and_manual_install; ::test_pi_settings_install_button_invokes_managed_install_and_surfaces_error | Assert install progress bar; distinct status states (outside-pinned/not-installed/no-path); detected-vs-pinned version rows; custom-path Apply + active-path. |
| SET-019 | Missing | — | In Pi section, add an API-key env-var name then remove it; assert list updates + "Setting updated" toast. |
| SET-020 | Partial | test_multi_repo.py::test_create_workspaces_in_multiple_projects_and_switch; test_regression_settings_delete_repo_stays_on_page.py | Assert per-repo path, agent count, and the accessibility/missing-path warning. |
| SET-021 | Partial | test_workspace_setup_command.py::test_setup_command_input_visible_in_settings; ::test_setup_command_saves_on_blur; ::test_setup_edit_button_deep_links_to_focused_textarea; test_regression_setup_command_backfill.py | Cover the branch-naming pattern field and the setup-command "Using default"/"Reset to default" affordances. |
| SET-022 | Partial | test_delete_last_repo.py::test_deleting_last_repo_shows_onboarding_add_repo_step; test_regression_settings_delete_repo_stays_on_page.py::test_deleting_repo_stays_on_settings_page | Assert the confirmation dialog showing the agent count and the success/error toast on remove. |
| SET-023 | Missing | — (no Git-settings UI test) | Edit PR-creation prompt (+reset), toggle PR polling (dependent fields disable), poll-interval 10–300s validation, closed-workspace multiplier 1–120× validation, default target branch — each with save toast. |
| SET-024 | Missing | — | Edit default branch-naming pattern (toast); set branch-deletion policy Never / Delete-if-safe / Always (toast). |
| SET-025 | Missing | — (test_ci_babysitter.py configures via API, not the Settings UI) | Toggle babysitter, retry-cap 1–10 validation, edit pipeline-failed & merge-conflict prompts (+reset), dependent fields disable when off, save toast. |
| SET-026 | Missing | — | Split-ratio 20–80%, tab-close behavior, line-wrapping, default diff view, commit prompt (+reset) — each with save toast. |
| SET-027 | Partial | test_settings_integration.py::test_env_vars_section_shows_setup_instructions; ::test_env_vars_override_toggle_saves_setting; ::test_env_vars_loaded_names_shows_no_vars_without_env_file; test_project_env_vars.py::test_env_var_names_shown_in_settings | Cover the refresh button and the global-vs-repo-specific grouping of the loaded list. |
| SET-029 | Partial | test_settings_integration.py::test_settings_experimental_has_review_all_toggle; ::test_enable_review_all_via_settings_shows_button (Review All only) | Toggle the other 8 experimental switches via UI and assert the "Setting updated" toast for each. |
| SET-030 | Missing | — | Set custom backend command and readiness timeout in Experimental/Advanced; assert the "restart required" toast. |
| SET-031 | Partial | test_custom_actions.py::test_create_action_from_settings; ::test_edit_action_from_settings; ::test_delete_action_from_settings; ::test_create_group_from_settings; ::test_delete_group_deletes_actions_from_settings; ::test_builtin_chips | Cover Export ("sculptor-actions.json" download, disabled-when-empty) and Import (file picker, validate+merge+count toast). |
| SET-032 | Partial | test_custom_actions.py::test_create_action_from_settings; ::test_edit_action_from_settings | Assert Save disabled until valid, Cmd+Enter submits, and the Auto-submit toggle behavior within the dialog. |
| SET-033 | Partial | test_custom_actions.py::test_create_group_from_settings; ::test_delete_group_deletes_actions_from_settings | Assert drag-to-reorder and inline group rename + success toast. |
| SET-034 | Partial | test_theme_builder.py::test_theme_builder_navigation; ::test_theme_builder_change_accent_color | Exercise changing appearance mode, primary font, code font, and code theme and verify the UI updates. |
| SET-035 | Partial | test_theme_builder.py::test_theme_builder_change_accent_color; ::test_theme_builder_reset_to_defaults | Cover custom hex entry, the light/dark hex override toggle, invalid-hex-shown-red, and the Gray/Success/Warning/Info swatches. |
| SET-036 | Missing | — | Click a radius / scaling / panel-background option and assert the live UI updates. |
| SET-038 | Partial | test_plugin_loader.py::test_valid_plugin_loads_and_can_be_removed; ::test_plugin_source_can_be_disabled_and_re_enabled | Cover the Refresh rescan of the plugins directory and the displayed directory path. |
| SET-039 | Partial | test_ci_babysitter.py::test_settings_selector_lists_only_driveable_harnesses | Assert the selector saves with a toast and is disabled when the babysitter is off. |
| SET-040 | Complete | test_plugins_settings_visibility.py::test_plugins_section_present_and_on_by_default; ::test_global_toggle_hides_management_ui_live | — |
| SET-041 | Complete | test_plugin_loader.py::test_failed_plugin_can_be_retried | — |
| DEV-001 | Partial | test_tanstack_devtools_panel.py::test_tanstack_devtools_panel_mounts_with_content (panel mounts only) | Cover header Dock/Float/Close controls, floating drag + resize within viewport, docked resize-from-top-edge + pushes content up, and closing hides it. |

---

## Complete coverage

Every scenario an integration test fully covers — it performs the user action *and* asserts the user-visible outcome — with the test(s) that cover it. Partial and Missing scenarios are in the gaps section above, not here.

### SHELL / ROUTE / HELP

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| SHELL-001 | test_workspace_tab_enhancements.py::test_cmd_t_opens_new_workspace_page |
| SHELL-003 | test_settings_tab.py::test_settings_opens_as_tab |
| SHELL-007 | test_workspace_tab_enhancements.py::test_new_workspace_tab_x_navigates_to_mru_workspace; test_home_page_tab.py::test_home_tab_is_closeable |
| SHELL-009 | test_workspace_tab_enhancements.py::test_cmd_w_closes_workspace_tab_without_deletion; ::test_cmd_w_on_new_workspace_page_navigates_to_mru_workspace |
| SHELL-016 | test_workspace_tab_context_menu_icons.py::test_workspace_context_menu_rename; ::test_workspace_context_menu_rename_escape_cancels |
| SHELL-017 | test_workspace_tab_enhancements.py::test_context_menu_delete_removes_workspace |
| SHELL-020 | test_closed_workspaces_dropdown.py::test_pill_visibility_toggles_with_closed_workspace_count |
| SHELL-021 | test_closed_workspaces_dropdown.py::test_dropdown_opens_and_shows_closed_workspace_rows |
| SHELL-022 | test_closed_workspaces_dropdown.py::test_reopen_workspace_from_dropdown |
| SHELL-023 | test_closed_workspaces_dropdown.py::test_open_all_reopens_all_closed_workspaces |
| SHELL-024 | test_closed_workspaces_dropdown.py::test_delete_workspace_from_dropdown |
| SHELL-025 | test_command_palette.py::test_open_command_palette_via_sidebar_cmdk_link |
| SHELL-028 | test_zen_mode.py::test_zen_mode_hides_chrome_and_panels |
| SHELL-029 | test_zen_mode.py::test_exit_zen_mode_button_works |
| SHELL-030 | test_zen_mode.py::test_workspace_tab_navigation_works_in_zen_mode |
| SHELL-031 | test_zen_mode.py::test_focus_mode_hides_panels_but_keeps_chrome |
| SHELL-032 | test_zen_mode.py::test_panel_toggle_in_zen_mode_persists_on_exit; test_panels_settings.py::test_regression_focus_mode_toggle |
| SHELL-036 | test_auto_update_browser.py::test_update_dot_appears_when_ready; ::test_update_dot_appears_when_downloading |
| SHELL-037 | test_auto_update_browser.py::test_downloading_status_shows_progress |
| SHELL-039 | test_auto_update_browser.py::test_error_status_shows_error |
| SHELL-040 | test_auto_update_browser.py::test_dismissed_download_toast_stays_dismissed |
| SHELL-046 | test_backend_shutdown_stall.py::test_shutdown_stall_recovery_after_timeout; ::test_shutdown_spinner_remains_before_timeout |
| SHELL-049 | test_workspace_diagnostics_context_menu.py::test_workspace_context_menu_copy_name_branch_id |
| SHELL-050 | test_workspace_close_vs_delete.py::test_cmd_shift_w_deletes_active_workspace |
| ROUTE-001 | test_restart_mru.py::test_restart_restores_active_workspace_and_agent; ::test_restart_with_no_mru_lands_on_new |

### HOME / ADDWS / ADDREPO

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| HOME-002 | test_home_page.py::test_empty_state_shown_for_new_user |
| HOME-013 | test_home_page.py::test_clicking_workspace_row_navigates_to_workspace; test_home_page_tab.py::test_clicking_workspace_replaces_home_tab |
| ADDWS-005 | test_add_workspace_page.py::test_workspace_form_draft_persists_after_navigation; ::test_multiple_new_workspace_tabs_with_independent_drafts |
| ADDWS-013 | test_worktree_create_happy_path.py::test_worktree_create_with_default_branch_name |
| ADDWS-015 | test_branch_name_collisions.py::test_worktree_mode_collision_blocks_creation; ::test_clone_mode_collision_blocks_creation |
| ADDWS-016 | test_add_workspace_agent_type.py::test_agent_type_select_visible_with_claude_default; ::test_pi_option_gated_behind_pi_agent_flag; test_agent_type_menu.py::test_registered_terminal_agent_appears_in_menu_and_creates |
| ADDWS-017 | test_add_workspace_agent_type.py::test_first_agent_type_defaults_to_shared_last_used; test_agent_type_menu.py::test_agent_type_menu_creates_terminal_agent_and_remembers_type |
| ADDWS-021 | test_worktree_create_happy_path.py::test_worktree_create_with_default_branch_name; test_add_workspace_agent_type.py::test_cmd_enter_in_workspace_name_creates_workspace |
| ADDWS-022 | test_add_workspace_page.py::test_arrow_down_focuses_name_input_when_nothing_focused; ::test_arrow_up_focuses_name_input_when_nothing_focused |
| ADDWS-025 | test_add_workspace_page.py::test_workspace_form_branch_state_persists_after_navigation |
| ADDREPO-007 | test_path_autocomplete_keyboard.py::test_enter_on_directory_highlights_first_subentry; ::test_selected_folder_submit_shows_correct_repo_name |
| ADDREPO-009 | test_add_repo_remote_picker.py::test_github_picker_happy_path_clones_and_adds_project |
| ADDREPO-010 | test_add_repo_remote_clone.py::test_add_repo_remote_clone_via_url_fallback; test_add_repo_remote_clone_errors.py::test_url_view_derives_name_from_url; ::test_url_view_ssh_url_clones_with_https_link_in_progress_view |
| ADDREPO-011 | test_add_repo_not_configured.py::test_not_configured_shows_configure_cta |
| ADDREPO-012 | test_add_repo_remote_clone_errors.py::test_url_view_ssh_url_clones_with_https_link_in_progress_view; ::test_clone_504_shows_timeout_message |
| ADDREPO-013 | test_add_repo_remote_clone_errors.py::test_clone_409_offers_add_as_local_cta; ::test_clone_412_does_not_offer_add_as_local_cta |

### ONB / MENT / SKILL / ACT

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| ONB-002 | test_onboarding.py::test_back_navigation_preserves_email |
| ONB-008 | test_onboarding.py::test_invalid_email_surfaces_validation_error |
| ONB-009 | test_telemetry_opt_out.py::test_onboarding_skip_account_setup |
| ONB-013 | test_onboarding.py::test_onboarding_without_git_installed; test_claude_binary_installation.py::test_onboarding_claude_not_found_shows_override |
| ONB-014 | test_onboarding.py::test_dependency_path_and_version_display |
| ONB-016 | test_onboarding.py::test_claude_not_authenticated |
| ONB-022 | test_onboarding.py::test_invalid_override_path_shows_error; test_claude_binary_installation.py::test_onboarding_claude_override_invalid_path |
| ONB-024 | test_onboarding.py::test_onboarding_without_git_installed / test_onboarding_without_claude_installed; ::test_installation_step_skips_add_repo_when_project_exists |
| ONB-026 | test_onboarding.py::test_full_onboarding_flow; ::test_installation_step_skips_add_repo_when_project_exists |
| ONB-030 | test_onboarding.py::test_full_onboarding_flow |
| ONB-034 | test_claude_auth_paste_code.py::test_claude_paste_code_sign_in_succeeds; ::test_claude_paste_code_invalid_code_shows_error |
| MENT-005 | test_mention_picker_completion.py::test_plus_opens_prefilter_picker; ::test_plus_filters_categories_by_query; ::test_plus_drill_into_files/skills/workspaces/repositories_via_enter; ::test_mention_toolbar_button_opens_picker |
| MENT-006 | test_at_mention_completion.py; test_at_mention_keyboard_navigation.py; test_at_mention_tab_drill_and_shift_tab.py; test_at_mention_path_mode.py |
| MENT-007 | test_skill_autocomplete.py; test_pseudo_skills.py; test_slash_command_enter_accepts_suggestion.py; test_mention_picker_completion.py::test_plus_drill_into_skills_via_enter |
| MENT-008 | test_entity_picker_workspace_drill.py::test_tab_on_workspace_drills_into_agent_list; ::test_click_on_workspace_drills_into_agent_list; ::test_shift_tab_steps_back_from_workspace_drill; ::test_enter_on_agent_after_drill_commits_agent_chip |
| MENT-010 | test_path_autocomplete_keyboard.py::test_enter_on_directory_highlights_first_subentry; ::test_cmd_enter_submits_path; ::test_selected_folder_submit_shows_correct_repo_name; ::test_autocomplete_shows_submit_hint; test_files_panel.py::test_path_autocomplete_shows_tilde_for_home_directory |
| SKILL-001 | test_skills_panel.py::test_skills_panel_click_inserts_mention_chip; ::test_skills_panel_lists_workspace_skill; ::test_skills_panel_keyboard_navigation_inserts_chip; test_skill_without_frontmatter.py |
| SKILL-003 | test_skills_panel.py::test_skills_panel_search_filters_list; ::test_skills_panel_keyboard_navigation_inserts_chip; test_skill_autocomplete.py; test_pseudo_skills.py::test_autocomplete_filters_pseudo_skills |
| ACT-001 | test_custom_actions.py::test_draft_action_populates_and_focuses_chat_input; ::test_builtin_chips; ::test_create_action_from_panel; test_terminal_agent_automated_prompts.py (terminal-agent draft types into the PTY without submitting) |
| ACT-004 | test_custom_actions.py::test_delete_action_from_settings; ::test_delete_group_deletes_actions_from_settings; ::test_delete_group_deletes_actions_from_panel |

### WS

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| WS-003 | test_queued_messages.py::test_keyboard_shortcut_interrupt_and_send_queued_message; test_interrupt_and_continue.py::test_interrupt_and_continue |
| WS-004 | test_chat_input_send_error.py::test_send_error_surfaces_attribute_and_toast_without_clearing_editor |
| WS-006 | test_image_upload.py::test_image_upload_from_chat_input |
| WS-007 | test_image_upload.py::test_remove_attached_image; test_image_thumbnail_strip.py::test_thumbnail_click_opens_lightbox |
| WS-008 | test_at_mention_completion.py::test_at_mention_opens_suggestion_popup |
| WS-010 | test_agent_settings.py::test_effort_level_persists_without_sending_message; ::test_effort_level_persists_across_workspace_switches |
| WS-011 | test_fast_mode_persistence.py::test_fast_mode_persists_after_sending_message_and_switching_agents |
| WS-012 | test_plan_mode.py::test_plan_first_toggle_activates_and_deactivates; ::test_plan_first_toggle_persists_after_send |
| WS-014 | test_pseudo_skills.py::test_clear_pseudo_skill_clears_context |
| WS-015 | test_pseudo_skills.py::test_copy_pseudo_skill_shows_toast |
| WS-016 | test_btw.py::test_btw_happy_path_while_main_busy; ::test_btw_first_message_shows_unavailable_toast |
| WS-017 | test_queued_messages.py::test_queued_message_bar_appears_and_shows_content |
| WS-018 | test_queued_messages.py::test_cancel_queued_message |
| WS-019 | test_queued_messages.py::test_edit_queued_message_into_empty_editor |
| WS-020 | test_queued_messages.py::test_edit_dialog_overwrite_replaces_editor_content; ::test_edit_dialog_remove_discards_queued_message; ::test_edit_dialog_cancel_requeues_message |
| WS-021 | test_queued_messages.py::test_interrupt_and_send_queued_message; test_regression_queued_messages_after_restart.py::test_queued_message_dispatched_after_graceful_restart |
| WS-028 | test_ci_babysitter.py::test_scenario_4_pause_toggle_prevents_prompt; ::test_pause_state_persists_across_restart |
| WS-036 | test_workspace_banner.py::test_repo_segment_shows_mode_label |
| WS-037 | test_zen_mode.py::test_zen_mode_hides_chrome_and_panels; ::test_focus_mode_hides_panels_but_keeps_chrome |
| WS-040 | test_workspace_banner.py::test_banner_shows_diff_stats; ::test_banner_click_navigates_to_changes_all |
| WS-041 | test_multi_agent_workspace.py::test_multiple_agent_tabs_shown_for_shared_workspace; ::test_single_agent_shows_one_agent_tab |
| WS-044 | test_multi_agent_workspace.py::test_create_second_agent_in_existing_workspace |
| WS-045 | test_agent_type_menu.py::test_agent_type_menu_creates_terminal_agent_and_remembers_type; ::test_agent_type_menu_gates_pi_behind_pi_agent_flag; ::test_registered_terminal_agent_appears_in_menu_and_creates |
| WS-047 | test_agent_tab_context_menu.py::test_agent_context_menu_has_rename_and_delete; test_agent_diagnostics_context_menu.py::test_agent_diagnostics_disabled_without_session; ::test_agent_diagnostics_copy_session_id_and_transcript_path; ::test_agent_context_menu_copy_name_and_id |
| WS-048 | test_agent_tab_context_menu.py::test_agent_context_menu_delete; test_multi_agent_workspace.py::test_workspace_survives_when_other_agents_remain |
| WS-049 | test_mark_unread.py::test_mark_adjacent_tab_unread; test_read_unread_status.py::test_unread_indicator_when_switching_agents_within_workspace |
| WS-051 | test_terminal_agent_basic.py::test_terminal_agent_basic |
| WS-052 | test_terminal_agent_basic.py::test_terminal_agent_basic (switch away/back, scrollback restored); test_terminal_tab_enhancements.py::test_terminal_compact_layout_no_heading |
| WS-079 | test_terminal_agent_focus.py::test_terminal_agent_tab_switch_focuses_terminal |
| WS-053 | test_ask_user_question.py::test_ask_user_question_full_flow; test_alpha_ask_user_question.py::test_alpha_auq_pill_shows_answered_summary |
| WS-054 | test_ask_user_question.py::test_ask_user_question_full_flow |
| WS-055 | test_ask_user_question.py::test_ask_user_question_multiselect |
| WS-056 | test_ask_user_question.py::test_ask_user_question_other_option; ::test_ask_user_question_multiselect_with_other |
| WS-058 | test_ask_user_question.py::test_ask_user_question_next_button; ::test_ask_user_question_dismiss; test_ask_user_question_continue.py::test_ask_user_question_and_continue |
| WS-059 | test_error_states.py::test_crash_puts_task_in_error_state |
| WS-066 | test_side_toggle.py::test_right_side_toggle_hides_and_shows_panels; ::test_bottom_toggle_hides_and_shows_terminal |
| WS-070 | test_chat_search_bar.py::test_cmd_f_enter_advances_through_all_matches |
| WS-074 | test_workspace_setup_command.py::test_setup_config_prompt_deep_links_to_focused_textarea; test_regression_setup_command_backfill.py; test_regression_setup_command_rerun.py::test_setup_rerun_button_runs_command_again |
| WS-075 | test_btw.py::test_btw_happy_path_while_main_busy |
| WS-076 | test_btw.py::test_btw_popup_is_draggable; ::test_btw_popup_closes_on_escape; ::test_btw_empty_shows_inline_toast |
| WS-078 | test_pr_management.py::test_banner_target_branch_lists_local_branches_when_no_remote |

### CHAT

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| CHAT-004 | test_workspace_setup_status.py::test_setup_card_shows_succeeded / ::test_setup_card_shows_failed / ::test_setup_rerun_replays_command / ::test_setup_cancel_stops_running_command / ::test_setup_truncation_banner / ::test_setup_run_button_appears_when_command_added_after_creation |
| CHAT-005 | test_status_pill.py::test_status_pill_disappears_after_completion |
| CHAT-008 | test_status_pill_tasks_widget.py::test_status_pill_shows_count_summary_after_turn; ::test_count_summary_updates_on_follow_up |
| CHAT-010 | test_status_pill_tasks_widget.py::test_hover_opens_tasks_popover / ::test_click_pins_tasks_popover / ::test_outside_click_closes_pinned_popover / ::test_graph_toggle_opens_and_closes_graph |
| CHAT-011 | test_status_pill_tasks_widget.py::test_empty_state_popover_before_tasks_arrive |
| CHAT-014 | test_status_pill_tasks_widget.py::test_non_linear_shows_waiting_badge_and_toggle; ::test_large_dag_scale_rules |
| CHAT-016 | test_status_pill_tasks_widget.py::test_row_click_expands_inline_detail |
| CHAT-019 | test_chat_search_bar.py::test_cmd_f_enter_advances_through_all_matches; test_alpha_scroll_search.py::test_alpha_search_flow |
| CHAT-023 | test_alpha_scroll_to_top.py::test_filling_to_pin_transition |
| CHAT-025 | test_alpha_scroll_auto_scroll.py::test_auto_scroll_and_jump_to_bottom |
| CHAT-026 | test_alpha_scroll_behaviors.py::test_jump_button_appears_and_works; test_alpha_scroll_auto_scroll.py::test_auto_scroll_and_jump_to_bottom |
| CHAT-027 | test_alpha_scroll_auto_scroll.py::test_user_can_scroll_during_streaming; test_alpha_scroll_to_top.py::test_reengagement_after_scroll_to_top |
| CHAT-028 | test_alpha_scroll_task_switch.py::test_scroll_position_restored_on_task_switch |
| CHAT-030 | test_alpha_prompt_navigator_interactions.py::test_dot_rail_shows_one_dot_per_user_prompt |
| CHAT-031 | test_alpha_prompt_navigator_interactions.py::test_clicking_dot_scrolls_and_highlights_prompt; ::test_active_dot_tracks_scroll_position; ::test_arrow_keys_continue_after_dot_click |
| CHAT-032 | test_alpha_prompt_navigator_interactions.py::test_hovering_dot_shows_popover; ::test_popover_swaps_content_between_dots; ::test_popover_contains_copy_button_and_prompt_label |
| CHAT-034 | test_alpha_prompt_navigator_interactions.py::test_popover_copy_button_copies_and_flips_icon; ::test_right_click_dot_opens_copy_context_menu |
| CHAT-035 | test_alpha_chat_subagent.py::test_background_subagent_launch_ack_not_visible |
| CHAT-036 | test_alpha_chat_subagent.py::test_background_subagent_launch_ack_not_visible; ::test_subagent_tool_result_not_visible |
| CHAT-041 | test_turn_footer_interactions.py::test_file_click_in_popover_opens_diff_panel |
| CHAT-042 | test_alpha_ask_user_question.py::test_alpha_auq_pill_shows_answered_summary; ::test_alpha_auq_comma_in_option_label |

### MSG

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| MSG-001 | test_alpha_chat_mixed_tools.py::test_mixed_write_bash_read_renders_all_types; ::test_text_and_tools_coexist; ::test_bash_with_error_and_write_coexist; test_alpha_chat_view.py::test_alpha_view_displays_tool_calls |
| MSG-002 | test_alpha_streaming_cursor.py::test_streaming_cursor_visible_during_streaming; ::test_streaming_cursor_hidden_after_completion; ::test_streaming_cursor_visible_during_tool_then_text; ::test_streaming_cursor_absent_after_multiple_turns |
| MSG-007 | test_markdown_gfm.py::test_markdown_renders_gfm_and_neutralises_unsafe (external anchors target=_blank + rel) |
| MSG-008 | test_markdown_gfm.py::test_markdown_renders_gfm_and_neutralises_unsafe (images suppressed) |
| MSG-009 | test_alpha_chat_view.py::test_alpha_file_path_link |
| MSG-014 | test_alpha_chat_table_wrap_toggle.py::test_table_wrap_toggle_is_per_table_and_does_not_scroll_chat |
| MSG-019 | test_alpha_tool_pill_pin.py::test_click_pins_popover_open; ::test_click_pinned_pill_again_closes; ::test_escape_closes_pinned_popover; test_alpha_tool_pill_hover.py::test_hover_opens_pill_popover; ::test_hover_leave_closes_popover |
| MSG-020 | test_alpha_tool_pill_keyboard.py::test_arrow_keys_move_open_popover_within_row; ::test_escape_closes_popover_and_restores_focus; ::test_enter_on_focused_pill_opens_popover |
| MSG-021 | test_alpha_chat_tool_density.py::test_toggle_to_expanded_density_stacks_rows; ::test_density_persists_across_reload; ::test_default_density_renders_pills_inline |
| MSG-023 | test_alpha_chat_bash_block.py::test_bash_block_expands_on_click; ::test_bash_description_persists_after_completion; test_alpha_chat_bash_block_advanced.py::test_bash_block_shows_command_text; ::test_bash_block_output_contains_stdout; ::test_bash_block_error_shows_output_on_click |
| MSG-026 | test_alpha_chat_chip_row.py::test_chip_row_renders_for_write_tool; test_alpha_chat_chip_row_advanced.py::test_chip_row_renders_for_edit_tool; ::test_view_full_diff_for_multi_edit_file_shows_correct_line_count |
| MSG-028 | test_alpha_chat_chip_row.py::test_chip_popover_opens_on_click; ::test_chip_popover_closes_on_second_click; ::test_chip_popover_swaps_on_different_chip_click; test_alpha_chat_chip_row_advanced.py::test_chip_popover_shows_diff_content; ::test_chip_row_hover_opens_popover |
| MSG-030 | test_missing_claude_binary.py::test_missing_claude_binary_shows_friendly_error; test_claude_binary_installation.py::test_settings_claude_cli_section_visible; ::test_onboarding_claude_not_found_shows_override |
| MSG-034 | test_plan_mode.py::test_exit_plan_mode_shows_approval_prompt; ::test_exit_plan_mode_revision_flow; ::test_exit_plan_mode_revision_auto_expands; test_alpha_chat_view.py::test_alpha_exit_plan_mode_approve |
| MSG-037 | test_copy_image_context_menu.py::test_copy_image_context_menu_scoped_to_chat_content |

### PANEL

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| PANEL-001 | test_file_browser.py::test_filter_tabs_switch_between_all_and_changes; ::test_changes_tab_shows_count; test_file_browser_tabs.py::test_tab_switching_shows_correct_content |
| PANEL-002 | test_file_browser.py::test_review_all_button_opens_combined_diff; ::test_review_all_shows_all_branch_files; test_review_all_visibility.py::test_review_all_visible_with_uncommitted_changes |
| PANEL-004 | test_file_browser.py::test_collapse_all_folders_button; ::test_collapse_all_changes_folders_button; ::test_collapse_all_commits_button |
| PANEL-006 | test_file_browser.py::test_file_search; ::test_file_search_filters_visible_rows; ::test_file_search_escape_closes; ::test_file_search_no_matches_shows_empty_state; ::test_file_search_folders_are_collapsible |
| PANEL-007 | test_file_browser.py::test_folder_expand_and_collapse; ::test_collapse_all_folders_button |
| PANEL-008 | test_file_browser.py::test_click_file_opens_diff_panel; ::test_changes_tab_click_opens_diff; test_file_open_diff_modes.py::test_browse_tab_opens_file_view |
| PANEL-014 | test_changes_panel.py::test_scope_switch_toggles_active_scope; test_file_open_diff_modes.py::test_committed_file_visible_in_all_scope_only; test_file_browser_tabs.py::test_tab_switching_shows_correct_content |
| PANEL-015 | test_changes_panel.py::test_discard_file_removes_from_changes; ::test_discard_cancel_preserves_file; test_discard_preserves_all_tab.py::test_discard_last_uncommitted_keeps_all_tab_populated |
| PANEL-017 | test_changes_panel.py::test_commit_button_sends_commit_message |
| PANEL-020 | test_commits_panel.py::test_commit_entry_shows_metadata_line; ::test_merge_commit_shows_spur |
| PANEL-021 | test_file_browser.py::test_collapse_all_commits_button; test_commits_panel.py::test_click_file_in_multi_file_commit; ::test_switch_files_within_same_commit |
| PANEL-023 | test_commits_panel.py::test_commit_diff_shows_committed_content_not_uncommitted; ::test_commit_diff_file_header_shows_line_counts; ::test_same_file_two_commits_shows_correct_content |
| PANEL-024 | test_commits_panel.py::test_merge_commit_shows_spur; ::test_terminus_shows_fork_point_hash; ::test_terminus_visible_with_no_commits |
| PANEL-031 | test_file_open_diff_modes.py::test_browse_tab_opens_file_view; test_sculpt_ui_open_file.py::test_mode_file_opens_file_view_tab; test_diff_viewer.py::test_open_created_file_in_diff_viewer |
| PANEL-032 | test_auto_collapse_combined_diff.py::test_many_files_start_collapsed_in_review_all; ::test_few_files_start_expanded_in_review_all; test_file_browser.py::test_review_all_button_opens_combined_diff |
| PANEL-033 | test_diff_viewer.py::test_markdown_toggle_switches_views; ::test_markdown_toggle_hidden_for_non_markdown_files; ::test_markdown_toggle_disabled_when_flag_off |
| PANEL-034 | test_terminal.py::test_add_terminal_tab_creates_new_session; ::test_close_terminal_tab_switches_to_neighbor; ::test_terminal_tab_reuses_lowest_available_number; test_terminal_tab_enhancements.py::test_terminal_tab_double_click_rename; ::test_terminal_context_menu_has_close_all_and_rename |
| PANEL-035 | test_terminal.py::test_opt_left_moves_cursor_back_by_word; ::test_ctrl_c_cancels_input; ::test_ctrl_d_shows_process_exited_message; test_terminal_agent_basic.py::test_terminal_agent_basic |
| PANEL-043 | test_skills_panel.py::test_skills_panel_click_inserts_mention_chip |
| PANEL-050 | test_custom_actions.py::test_create_action_from_panel; ::test_edit_action_from_settings; ::test_delete_action_from_settings; ::test_builtin_chips |
| PANEL-053 | test_browser_panel.py::test_browser_panel_navigation_tour; ::test_browser_panel_screenshot; ::test_browser_panel_url_input_polish |
| PANEL-054 | test_browser_panel.py::test_browser_panel_navigation_tour; ::test_browser_panel_url_input_polish |
| PANEL-055 | test_browser_panel.py::test_browser_panel_toggle_shows_and_hides_icon; ::test_browser_panel_electron_mode_hides_web_placeholder |

### CMDP

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| CMDP-004 | test_command_palette.py::test_command_palette_filters_on_input |
| CMDP-010 | test_command_palette.py::test_command_palette_navigates_to_settings |
| CMDP-011 | test_command_palette.py::test_command_palette_cmd_enter_keeps_palette_open |
| CMDP-012 | test_command_palette.py::test_command_palette_subpage_push_pop |

### SET / DEV

| Scenario | Existing integration test(s) |
|----------|------------------------------|
| SET-007 | test_agent_settings.py::test_agent_settings_persist_and_apply_to_new_agents; test_fast_mode_persistence.py; test_model_capability_gating.py |
| SET-008 | test_keybindings.py::test_search_filters_keybindings |
| SET-009 | test_keybindings.py::test_record_new_keybinding; ::test_escape_cancels_recording; ::test_click_outside_cancels_recording; ::test_starting_second_recording_cancels_first |
| SET-010 | test_keybindings.py::test_duplicate_detection_reassign; ::test_duplicate_detection_cancel |
| SET-011 | test_keybindings.py::test_clear_keybinding; ::test_reset_all_to_defaults |
| SET-013 | test_panels_settings.py::test_disable_hides_panel; ::test_reset_to_defaults_preserves_shortcuts |
| SET-014 | test_claude_binary_installation.py::test_settings_claude_cli_section_visible; ::test_settings_mode_selector_persists; ::test_settings_managed_mode_shows_install_button |
| SET-016 | test_claude_binary_installation.py::test_settings_git_section_visible |
| SET-017 | test_pi_managed_install.py::test_pi_settings_section_visible_with_pi_agent_disabled |
| SET-028 | test_telemetry_opt_out.py::test_privacy_settings_telemetry_switch; ::test_onboarding_email_with_telemetry_opt_out; ::test_onboarding_skip_account_setup |
| SET-037 | test_theme_builder.py::test_theme_builder_component_gallery_button; ::test_theme_builder_reset_to_defaults; test_component_gallery_tab.py::test_component_gallery_opens_as_tab |
| DEV-002 | test_diff_viewer.py::test_gfm_features_render_in_read_only_preview (external anchors target=_blank + rel) |
| DEV-003 | test_diff_viewer.py::test_gfm_features_render_in_read_only_preview (fragment anchors inert + "not supported" title) |
| DEV-004 | test_diff_viewer.py::test_gfm_features_render_in_read_only_preview (relative anchors inert + "not supported" title) |

---

## How to use this report

- **Fill Missing first** where the behavior is user-critical and entirely untested by integration
  tests (see "Highest-value gaps" above).
- **Upgrade Partials** by adding the single missing assertion named in the right-hand column — these
  are cheap because a related integration test already drives the relevant state.
- Add new integration tests under `sculptor/tests/integration/frontend/` using the
  `write-integration-test` skill (FakeClaude for deterministic agent behavior). Reach for
  `real_claude`/`real_pi` only when the behavior genuinely needs a live model.
- The command palette (CMDP) is the single biggest integration gap: most commands have no end-to-end
  "ran the command → saw the on-screen result" assertion. A focused pass over `test_command_palette.py`
  that opens each sub-page and asserts the visible outcome would move ~18 scenarios from
  Missing/Partial to Complete.

*Coverage assessed by reading the cited integration tests, not filenames alone. Counts are derived
from the per-area tables; where a single scenario spans multiple controls (notably SET-*), status
reflects the weakest uncovered part.*
