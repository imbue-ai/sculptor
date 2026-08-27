# Sculptor — User-Facing Scenarios

This document enumerates every user-facing interaction and behavior in the Sculptor
frontend, expressed as Given/When/Then scenarios. It is intended as the source of truth
for building a test plan and integration tests that exercise **100% of user-visible
behavior**.

## Conventions

- **Given** = the precondition / app state the user can observe or that is set up before the action.
- **When** = the concrete user action (a click, key press, hover, drag, type, etc.).
- **Then** = the result that is **visible on screen**. Every assertion in a Then must be
  something a person can see in the UI — visible text, an icon, a color/state change, a
  panel appearing/disappearing, navigation, a toast, a tooltip, focus moving, etc. Do **not**
  assert on invisible markers (DOM attributes, atoms, localStorage, network calls) as the
  primary observable; those may be referenced parenthetically as implementation hints only.
- Each scenario has a stable ID (`AREA-NNN`) so tests can reference it.
- Keybindings are written in the macOS form (`Cmd`); the Windows/Linux equivalent is `Ctrl`.

## Areas / ID prefixes

| Prefix | Area |
|--------|------|
| `SHELL` | App shell: tabs, top bar, window controls, zen/focus mode, version, status banners |
| `ROUTE` | Routing, redirects, error/404 pages, startup |
| `HELP` | Keyboard-shortcuts (Help) dialog |
| `HOME` | Home page / recent-workspaces list |
| `ONB` | Onboarding wizard |
| `ADDWS` | Add-workspace page (create workspace form) |
| `ADDREPO` | Add-repository flow and dialogs |
| `WS` | Workspace shell (chat input, banner, PR button, agent tabs, peek, etc.) |
| `CHAT` | Chat-alpha interface, status, search, navigation, subagents, tasks, questions |
| `MSG` | Chat message & tool-content rendering |
| `PANEL` | Workspace side panels (files, changes, history, diff, terminal, notes, skills, actions, browser) |
| `CMDP` | Command palette |
| `SET` | Settings page |
| `ACT` | Actions feature components |
| `SKILL` | Skills UI components |
| `MENT` | Mentions, mention pickers, path autocomplete, mention chips |
| `DEV` | Dev/debug panels and markdown-diff anchors |

---

# SHELL — App shell, tabs & navigation

## Tabs

- **SHELL-001 — Open a new workspace tab**
  - Given: the app is open on any page.
  - When: the user clicks the `+` button at the end of the tab bar, or presses `Cmd+T`.
  - Then: a new "New Workspace" tab appears, becomes active, and the Add Workspace form is shown.

- **SHELL-002 — Open the Home tab**
  - Given: the app is open.
  - When: the user clicks the Home button in the top bar, or presses the Home keybinding.
  - Then: a "Home" tab is shown (created if absent, otherwise re-activated) and the home page is displayed.

- **SHELL-003 — Open the Settings tab**
  - Given: the app is open.
  - When: the user clicks the Settings (gear) button in the top bar, or presses the Settings keybinding.
  - Then: a "Settings" tab is shown and the settings page is displayed.

- **SHELL-004 — Switch tabs by clicking**
  - Given: multiple tabs are open.
  - When: the user clicks a non-active tab.
  - Then: that tab becomes highlighted/active and its content is shown.

- **SHELL-005 — Cycle to next tab**
  - Given: multiple tabs are open.
  - When: the user presses `Cmd+]`.
  - Then: the next tab to the right becomes active, wrapping to the first after the last.

- **SHELL-006 — Cycle to previous tab**
  - Given: multiple tabs are open.
  - When: the user presses `Cmd+[`.
  - Then: the previous tab becomes active, wrapping to the last before the first.

- **SHELL-007 — Close a tab via its X button**
  - Given: a tab is present.
  - When: the user clicks the tab's X (close) button.
  - Then: the tab disappears; an adjacent tab becomes active, or the Add Workspace page is shown if it was the last tab.

- **SHELL-008 — Close a tab via middle-click**
  - Given: multiple tabs are open.
  - When: the user middle-clicks a tab.
  - Then: that tab closes without changing which tab is active (unless the active one was closed).

- **SHELL-009 — Close the current tab via keyboard**
  - Given: a workspace/Home/Settings tab is active.
  - When: the user presses `Cmd+W`.
  - Then: the active tab closes and a remaining tab (or the Add Workspace page) is shown.

- **SHELL-010 — Reorder tabs by dragging**
  - Given: multiple tabs are open.
  - When: the user drags a tab horizontally past another.
  - Then: a drop indicator appears, and on release the tabs reorder; the active tab is unchanged.

- **SHELL-011 — Tab overflow scrolling**
  - Given: more tabs are open than fit in the bar.
  - When: the user scrolls (wheel or trackpad) over the tab bar.
  - Then: the tab strip scrolls horizontally to reveal hidden tabs.

- **SHELL-012 — Active tab auto-scrolls into view**
  - Given: tabs overflow and the active tab is off-screen.
  - When: a tab becomes active (e.g., via keyboard cycle).
  - Then: the strip scrolls so the active tab is visible.

- **SHELL-013 — Tab label truncates**
  - Given: a tab with a long title.
  - When: the tab is rendered at a constrained width.
  - Then: the label is truncated with an ellipsis.

- **SHELL-014 — Workspace tab status dots**
  - Given: a workspace tab whose agents have a status.
  - When: the tab is displayed.
  - Then: status dot(s) appear next to the name (pulsing for running, solid for waiting/ready, red for error, two dots for mixed states).

- **SHELL-015 — Tab right-click context menu**
  - Given: a tab is present.
  - When: the user right-clicks the tab.
  - Then: a context menu appears with at least Close / Close others / Close all (and Rename/Delete + git actions for workspace tabs).

- **SHELL-016 — Rename a workspace tab inline**
  - Given: a workspace tab's context menu is open, or the user double-clicks the tab.
  - When: the user chooses Rename (or double-clicks), types a new name, and presses Enter.
  - Then: the tab label updates to the new name; pressing Escape instead cancels and restores the old name.

- **SHELL-017 — Delete a workspace from its tab**
  - Given: a workspace tab context menu is open.
  - When: the user chooses Delete and confirms in the dialog.
  - Then: the tab disappears and an adjacent tab/page is shown.

- **SHELL-049 — Copy workspace details from tab context menu**
  - Given: a workspace tab's context menu is open.
  - When: the user chooses Copy workspace name, Copy branch, or Copy workspace id.
  - Then: the chosen value is copied to the clipboard (a confirmation appears briefly).

- **SHELL-050 — Delete the active workspace via keybinding**
  - Given: a workspace tab is active.
  - When: the user presses `Cmd+Shift+W`.
  - Then: the same delete-workspace confirmation dialog opens; confirming removes the workspace and its agents and an adjacent tab/page is shown.

- **SHELL-018 — Close others / Close all from tab menu**
  - Given: multiple tabs open and a tab's context menu is open.
  - When: the user chooses "Close others" or "Close all".
  - Then: all other tabs (or all tabs) close accordingly; "Close all" navigates to the Add Workspace page.

- **SHELL-019 — Tabs persist across restart**
  - Given: the user has tabs open in a particular order with one active.
  - When: the app is closed and reopened.
  - Then: the same tabs reappear in the same order and the previously active tab is shown.

## Closed-workspaces pill

- **SHELL-020 — Closed-workspaces pill appears**
  - Given: the user has closed one or more workspace tabs.
  - When: viewing the top bar.
  - Then: a "Closed N" pill is visible.

- **SHELL-021 — Open the closed-workspaces menu**
  - Given: the closed-workspaces pill is visible.
  - When: the user clicks it.
  - Then: a dropdown lists recently-closed workspaces (showing a spinner while loading).

- **SHELL-022 — Reopen a closed workspace**
  - Given: the closed-workspaces dropdown is open.
  - When: the user clicks a workspace row.
  - Then: that workspace tab reopens and is shown; the dropdown closes.

- **SHELL-023 — Open all closed workspaces**
  - Given: the closed-workspaces dropdown is open.
  - When: the user clicks "Open all".
  - Then: all closed workspace tabs reopen in the bar; the dropdown closes.

- **SHELL-024 — Delete a closed workspace from the menu**
  - Given: the closed-workspaces dropdown is open.
  - When: the user triggers delete on a row and confirms.
  - Then: that row disappears from the list and the workspace is gone.

## Top-bar buttons

- **SHELL-025 — Command palette button**
  - Given: the top bar is visible.
  - When: the user clicks the search/command icon (tooltip "Command palette").
  - Then: the command palette opens with its input focused.

- **SHELL-026 — Help button**
  - Given: the top bar is visible.
  - When: the user clicks the Help (?) icon.
  - Then: the keyboard-shortcuts dialog opens.

- **SHELL-027 — Top-bar button tooltips**
  - Given: the top bar is visible.
  - When: the user hovers a top-bar button.
  - Then: a tooltip shows the button name and its keyboard shortcut.

## Zen & focus modes

- **SHELL-028 — Enter zen mode**
  - Given: the user is on a workspace page.
  - When: the user presses `Cmd+Shift+\`.
  - Then: the top bar and side panels hide, leaving only the chat; a draggable title bar is shown.

- **SHELL-029 — Exit zen mode via floating button**
  - Given: zen mode is active.
  - When: the user moves the mouse to the top-left hot zone.
  - Then: an "Exit zen mode" button appears; clicking it restores the normal layout.

- **SHELL-030 — Tab cycling works in zen mode**
  - Given: zen mode is active.
  - When: the user presses `Cmd+[` / `Cmd+]`.
  - Then: the active tab changes even though the top bar remains hidden.

- **SHELL-031 — Toggle focus mode**
  - Given: the user is on a workspace page.
  - When: the user presses `Cmd+\`.
  - Then: all side panels collapse and the chat expands; pressing again restores the panels.

- **SHELL-032 — Toggle individual panels via keyboard**
  - Given: the user is on a workspace page.
  - When: the user presses `Cmd+Alt+Left` / `Cmd+Alt+Down` / `Cmd+Alt+Right`.
  - Then: the left / bottom / right panel toggles hidden/visible respectively.

## Theme

- **SHELL-033 — Toggle theme via keyboard**
  - Given: the app is focused.
  - When: the user presses `Cmd+Shift+D`.
  - Then: the app switches between light and dark mode immediately, with no reload.

## Version indicator & updates

- **SHELL-034 — Version number shown**
  - Given: the user is on a non-workspace page (and not in zen mode).
  - When: the page renders.
  - Then: the version number is visible in the bottom-right corner.

- **SHELL-035 — Open version popover**
  - Given: the version number is visible.
  - When: the user clicks it (or the adjacent bug icon).
  - Then: a popover opens showing version details, update status, and diagnostics (platform, uptime, active agents, disk, paths, Claude CLI info).

- **SHELL-036 — Update-available dot**
  - Given: an update is downloading or ready.
  - When: viewing the version indicator.
  - Then: a colored dot appears next to the version number.

- **SHELL-037 — Downloading-update toast**
  - Given: an update download begins.
  - When: the download is in progress.
  - Then: a toast shows "Downloading update…" with a percentage.

- **SHELL-038 — Update-ready toast & install**
  - Given: an update finished downloading.
  - When: the toast appears with "Install and restart" and the user clicks it.
  - Then: the button shows "Restarting…" and the app restarts.

- **SHELL-039 — Update-error toast**
  - Given: the auto-updater errors.
  - When: the error occurs.
  - Then: an error toast appears and auto-dismisses after a few seconds.

- **SHELL-040 — Dismiss download toast**
  - Given: a downloading-update toast is showing.
  - When: the user dismisses it.
  - Then: the toast disappears and does not reappear while the same download continues.

- **SHELL-041 — Dev-tools toggles in version popover**
  - Given: the version popover is open.
  - When: the user toggles "React Grab", "TanStack Devtools", or "TanStack event log".
  - Then: the corresponding dev tool appears/disappears.

## Status banners

- **SHELL-042 — Backend-unresponsive banner**
  - Given: the backend becomes unresponsive.
  - When: the status changes.
  - Then: a yellow banner appears at the bottom: "Backend not responding. Please try restarting the app."

- **SHELL-043 — Backend health-warning banner**
  - Given: the backend reports a health warning.
  - When: the status changes.
  - Then: a yellow warning banner appears with the warning message (and optional link).

- **SHELL-044 — Missing project-folder banner**
  - Given: the active workspace's project folder is not found.
  - When: the page renders.
  - Then: a banner reads "Project folder not found: {name}." with a "Learn more" link that opens a dialog.

- **SHELL-045 — Backend loading splash**
  - Given: the app is starting and the backend is launching.
  - When: viewing the screen.
  - Then: a splash with the Sculptor logo, "Loading" message, and progress bar is shown until the backend is ready.

- **SHELL-046 — Backend shutting-down screen**
  - Given: the app is quitting / restarting the backend.
  - When: the status becomes shutting-down.
  - Then: a "Shutting down…" message with a progress bar is shown; if stalled past ~30s a recovery message appears.

- **SHELL-047 — Dev-mode indicator**
  - Given: the app is running from source (not packaged).
  - When: viewing the page.
  - Then: a dev-mode indicator is shown (bottom-left); hovering it shows a "Running from source" tooltip with the workspace id.

## Window & zoom

- **SHELL-048 — Zoom in / out / reset**
  - Given: the app is focused.
  - When: the user presses `Cmd+=`, `Cmd+-`, or `Cmd+0`.
  - Then: the UI scales up, down, or back to 100% respectively, and the zoom level persists across restarts.

---

# ROUTE — Routing, startup & error pages

- **ROUTE-001 — Startup redirect to last active tab**
  - Given: the user had tabs open previously.
  - When: the app launches and loads `/`.
  - Then: it redirects to the previously active tab's page (or the Add Workspace page if none).

- **ROUTE-002 — New-workspace route generates a draft**
  - Given: the user navigates to `/ws/new`.
  - When: the route loads.
  - Then: it redirects to `/ws/new/{draftId}` and shows the Add Workspace form.

- **ROUTE-003 — 404 page for unknown route**
  - Given: the user navigates to a URL that matches no route.
  - When: the page loads.
  - Then: a Not-Found page shows the Sculptor logo and "The page you are looking for does not exist." with a link back to home.

- **ROUTE-004 — Route error boundary**
  - Given: a route loader or component throws.
  - When: the error occurs.
  - Then: an error page is shown with a generic message and the error details in a scrollable box.

- **ROUTE-005 — Copy error to clipboard**
  - Given: the route error page is shown.
  - When: the user clicks "Copy Error to Clipboard".
  - Then: the error text is copied (a person can paste it elsewhere).

- **ROUTE-006 — Clear custom-backend command from error page**
  - Given: a custom backend command is set and causing errors, and the error page shows the clear button.
  - When: the user clicks "Clear Custom Backend Command".
  - Then: the button becomes disabled and its label changes to indicate the command was cleared and a restart is needed.

---

# HELP — Keyboard shortcuts dialog

- **HELP-001 — Open the help dialog**
  - Given: the app is focused.
  - When: the user clicks the Help button or presses `Cmd+/`.
  - Then: a modal titled "Help" opens listing all keybindings grouped by category.

- **HELP-002 — Shortcuts formatted per OS**
  - Given: the help dialog is open.
  - When: viewing a shortcut.
  - Then: it is shown in a key-badge formatted for the current OS (e.g., `Cmd+K` on macOS, `Ctrl+K` elsewhere).

- **HELP-003 — Close the help dialog**
  - Given: the help dialog is open.
  - When: the user clicks the X or presses Escape.
  - Then: the dialog closes.

---

# HOME — Home page / recent workspaces

The home page and the Add Workspace page share the recent-workspaces list and its rows.

- **HOME-001 — Loading state**
  - Given: the workspace list is being fetched.
  - When: the page first renders.
  - Then: a spinner is shown in the list area.

- **HOME-002 — Empty state (no workspaces)**
  - Given: the user has no workspaces.
  - When: the list loads.
  - Then: a centered folder icon, "No workspaces yet" heading, and a "Describe what you need above to create your first workspace." message are shown.

- **HOME-003 — Search bar present & autofocused**
  - Given: at least one workspace exists.
  - When: the page loads.
  - Then: a search input with placeholder "Search workspaces…" is shown and focused.

- **HOME-004 — Filter workspaces by query**
  - Given: the workspace list is populated.
  - When: the user types in the search box.
  - Then: the list filters in real time by workspace name, branch, and project (case-insensitive).

- **HOME-005 — No search results**
  - Given: a search query matches nothing.
  - When: filtering completes.
  - Then: a centered message `No results for "{query}"` is shown.

- **HOME-006 — Escape clears search**
  - Given: the search box has text and focus.
  - When: the user presses Escape.
  - Then: the query clears, the full list returns, and focus returns to the search input.

- **HOME-007 — Sort order**
  - Given: multiple workspaces.
  - When: the list is shown.
  - Then: workspaces are ordered by most recent activity first.

- **HOME-008 — Pagination "Show more"**
  - Given: more than 25 workspaces exist.
  - When: the list loads.
  - Then: only 25 rows show, with a "Show more (N remaining)" button; clicking it reveals the next 25.

- **HOME-009 — Search resets visible count**
  - Given: more than 25 rows are shown after "Show more".
  - When: the user types a search query.
  - Then: the visible count resets to the first 25 filtered results.

- **HOME-010 — Workspace row contents**
  - Given: a workspace exists.
  - When: the row is shown.
  - Then: it shows a status dot, the workspace name, the branch name (monospace), a PR button if a branch exists, the project name (revealed on hover), a relative last-activity time, and a delete button (revealed on hover).

- **HOME-011 — Row hover/focus styling**
  - Given: a workspace row.
  - When: the user hovers or keyboard-focuses it.
  - Then: the row background changes and the project name and delete button become visible.

- **HOME-012 — Keyboard navigation into the list**
  - Given: the search box is focused.
  - When: the user presses ArrowDown.
  - Then: the first row gains focus and scrolls into view; ArrowUp from the first row returns focus to the search box.

- **HOME-013 — Open a workspace with Enter / click**
  - Given: a row is focused or visible.
  - When: the user presses Enter on it (or clicks it without a modifier).
  - Then: the current tab becomes that workspace and it opens.

- **HOME-014 — Open a workspace in a new tab**
  - Given: a workspace row is visible.
  - When: the user Cmd/Ctrl-clicks it (or chooses "Open in New Tab" from its right-click menu).
  - Then: the workspace opens in a new tab while the home page remains visible.

- **HOME-015 — Row context menu**
  - Given: a workspace row.
  - When: the user right-clicks it.
  - Then: a menu with "Open in New Tab" and "Delete Workspace" (in red) appears.

- **HOME-016 — Delete via row button / menu**
  - Given: a row is hovered (delete button visible) or its context menu is open.
  - When: the user clicks the delete trash icon or "Delete Workspace".
  - Then: a delete-confirmation dialog opens.

- **HOME-017 — Delete confirmation dialog**
  - Given: the delete dialog is open.
  - When: viewing it.
  - Then: it shows "Delete workspace?", a warning naming the workspace, a Cancel button, and a red Delete button (focused by default).

- **HOME-018 — Cancel deletion**
  - Given: the delete dialog is open.
  - When: the user clicks Cancel or presses Escape.
  - Then: the dialog closes and the workspace remains.

- **HOME-019 — Confirm deletion**
  - Given: the delete dialog is open.
  - When: the user clicks Delete (or presses Enter).
  - Then: the dialog closes and the row disappears from the list immediately.

- **HOME-020 — PR button states on a row**
  - Given: a workspace row with a branch.
  - When: the PR status is known.
  - Then: the button reflects the state: a spinner + "Checking PR…" while loading; "Create PR" when none exists; "PR #N" with pipeline & review status dots when open; a merged/closed badge when merged/closed; an "Assign PR" option when a PR targets a different branch; and an error button (warning/info icon) on failure.
  - (See WS-PR scenarios for full PR-button behavior; rows reuse the same component.)

---

# ONB — Onboarding wizard

## Step indicator

- **ONB-001 — Step indicator shows three steps**
  - Given: the onboarding wizard is shown.
  - When: viewing the bottom indicator.
  - Then: three dots represent Email, Installation, and Add-Repo; the current step is visually distinct, past steps are clickable, future steps are disabled.

- **ONB-002 — Navigate to a past step**
  - Given: the user is on the Installation step.
  - When: the user clicks the Email step dot.
  - Then: the wizard returns to the Email step.

- **ONB-003 — Future steps not clickable**
  - Given: the user is on the Email step.
  - When: the user clicks the Installation/Add-Repo dots.
  - Then: nothing happens (they appear disabled).

## Email / welcome step

- **ONB-004 — Email step fields**
  - Given: the Email step is shown.
  - When: viewing the form.
  - Then: a "Full name" input (autofocused), an "Email address" input, a marketing opt-in checkbox (unchecked), a telemetry checkbox (checked), and terms/privacy links are visible, along with the message "Your code is yours — Imbue does not store your repositories or train on your code".

- **ONB-005 — Get Started disabled without valid email**
  - Given: the Email step is shown.
  - When: the email field is empty or lacks an "@".
  - Then: the "Get Started" button is disabled.

- **ONB-006 — Get Started enabled with valid email**
  - Given: the Email step is shown.
  - When: the user types an email containing "@".
  - Then: the "Get Started" button becomes enabled.

- **ONB-007 — Submit email (loading)**
  - Given: a valid email is entered.
  - When: the user clicks "Get Started" (or presses Enter).
  - Then: the button shows a spinner and is disabled while the request is in flight; on success the wizard advances to the Installation step.

- **ONB-008 — Submit email error**
  - Given: a valid email is submitted.
  - When: the request fails.
  - Then: a red error message appears below the button.

- **ONB-009 — Continue without an account**
  - Given: the Email step is shown.
  - When: the user clicks "Continue without an account".
  - Then: the link/button disables while in flight and the wizard advances to the Installation step.

- **ONB-010 — Toggle marketing / telemetry checkboxes**
  - Given: the Email step is shown.
  - When: the user clicks the marketing or telemetry checkbox.
  - Then: that checkbox toggles checked/unchecked.

## Installation step

- **ONB-011 — Installation step header**
  - Given: the Installation step is shown.
  - When: viewing the page.
  - Then: "Let's get you set up" and "The following are required to use Sculptor" are shown.

- **ONB-012 — Dependency card: loading**
  - Given: the Installation step loads.
  - When: dependency status is being fetched.
  - Then: each dependency card shows a spinner and "—" for path/version.

- **ONB-013 — Dependency card: not installed**
  - Given: a dependency (Claude/Git) is not installed.
  - When: status loads.
  - Then: the card shows a red error icon, "not installed", and an Install button.

- **ONB-014 — Dependency card: installed**
  - Given: a dependency is installed at the right version (and authenticated for Claude).
  - When: status loads.
  - Then: the card shows a green checkmark and the path/version.

- **ONB-015 — Dependency card: wrong version**
  - Given: a dependency is installed at the wrong version.
  - When: status loads.
  - Then: the card shows a red error and, when expanded, the current and required versions.

- **ONB-016 — Claude card: needs auth**
  - Given: Claude is installed but not signed in.
  - When: status loads.
  - Then: the card shows a yellow warning, "not signed in", and a Sign-in button.

- **ONB-017 — Claude card: authenticating**
  - Given: the user clicked Sign in.
  - When: authentication is in progress.
  - Then: a spinner and "authenticating" appear with a help message about running `claude auth login` in a terminal.

- **ONB-034 — Claude card: paste-a-code sign-in**
  - Given: a headless/remote setup where a browser callback can't reach the app, after the user starts Claude sign-in.
  - When: the card shows the paste-a-code panel.
  - Then: the sign-in URL and instructions are shown with a "Paste code here" input; pasting the authorization code and submitting (Enter) completes sign-in.

- **ONB-035 — GitHub CLI card: device-flow sign-in**
  - Given: the optional GitHub CLI (`gh`) card shows "not signed in".
  - When: the user clicks "Sign in".
  - Then: the card shows a one-time code, an "Open verification page" link, and a waiting state; once the user approves at GitHub and `gh` reports authenticated, the card flips to signed-in on its own.

- **ONB-018 — Claude managed install (progress)**
  - Given: Claude is managed and not installed.
  - When: installation runs (auto-triggered on load or via Install).
  - Then: the card shows "installing" with a circular progress percentage.

- **ONB-019 — Install error & retry**
  - Given: an install fails.
  - When: the failure occurs.
  - Then: the card shows an error; the user can retry / re-check.

- **ONB-020 — Expand dependency card**
  - Given: a dependency card is shown.
  - When: the user clicks it.
  - Then: a details section expands revealing path, version, and mode controls; the chevron flips.

- **ONB-021 — Install popover / command**
  - Given: a dependency is not installed.
  - When: the user opens the Install affordance.
  - Then: a popover shows the install command (e.g., `brew install claude-code`) and a docs link.

- **ONB-022 — Override binary path**
  - Given: a dependency card is expanded.
  - When: the user clicks "override", enters a path, and clicks Apply.
  - Then: a valid path updates the card; an invalid path shows "No executable found at this path".

- **ONB-023 — Switch managed/custom mode**
  - Given: a dependency card is expanded.
  - When: the user clicks "Use System PATH" / "Use Managed".
  - Then: the mode switches and the UI updates accordingly.

- **ONB-024 — Continue button gating**
  - Given: the Installation step is shown.
  - When: any required dependency is missing/unauthenticated.
  - Then: the Continue button is disabled; once all are satisfied it is enabled.

- **ONB-025 — Check again**
  - Given: the Installation step is shown.
  - When: the user clicks the "check again" link.
  - Then: the text changes to "Checking…" briefly and the cards refresh with current status.

- **ONB-026 — Continue from installation**
  - Given: dependencies are satisfied and Continue is enabled.
  - When: the user clicks Continue (or presses Enter).
  - Then: if the user already has projects, onboarding completes; otherwise the Add-Repo step is shown.

## Add-repo step

- **ONB-027 — Add-repo step header & source picker**
  - Given: the Add-Repo step is shown.
  - When: viewing the page.
  - Then: "Add your first repo" with a source picker defaulting to **GitHub** (search/clone your repos) and a **Local Folder** option (a path input, placeholder `~/path/to/repo`) is shown.

- **ONB-028 — Browse for folder (desktop)**
  - Given: the Add-Repo step on desktop with the Local Folder source selected.
  - When: the user clicks "Or browse for a folder" and selects a folder.
  - Then: the path input is populated with the chosen path.

- **ONB-036 — Connect first repo by cloning from GitHub**
  - Given: the Add-Repo step on the GitHub source with `gh` authenticated.
  - When: the user selects one of their GitHub repos (or pastes a URL) and submits.
  - Then: a clone-progress view is shown; on success the repo is added and the wizard completes into the app.

- **ONB-029 — Add button gating**
  - Given: the Add-Repo step.
  - When: the path is empty.
  - Then: the Add button is disabled with tooltip "Enter a repository path above"; entering a path enables it; clicking it shows a spinner while validating.

- **ONB-030 — Valid repo added**
  - Given: a path to a valid git repo with commits is entered.
  - When: the user clicks Add.
  - Then: validation succeeds, the wizard completes, and the user is taken into the app.

- **ONB-031 — Not-a-git-repo prompt**
  - Given: a path to a non-git directory is entered.
  - When: the user clicks Add.
  - Then: a dialog offers to initialize git; choosing "Initialize Git" shows "Setting up repository…" and on success adds the repo; Cancel returns to the step.

- **ONB-032 — Empty-repo prompt**
  - Given: a git repo with no commits is entered.
  - When: the user clicks Add.
  - Then: a dialog offers "Make Initial Commit"; choosing it creates the commit and adds the repo; Cancel returns.

- **ONB-033 — Invalid path error**
  - Given: a nonexistent/inaccessible path is entered.
  - When: the user clicks Add.
  - Then: the dialog shows an error message with a Close button.

---

# ADDWS — Add-workspace page (create workspace)

- **ADDWS-001 — Page loading then form**
  - Given: the Add Workspace page is opening.
  - When: projects are being fetched.
  - Then: a centered spinner is shown; once loaded the creation form appears.

- **ADDWS-002 — Default project selection**
  - Given: projects exist.
  - When: the page loads.
  - Then: the most-recently-used project (or the first project if no MRU) is pre-selected in the repo selector.

- **ADDWS-003 — Workspace name input**
  - Given: the form is shown.
  - When: viewing it.
  - Then: a name input with placeholder "Untitled workspace (optional)" is shown and autofocused; typing shows the text.

- **ADDWS-004 — Empty / whitespace name defaults**
  - Given: the name is empty or only whitespace.
  - When: the user creates the workspace.
  - Then: it is created as "Untitled workspace".

- **ADDWS-005 — Name draft persists**
  - Given: the user typed a name and navigated away.
  - When: the user returns to the same draft.
  - Then: the previously typed name is restored.

- **ADDWS-025 — Repo/branch/source-branch selections persist across tab switches**
  - Given: the user chose a repo, source branch, and branch name on the Add Workspace form, then switched tabs.
  - When: the user returns to the same draft.
  - Then: the previously chosen repo, source branch, and branch name are all restored.

- **ADDWS-006 — Repo selector dropdown**
  - Given: the repo selector is shown.
  - When: the user clicks it.
  - Then: a dropdown lists all projects plus an "Add Repository" entry.

- **ADDWS-007 — Select a different project**
  - Given: the repo dropdown is open.
  - When: the user clicks another project.
  - Then: the selection changes, the branch selector reloads, and any branch-name override clears.

- **ADDWS-008 — Add repository from selector**
  - Given: the repo dropdown is open.
  - When: the user clicks "Add Repository".
  - Then: the Add Repository dialog opens; on success the new project is auto-selected.

- **ADDWS-009 — Branch selector loading**
  - Given: a project is selected and branch info is loading.
  - When: viewing the branch control.
  - Then: it shows a spinner and "Loading …" and is disabled.

- **ADDWS-010 — Branch selector dropdown & selection**
  - Given: branch info loaded.
  - When: the user opens the branch selector and clicks a branch.
  - Then: the dropdown lists recent branches (and a "Fetch more branches" option), and selecting one updates the source branch and clears any branch-name override.

- **ADDWS-011 — Branch selector disabled for in-place**
  - Given: the mode is In-place.
  - When: viewing the branch selector.
  - Then: it is disabled with a tooltip explaining in-place workspaces use the current branch.

- **ADDWS-012 — Branch-name field visibility & label**
  - Given: the mode is Worktree / Clone / In-place.
  - When: viewing the form.
  - Then: Worktree shows a required branch-name field; Clone shows an optional one; In-place shows no branch-name field.

- **ADDWS-013 — Branch-name auto-fill preview**
  - Given: Worktree mode and the user typed a workspace name.
  - When: the form is shown.
  - Then: the branch-name field auto-fills a preview (with a "…" spinner while fetching) derived from the name, updating as the name changes.

- **ADDWS-014 — Manual branch-name override & reset**
  - Given: the branch-name field has an auto-filled preview.
  - When: the user types into it.
  - Then: the manual value takes over, auto-fill stops, and a reset link appears; clicking reset restores the preview.

- **ADDWS-015 — Branch-name collision error**
  - Given: a branch name is entered that already exists in the repo.
  - When: the collision check completes.
  - Then: a red message "Branch '{name}' already exists" appears below the field and clears when the user edits the name.

- **ADDWS-016 — Agent-type selector options**
  - Given: the form is shown.
  - When: the user opens the agent-type selector.
  - Then: it lists Claude, Terminal, Pi, and any registered custom agents; re-opening rescans for newly registered agents.

- **ADDWS-017 — Select agent type & MRU**
  - Given: the agent-type dropdown is open.
  - When: the user selects a type.
  - Then: the button shows the new type; the selection is remembered as the default for next time. A previously-selected type that is no longer available falls back to Claude.

- **ADDWS-018 — Mode selector visibility**
  - Given: clone and/or in-place workspaces are enabled in settings.
  - When: viewing the form.
  - Then: an environment/mode selector is shown (Worktree always; Clone and/or In-place when enabled); if neither experimental mode is enabled, the selector is hidden and defaults to Worktree.

- **ADDWS-019 — Change mode updates branch fields**
  - Given: a mode is selected.
  - When: the user switches to Clone or In-place.
  - Then: the branch-name field changes to optional (Clone) or disappears and the branch selector disables (In-place).

- **ADDWS-020 — Create button gating & tooltips**
  - Given: the form is shown.
  - When: required fields are incomplete (e.g., Worktree branch name empty or still loading) or creation is in progress.
  - Then: the Create button is disabled with an explanatory tooltip ("Waiting for branch name…", "Agent is being created…"); when ready it is enabled with tooltip "Cmd/Ctrl+↵ to create workspace".

- **ADDWS-021 — Create the workspace**
  - Given: all fields are valid.
  - When: the user clicks "Create workspace" or presses `Cmd+Enter`.
  - Then: the workspace and its first agent are created and the user is navigated into the new workspace/agent tab.

- **ADDWS-022 — Keyboard focus into form**
  - Given: the page loads with nothing focused.
  - When: the user presses ArrowDown/ArrowUp.
  - Then: focus moves to the workspace-name input.

- **ADDWS-023 — Create error: branch exists**
  - Given: the user submits with a branch name that already exists.
  - When: the request returns a conflict.
  - Then: an error toast "Branch '{name}' already exists" appears and the form stays open for editing.

- **ADDWS-024 — Create error: generic failure**
  - Given: the user submits the form.
  - When: workspace or agent creation fails.
  - Then: an error toast ("Failed to create workspace" / "Failed to create agent") with details is shown.

---

# ADDREPO — Add-repository dialog & path autocomplete

- **ADDREPO-001 — Open add-repo dialog**
  - Given: the repo selector dropdown is open (or another add-repo entry point).
  - When: the user clicks "Add Repository".
  - Then: a modal opens with a source picker (radio cards) defaulting to **GitHub**, plus a **Local
    Folder** option; the Local Folder option shows a path input and, on desktop, a Browse button.

- **ADDREPO-002 — Cancel dialog**
  - Given: the dialog is open and not validating.
  - When: the user clicks Cancel / Escape / clicks the overlay.
  - Then: the dialog closes with no changes.

- **ADDREPO-003 — Prevent close during validation**
  - Given: validation is in progress.
  - When: the user tries to close the dialog.
  - Then: it stays open.

- **ADDREPO-004 — Add valid repo**
  - Given: a valid path is entered.
  - When: the user clicks "Add Repository".
  - Then: on success the dialog closes and the new repo is selected in the dropdown.

- **ADDREPO-005 — Dialog resets on reopen**
  - Given: the user previously typed a path and closed the dialog.
  - When: the dialog is reopened.
  - Then: the path input is empty.

- **ADDREPO-006 — Path autocomplete dropdown**
  - Given: a path input.
  - When: the user types a path containing "/" or starting with "~".
  - Then: after a short debounce a spinner shows, then a list of matching directories appears (or "No matching directories").

- **ADDREPO-007 — Navigate directories in autocomplete**
  - Given: the autocomplete list is shown.
  - When: the user clicks a directory.
  - Then: the path gains a trailing "/" and the next level of directories is fetched.

- **ADDREPO-008 — Autocomplete keyboard hints & submit**
  - Given: the autocomplete dropdown has items.
  - When: viewing the footer.
  - Then: hints "Esc: close", "↵: open", "{Meta}↵: add" are shown; pressing Enter with the dropdown closed (or `Cmd+Enter` anytime) submits the trimmed path.

- **ADDREPO-009 — GitHub repo search & select**
  - Given: the dialog is on the GitHub source and `gh` is authenticated.
  - When: the user types in the "Repository" combobox.
  - Then: matching repos appear (each showing its name, a lock for private repos, and last-pushed time); selecting one fills the repo and a suggested target folder, ready to clone.

- **ADDREPO-010 — Paste a clone URL instead**
  - Given: the dialog is on the GitHub source.
  - When: the user clicks "I'll paste a URL instead".
  - Then: the form switches to a URL field accepting an HTTPS/SSH/`git` clone URL; "Search my repositories instead" switches back.

- **ADDREPO-011 — GitHub not configured**
  - Given: the dialog is on the GitHub source and `gh` is missing or not authenticated.
  - When: viewing the GitHub form.
  - Then: a "GitHub CLI not configured" message explains the requirement and offers a "Configure GitHub" shortcut to Settings; the user can still paste a URL.

- **ADDREPO-012 — Clone progress**
  - Given: a GitHub repo (or pasted URL) is selected.
  - When: the user submits the clone.
  - Then: a progress view appears titled "Cloning {owner/repo}…" with a progress bar until the clone finishes and the repo is added.

- **ADDREPO-013 — Clone destination exists → add as local**
  - Given: a clone whose target folder already exists.
  - When: the clone fails for that reason.
  - Then: Sculptor surfaces the error and offers to add the existing folder as a local repo instead.

---

# WS — Workspace shell (chat input, banner, PR, agents, peek)

## Chat input & sending

- **WS-001 — Type and send a message**
  - Given: a workspace with an active agent.
  - When: the user types in the chat input and clicks Send (or presses the send keybinding).
  - Then: the message is sent, the editor clears, and any attachments clear.

- **WS-002 — Send button disabled & blocked states**
  - Given: the chat input.
  - When: the editor is empty, or the agent is busy (for non-`/btw` content), or the agent's harness has no usable model (a Pi agent with no authenticated providers).
  - Then: for an empty editor or a busy agent the Send button is disabled and hovering shows the reason; when the harness has no usable model the Send button is replaced by a **Go to harness configuration** button that opens the harness's settings (Settings → Pi, or Settings → Dependencies for Claude).

- **WS-003 — Interrupt-and-send**
  - Given: the agent is busy and the user typed a message.
  - When: the user presses the interrupt-and-send keybinding.
  - Then: the running turn is interrupted and the new message is sent.

- **WS-004 — Send failure feedback**
  - Given: the user sends a message.
  - When: sending fails.
  - Then: an error toast appears, the editor text is preserved, and the Send button reflects the error on hover.

- **WS-005 — Attach files via drag-and-drop**
  - Given: file attachment is supported.
  - When: the user drags files over the chat input.
  - Then: a "Drop to attach images" overlay appears; on drop the files are added to a preview list.

- **WS-006 — Attach files via upload button**
  - Given: file attachment is supported.
  - When: the user clicks the upload button and selects files.
  - Then: the files are added to the attachment preview list.

- **WS-007 — Remove an attached file**
  - Given: files are attached.
  - When: the user clicks a file's remove button.
  - Then: that file is removed from the preview list.

- **WS-008 — Mention/insert menu**
  - Given: the chat input.
  - When: the user clicks the "+" toolbar button (or types a trigger).
  - Then: a picker opens offering files, skills/commands, and entities (see MENT scenarios).

- **WS-009 — Model selector**
  - Given: the chat input toolbar.
  - When: the user opens the model selector and picks a model.
  - Then: the selection is highlighted and applied to future messages.

- **WS-010 — Effort selector**
  - Given: the chat input toolbar.
  - When: the user opens the effort selector and picks a level.
  - Then: the choice is applied to future messages.

- **WS-011 — Fast-mode toggle**
  - Given: the model supports fast mode.
  - When: the user toggles fast mode.
  - Then: the toggle state changes and is applied to future messages.

- **WS-012 — Plan-mode toggle**
  - Given: an agent that supports interactive plan mode.
  - When: the user toggles plan mode and sends a message.
  - Then: the toggle's styling changes when active; sending enters plan mode (or exits it if already in plan mode).

- **WS-013 — Multiline input**
  - Given: the chat input.
  - When: the user inserts line breaks (Shift+Enter).
  - Then: the editor grows to show multiple lines; sending submits the whole text as one message.

- **WS-014 — `/clear` pseudo-command**
  - Given: the agent supports context reset.
  - When: the user types `/clear` and sends.
  - Then: the context is cleared and a success toast appears (or, if unsupported, a "capability unsupported" toast).

- **WS-015 — `/copy` pseudo-command**
  - Given: there is an assistant message.
  - When: the user types `/copy` and sends.
  - Then: the last assistant message is copied and a "copied" toast appears (or an error toast if there is none).

- **WS-016 — `/btw` side chat**
  - Given: an active session exists.
  - When: the user types `/btw <question>` and sends.
  - Then: a side-chat popup opens showing the question and the agent's streamed answer (or a toast if no session yet).

## Queued messages

- **WS-017 — Queued-message bar appears**
  - Given: the agent is running and the user queued a message.
  - When: viewing the chat.
  - Then: a queued-message bar appears below the input showing the queued text.

- **WS-018 — Remove a queued message**
  - Given: a queued message is shown.
  - When: the user clicks its remove icon.
  - Then: the queued message is deleted and the bar disappears.

- **WS-019 — Edit a queued message (empty editor)**
  - Given: a queued message is shown and the editor is empty.
  - When: the user clicks edit.
  - Then: the queued message is removed and its text is restored to the editor.

- **WS-020 — Edit-conflict dialog**
  - Given: a queued message exists and the editor already has unsaved text.
  - When: the user clicks edit.
  - Then: an Undo/Queued dialog opens offering "Keep queued", "Remove", and "Overwrite", plus a copy button; each option behaves as labeled.

- **WS-021 — Interrupt-and-send a queued message**
  - Given: a queued message bar is shown and interruption is supported.
  - When: the user clicks the interrupt-and-send (arrow-up) button.
  - Then: the running turn is interrupted and the queued message is sent; the button is hidden if interruption is unsupported.

## PR button

- **WS-022 — Checking PR status**
  - Given: a workspace with a branch.
  - When: PR status is loading.
  - Then: a spinner with "Checking PR…" is shown.

- **WS-023 — Create PR**
  - Given: no PR exists for the branch.
  - When: the user clicks "Create PR".
  - Then: a default PR-creation prompt (including the target branch) is sent to the agent.

- **WS-024 — Edit PR prompt before creating**
  - Given: the Create PR button is shown.
  - When: the user opens its chevron menu and clicks "Edit prompt…".
  - Then: a dialog opens to edit the prompt; Save updates it and closes.

- **WS-025 — Open PR display**
  - Given: an open PR exists.
  - When: viewing the button.
  - Then: it shows "PR #N" with pipeline and review status dots.

- **WS-026 — Open PR in browser**
  - Given: an open PR button is shown.
  - When: the user clicks the PR number.
  - Then: the PR opens in the browser.

- **WS-027 — PR detail dropdown**
  - Given: an open PR button is shown.
  - When: the user clicks the chevron.
  - Then: a popover shows PR title/link, checks/pipeline status, approvals with reviewer names, and unresolved comments.

- **WS-028 — CI babysitter toggle in PR dropdown**
  - Given: CI babysitter is enabled and the PR dropdown is open.
  - When: the user toggles the babysitter switch.
  - Then: it pauses/resumes and the status text updates; the pause state is remembered for the
    workspace and is still in effect after an app restart.

- **WS-077 — CI babysitter disabled reason in PR dropdown**
  - Given: the babysitter can't run for this workspace (e.g. its configured agent type can't be resolved) and the PR dropdown is open.
  - When: the user views the babysitter row.
  - Then: a short disabled-reason message is shown in place of the usual status; for a persistent reason the switch is forced off and greyed out (inert).

- **WS-029 — Merged/closed PR**
  - Given: the PR was merged or closed.
  - When: viewing the button.
  - Then: it shows a merge icon with "PR #N merged"/"closed"; clicking opens it in the browser.

- **WS-030 — PR pipeline & review dot tooltips**
  - Given: an open PR with pipeline/review status.
  - When: the user hovers the dots.
  - Then: tooltips show "Pipeline running/passed/failed/No pipeline" and "Approved/Review pending/No reviewers".

- **WS-031 — Assign PR (target mismatch)**
  - Given: a PR exists for a different target than the workspace's.
  - When: viewing the button.
  - Then: an "Assign PR" button is shown; opening it offers "Create PR → {target}" and "switch target to {target}".

- **WS-032 — PR error states**
  - Given: PR status checking failed.
  - When: viewing the button.
  - Then: an error button with a warning triangle (actionable) or info icon (non-actionable) is shown; opening it shows a popover with a title, description, optional details, and an optional copyable remediation command (copy icon turns to a checkmark briefly).

## Target branch & repo segment

- **WS-033 — Target-branch selector**
  - Given: any workspace (regardless of remote host).
  - When: viewing the banner.
  - Then: the target branch name is shown; clicking it opens a dropdown of branches, and selecting one updates the target.

- **WS-078 — Target-branch selector on a repo with no remote**
  - Given: a workspace whose repo has no remote configured.
  - When: the user opens the target-branch selector.
  - Then: the dropdown offers the repo's local branches (excluding the workspace's own branch), and selecting one updates the target shown in the banner.

- **WS-034 — Target-branch PR mismatch warning**
  - Given: the workspace target differs from an existing PR's target.
  - When: viewing the selector.
  - Then: the branch is shown in a warning color; hovering shows "PR #N targets {branch} — retarget?"; selecting the matching branch updates the target.

- **WS-035 — Repo segment menu**
  - Given: the banner shows the repo name.
  - When: the user clicks the repo segment.
  - Then: a dropdown offers Open folder, Copy path, Copy relative path, and Open in installed apps (VS Code, etc.), each performing its labeled action; the chosen app is remembered.

- **WS-036 — Initialization-strategy badge**
  - Given: the workspace uses clone or in-place mode.
  - When: viewing the banner.
  - Then: a "clone" or "in-place" badge is shown next to the repo name (no badge for worktree).

## Banner & diff summary

- **WS-037 — Banner visibility**
  - Given: the user is/ is not in zen mode.
  - When: viewing the workspace.
  - Then: the banner with repo/branch/PR info is shown normally and hidden in zen mode.

- **WS-038 — Banner progressive collapse**
  - Given: the viewport narrows.
  - When: space becomes constrained.
  - Then: banner elements collapse in priority order (PR button → diff summary → repo segment).

- **WS-039 — Copy branch name from banner**
  - Given: the branch name is shown in the banner.
  - When: the user clicks it.
  - Then: it is copied and a "Copied!" tooltip appears briefly.

- **WS-040 — Diff summary button**
  - Given: the workspace has uncommitted changes.
  - When: viewing the banner.
  - Then: a "+X −Y · Z files" summary is shown (with a shimmer while loading); clicking it opens the file browser's Changes tab scoped to the target branch.

## Agent tabs

- **WS-041 — Agent tabs shown**
  - Given: a workspace with one or more agents.
  - When: viewing the workspace.
  - Then: a tab per agent is shown with its title and status dot.

- **WS-042 — Switch agents**
  - Given: multiple agent tabs.
  - When: the user clicks another agent tab (or presses the next/previous-agent keybinding).
  - Then: the view switches to that agent's chat/state.

- **WS-043 — Agent status-dot tooltip**
  - Given: an agent tab.
  - When: the user hovers its status dot.
  - Then: a tooltip shows the status label and time since last activity / creation.

- **WS-044 — Create a new agent**
  - Given: agent tabs are shown.
  - When: the user clicks the "+" button.
  - Then: a new agent of the default type is created and shown.

- **WS-045 — Choose agent type when creating**
  - Given: the "+" chevron menu.
  - When: the user opens it.
  - Then: it lists Claude, Pi, Terminal, and registered custom agents; selecting one creates that type and remembers it.

- **WS-046 — Rename an agent (double-click)**
  - Given: an agent tab.
  - When: the user double-clicks the title, types a name, and presses Enter.
  - Then: the agent is renamed; Escape cancels.

- **WS-047 — Agent context menu**
  - Given: an agent tab.
  - When: the user right-clicks it.
  - Then: a menu offers Rename, Mark as unread, Copy agent name, Delete, and a Diagnostics submenu (Debug View toggle; copy Claude session id / transcript path / Sculptor transcript path — disabled when unavailable).

- **WS-048 — Delete an agent**
  - Given: an agent context menu (or close button) is used.
  - When: the user deletes and confirms.
  - Then: the agent is removed and navigation moves to the next agent (or a fresh one if it was the last).

- **WS-049 — Mark agent unread**
  - Given: a read agent.
  - When: the user chooses "Mark as unread".
  - Then: the agent's status indicator changes to unread.

- **WS-050 — Reorder agent tabs**
  - Given: multiple agent tabs.
  - When: the user drags a tab to a new position.
  - Then: the order updates.

## Terminal agent panel

- **WS-051 — Terminal agent shows a terminal**
  - Given: a terminal-type agent (no chat interface).
  - When: viewing the agent.
  - Then: a full-pane terminal is shown instead of the chat, streaming output.

- **WS-052 — Terminal persists across agent switches**
  - Given: a terminal agent is active.
  - When: the user switches away and back.
  - Then: the terminal reconnects and previous scrollback is restored.

- **WS-079 — Terminal pane focuses on tab select**
  - Given: a workspace with a terminal agent among its tabs.
  - When: the user selects the terminal agent's tab.
  - Then: the terminal pane takes keyboard focus so the user can type into the shell immediately.

## Ask-user-question (input area)

- **WS-053 — Question panel replaces input**
  - Given: the agent issues an AskUserQuestion.
  - When: the question arrives.
  - Then: a question panel replaces the chat input, showing a category chip, the question, options (plus "Other"), and navigation controls.

- **WS-054 — Single-select answer**
  - Given: a single-select question.
  - When: the user clicks an option and submits.
  - Then: only that option is selected and the answer is sent.

- **WS-055 — Multi-select answer**
  - Given: a multi-select question.
  - When: the user checks multiple options and submits.
  - Then: all selected options are sent.

- **WS-056 — Custom "Other" answer**
  - Given: a question with an alternative option.
  - When: the user clicks "Other" and types text.
  - Then: a textarea captures the custom answer.

- **WS-057 — Navigate between questions**
  - Given: multiple questions.
  - When: the user uses Tab/Shift+Tab, arrows, or the progress dots.
  - Then: the current question changes and dots show answered/unanswered/current.

- **WS-058 — Submit / next / dismiss**
  - Given: questions are shown.
  - When: the user submits.
  - Then: if unanswered questions remain the button reads "Next" and jumps to the first unanswered; when all answered, submitting sends all answers and closes the panel; a Dismiss option closes without answering.

## Error input / restore

- **WS-059 — Agent error state with restore**
  - Given: the agent is in an error state and its workspace still exists.
  - When: viewing the input area.
  - Then: an error message with "Click here to try to restore the agent" is shown; clicking attempts restore.

- **WS-060 — Deleted-workspace error state**
  - Given: the agent errored and its workspace was deleted.
  - When: viewing the input area.
  - Then: a message states the workspace was deleted and cannot be restored (no restore link).

## Workspace peek

- **WS-061 — Peek popover on hover**
  - Given: workspace tabs are shown.
  - When: the user hovers a workspace tab for a moment.
  - Then: a peek popover appears showing status, agent list, PR info, branch, and diff stats.

- **WS-062 — Smooth peek transitions**
  - Given: a peek popover is open.
  - When: the user moves between tabs within the grace period.
  - Then: the popover content swaps instantly; leaving all tabs closes it after a short delay.

- **WS-063 — Expand more agents in peek**
  - Given: a workspace with more than 5 agents.
  - When: viewing its peek popover.
  - Then: only 5 agents show with a "+N more agents" button that reveals the rest.

- **WS-064 — Navigate from peek**
  - Given: the peek popover is open.
  - When: the user clicks an agent row or the header.
  - Then: the popover closes and the workspace/agent opens; clicking the branch copies it ("Copied!").

## Bottom bar & layout

- **WS-065 — Panel toggle buttons**
  - Given: not in zen mode.
  - When: viewing the bottom bar.
  - Then: toggle buttons for the left, bottom, and right panels and a focus-mode button are shown.

- **WS-066 — Toggle a panel from the bottom bar**
  - Given: a panel has content.
  - When: the user clicks its toggle button.
  - Then: the panel hides/shows and the button's active state updates.

- **WS-067 — Empty-panel toggle disabled**
  - Given: a panel has no content.
  - When: viewing/hovering its toggle button.
  - Then: the button is disabled with a "Panel is empty" tooltip and does nothing on click.

- **WS-068 — Panel toggle tooltips show keybinding**
  - Given: a panel toggle button.
  - When: the user hovers it.
  - Then: a tooltip shows the name and keybinding.

- **WS-069 — Diff split resize / collapse / expand**
  - Given: the diff panel is open beside the chat.
  - When: the user drags the divider.
  - Then: the panels resize; dragging past a threshold collapses the diff panel; an expand control maximizes the diff and collapses the chat, and vice-versa.

## Chat search bar (workspace-level)

- **WS-070 — Open chat search**
  - Given: a chat panel is visible.
  - When: the user presses `Cmd+Shift+F` (or `Cmd+F` in the chat).
  - Then: a search bar opens above the chat with its input focused.

- **WS-071 — Search and match counter**
  - Given: the chat search bar is open.
  - When: the user types a query.
  - Then: matches are highlighted and a "X/Y" counter is shown ("0/0" with the input turning red when none).

- **WS-072 — Navigate matches**
  - Given: search has matches.
  - When: the user presses Enter / Shift+Enter (or the up/down arrows).
  - Then: focus moves to the next / previous match.

- **WS-073 — Close chat search**
  - Given: the chat search bar is open.
  - When: the user presses Escape or clicks close.
  - Then: the search bar closes and highlights clear.

## Setup config & BTW popup

- **WS-074 — Setup config prompt**
  - Given: a workspace with no setup command configured.
  - When: viewing the chat intro.
  - Then: a prompt with a "Configure a workspace setup command" link is shown; clicking it opens settings to the repositories section.

- **WS-075 — BTW popup display & streaming**
  - Given: the user ran `/btw`.
  - When: the side chat processes.
  - Then: a draggable popup appears in the corner showing the question and the streamed answer (with a blinking cursor while streaming).

- **WS-076 — BTW popup drag / close / error**
  - Given: the BTW popup is open.
  - When: the user drags its handle / clicks close or Escape / an error occurs.
  - Then: it moves and stays within the viewport / closes and returns focus to the input / shows an error in red.

---

# CHAT — Chat interface, status, search, navigation, subagents, tasks

## Chat intro / empty state

- **CHAT-001 — Chat intro on empty conversation**
  - Given: a workspace with no messages.
  - When: the page loads.
  - Then: an intro card shows the project/branch, workspace name, agent name, creation time, source-branch info, a shared-code warning, and a `/sculptor:help` hint.

- **CHAT-002 — Intro reflects workspace type**
  - Given: the workspace is in-place / branched / cloned.
  - When: the intro renders.
  - Then: it shows "Working directly in {branch}", "Branched off {branch}", or "Cloned {branch} from {project}" accordingly.

- **CHAT-003 — Setup status card in intro**
  - Given: the workspace has pending setup commands.
  - When: the intro renders.
  - Then: a setup status card appears below the intro showing the setup step, progress, and elapsed time.

- **CHAT-004 — Setup card controls**
  - Given: the setup status card is shown.
  - When: the user hovers/clicks it.
  - Then: a popover reveals the setup command, output, and edit/play/stop controls; running shows live scrolling output; success shows a checkmark; failure shows an error.

## Status pill

- **CHAT-005 — Status pill hidden when idle**
  - Given: the agent is idle with no tasks.
  - When: viewing the chat.
  - Then: no status pill is shown.

- **CHAT-006 — Status pill states**
  - Given: the agent is active.
  - When: it transitions between phases.
  - Then: the pill shows "Thinking…", "Streaming…", "Calling Tools…", "Waiting on agent…", "Compacting…", or "Stopped" with an animated icon and a live elapsed-time counter (frozen when stopped/compacting/complete).

- **CHAT-007 — Task progress in pill**
  - Given: a plan with tasks exists and the agent is active.
  - When: the pill renders.
  - Then: it shows "X / N · {task subject}".

- **CHAT-008 — All-tasks-complete celebration**
  - Given: all tasks reach completed.
  - When: the last task completes.
  - Then: the pill shows "X of N done" without a timer and lingers briefly.

- **CHAT-009 — Stop button in pill**
  - Given: the agent is running and supports interruption.
  - When: the pill is shown.
  - Then: a square stop button is shown (with a "Stop (Ctrl+C)" tooltip); clicking it or pressing Ctrl+C interrupts; if interruption is unsupported the button is disabled with an explanatory tooltip.

- **CHAT-010 — Task graph on pill hover/click**
  - Given: the pill with tasks is shown.
  - When: the user hovers (or clicks to pin) the pill.
  - Then: a popover shows the task graph with nodes colored by status (completed/in-progress/pending); clicking again or outside closes it.

## Agent tasks panel & graph

- **CHAT-011 — Tasks empty state**
  - Given: no plan/tasks.
  - When: the tasks popover opens.
  - Then: a "No tasks" message is shown.

- **CHAT-012 — Task list with status icons**
  - Given: tasks exist.
  - When: the panel opens.
  - Then: a scrollable list shows each task's status icon (checkmark/bar/box), subject, and description, colored green/blue/outline for completed/in-progress/pending.

- **CHAT-013 — Pending tasks fade downstream**
  - Given: an in-progress task with downstream pending tasks.
  - When: the panel renders.
  - Then: downstream pending tasks fade with distance.

- **CHAT-014 — Waiting/blocked badge**
  - Given: a task is blocked by others.
  - When: it is shown.
  - Then: a "Waiting on #1, #2 (+N more)" badge is shown.

- **CHAT-015 — Graph compact vs normal**
  - Given: 15+ tasks vs fewer.
  - When: the panel opens.
  - Then: the graph renders in compact mode (small nodes) for 15+ tasks, larger nodes otherwise.

- **CHAT-016 — Expand a task**
  - Given: a task with a description.
  - When: the user clicks the task row.
  - Then: the row expands to show the full description/active form.

## In-chat search

- **CHAT-017 — Open in-chat search**
  - Given: the chat is loaded.
  - When: the user opens search (`Cmd+F`).
  - Then: a search bar slides in at the top with the input focused and selected.

- **CHAT-018 — Search results & highlight**
  - Given: the search bar is open.
  - When: the user types a query.
  - Then: an "active/total" count is shown and matches are highlighted; the active match scrolls into view.

- **CHAT-019 — Next/previous match with wrap**
  - Given: matches exist.
  - When: the user presses Enter / Shift+Enter (or clicks next/prev).
  - Then: the active match advances/retreats, wrapping at the ends.

- **CHAT-020 — Close in-chat search**
  - Given: the search bar is open.
  - When: the user presses Escape or clicks close.
  - Then: the bar closes, focus returns to the chat, and highlights clear.

- **CHAT-021 — Search auto-closes on task switch**
  - Given: search is open with a query.
  - When: the user navigates to a different agent/task.
  - Then: the search bar closes automatically.

- **CHAT-022 — Auto-scroll suppressed during search**
  - Given: the agent is streaming and search is open.
  - When: new messages arrive.
  - Then: the chat does not jump to the bottom while searching.

## Jump-to-bottom & scrolling

- **CHAT-023 — Jump button hidden at bottom**
  - Given: the chat is scrolled to the bottom.
  - When: at rest.
  - Then: no jump-to-bottom button is shown.

- **CHAT-024 — Jump button appears when scrolled up**
  - Given: the user scrolled up.
  - When: after a short debounce.
  - Then: a "Jump" button with a down-arrow appears at the bottom-right.

- **CHAT-025 — "New activity" label while streaming**
  - Given: the user is scrolled up and the agent is streaming.
  - When: new content arrives below the viewport.
  - Then: the button label changes to "New activity", reverting to "Jump" after streaming.

- **CHAT-026 — Click jump-to-bottom**
  - Given: the jump button is visible.
  - When: the user clicks it.
  - Then: the chat smoothly scrolls to the latest message and the button disappears.

- **CHAT-027 — Auto-scroll engagement**
  - Given: the chat is at the bottom and the agent is streaming.
  - When: new messages arrive.
  - Then: the chat auto-scrolls; scrolling up disengages auto-scroll; returning to the bottom re-engages it.

- **CHAT-028 — Scroll position persists per task**
  - Given: the user scrolled to a position.
  - When: they switch to another agent/task and back.
  - Then: the scroll position is restored.

- **CHAT-029 — Viewport stability on resize / density toggle**
  - Given: a message above the viewport changes height (or tool density toggles).
  - When: the change occurs.
  - Then: the currently viewed message stays anchored without jumping.

## Prompt navigator (dot rail)

- **CHAT-030 — Dot rail visibility**
  - Given: the chat has user messages.
  - When: the chat loads.
  - Then: a vertical dot rail appears on the right edge with one dot per user prompt (hidden when there are none).

- **CHAT-031 — Active dot & navigation**
  - Given: multiple prompts.
  - When: the user clicks a dot.
  - Then: the chat scrolls to that prompt and the dot becomes active.

- **CHAT-032 — Dot preview popover**
  - Given: the dot rail is shown.
  - When: the user hovers a dot.
  - Then: a popover shows "PROMPT N", the full prompt text, and a copy button; the popover switches instantly between dots while hovering.

- **CHAT-033 — Collapsed rail with many prompts**
  - Given: many user messages with limited height.
  - When: the rail renders.
  - Then: a "+N" collapsed indicator appears; clicking it expands the rail, and clicking outside collapses it.

- **CHAT-034 — Copy prompt from rail**
  - Given: a dot popover (or its right-click menu).
  - When: the user clicks copy / "Copy prompt".
  - Then: the prompt text is copied (copy icon shows a checkmark briefly).

## Subagents

- **CHAT-035 — Subagent pill while running**
  - Given: a subagent is running.
  - When: its pill renders.
  - Then: an animated icon, the subagent prompt text, and a live elapsed time are shown.

- **CHAT-036 — Subagent pill completed**
  - Given: a subagent finished.
  - When: its pill renders.
  - Then: a result icon replaces the animation and the elapsed time is frozen.

- **CHAT-037 — Subagent popover**
  - Given: a subagent pill.
  - When: the user clicks it (or hovers).
  - Then: a popover shows the prompt, the nested tools the subagent used, and its response (rendered markdown); Escape closes it.

- **CHAT-038 — Subagent keyboard navigation**
  - Given: a subagent popover is open in a row.
  - When: the user presses arrow keys.
  - Then: focus moves left/right through nested tool pills and up/down to adjacent rows.

## Turn footer

- **CHAT-039 — Turn footer metrics**
  - Given: an assistant turn finished.
  - When: viewing the footer.
  - Then: it shows the duration, a "Stopped" label if interrupted, the token count, context usage %, and a "N files changed" link, separated by bullets.

- **CHAT-040 — Token breakdown popover**
  - Given: a token count is shown.
  - When: the user clicks it.
  - Then: a popover breaks down input, output, reasoning tokens, and the context current/threshold.

- **CHAT-041 — Files-changed popover & open diff**
  - Given: a turn changed files.
  - When: the user clicks "N files changed" and then a file.
  - Then: a list of modified files with status badges is shown; clicking a file opens its diff in the side panel.

## Ask-user-question block (in-chat history)

- **CHAT-042 — Answered question in history**
  - Given: a question was answered.
  - When: viewing it in the chat history.
  - Then: it shows the selected options as static text (custom text in a code block), with no inputs.

- **CHAT-043 — Dismissed question in history**
  - Given: a question was dismissed.
  - When: viewing it.
  - Then: a "DISMISSED" badge is shown and the options appear dimmed.

## Debug chat view

- **CHAT-044 — Debug view content**
  - Given: Debug View is enabled for an agent.
  - When: viewing the chat.
  - Then: each message is listed with role, id, timestamp, and block types; tool_use/tool_result names are listed.

- **CHAT-045 — Debug timestamp toggle**
  - Given: the debug view shows timestamps.
  - When: the user clicks a timestamp.
  - Then: it toggles between relative and absolute formats.

- **CHAT-046 — Capability-gated model picker / Pi model catalog**
  - Given: agents whose harness does and doesn't support model selection.
  - When: the user opens the model picker on each (a Claude agent, a Pi agent, and a terminal agent).
  - Then: a Claude agent lists Claude models; a Pi agent lists Pi's own models grouped by provider (a single provider flat, two or more cascading into per-provider submenus), and a Pi agent with no authenticated providers shows the model picker disabled ("No models available") instead of a list — including when a model had previously been selected, where the now-unusable selection is dropped so the picker still empties — with the single fix-it action on the Send button, which is replaced by a "Go to harness configuration" button; a terminal agent shows the picker disabled with the current model; switching a Pi model that the harness rejects leaves the selection unchanged and shows an error toast.

---

# MSG — Message & tool-content rendering

## Messages

- **MSG-001 — Assistant message grouping**
  - Given: an assistant message with mixed content.
  - When: it renders.
  - Then: text, tools, errors, warnings, context summaries, and files are grouped and shown in order.

- **MSG-002 — Streaming cursor**
  - Given: the agent is streaming text in the last message.
  - When: text is arriving.
  - Then: a blinking cursor is shown at the end of the streamed content.

- **MSG-003 — User message text & timestamp**
  - Given: a user message.
  - When: it renders.
  - Then: the text renders as markdown with a human-readable timestamp below.

- **MSG-004 — Copy a user message**
  - Given: a user message with text.
  - When: the user hovers it and clicks copy.
  - Then: the text is copied (icon shows a checkmark for ~1.5s).

- **MSG-005 — User message attachments & "via" badge**
  - Given: a user message with files and/or a `sentVia` method.
  - When: it renders.
  - Then: file previews are shown and a "via {method}" badge appears above the message when applicable.

## Markdown

- **MSG-006 — Markdown elements render**
  - Given: assistant/user text with markdown.
  - When: it renders.
  - Then: paragraphs, headings, ordered/unordered lists (markers preserved), and emoji render correctly.

- **MSG-007 — Links open externally**
  - Given: a markdown link.
  - When: the user clicks it.
  - Then: it opens in a new browser tab (external).

- **MSG-008 — Images suppressed**
  - Given: a markdown image.
  - When: it renders.
  - Then: the image is not displayed.

- **MSG-009 — Inline file-path linkification**
  - Given: text/inline-code containing a workspace file path.
  - When: it renders.
  - Then: the path becomes a clickable link (monospace); clicking (or Enter/Space when focused) opens the file in the diff/file view.

- **MSG-010 — Blockquote with copy**
  - Given: a markdown blockquote.
  - When: the user hovers it and clicks copy.
  - Then: the quoted text (with "> " prefixes) is copied (checkmark for ~1.5s).

## Code blocks

- **MSG-011 — Code block plain → highlighted**
  - Given: a fenced code block with a language.
  - When: it first renders, then syntax highlighting loads.
  - Then: it shows as plain monospace then swaps to colored tokens with no layout shift.

- **MSG-012 — Copy code block**
  - Given: a code block.
  - When: the user hovers it and clicks copy.
  - Then: the (trimmed) code is copied (checkmark for ~1.5s).

- **MSG-013 — Code search highlight**
  - Given: an active chat search with matches inside code.
  - When: rendered.
  - Then: matches are highlighted over the syntax coloring.

## Tables

- **MSG-014 — Table horizontal scroll & wrap toggle**
  - Given: a wide table.
  - When: it renders / the user hovers and clicks the wrap toggle.
  - Then: the table scrolls horizontally with fade indicators; toggling switches to wrapped cells (fades disappear) and back.

- **MSG-015 — Copy table as markdown**
  - Given: a table.
  - When: the user hovers it and clicks copy.
  - Then: the table is copied as markdown (checkmark for ~1.5s).

## Tool pills & rows

- **MSG-016 — Tool pill icon & label**
  - Given: a tool call.
  - When: it renders.
  - Then: a pill shows the tool-specific icon (Bash terminal, Read file, Edit pencil, Grep search, etc.; a wrench fallback for unknown tools) and label.

- **MSG-017 — Executing tool indicator**
  - Given: a command-style tool (Bash/Monitor) is running.
  - When: the pill renders.
  - Then: a pulsing dot replaces the icon while it runs.

- **MSG-018 — Tool pill error state**
  - Given: a tool finished with an error.
  - When: the pill renders.
  - Then: it shows error styling (red).

- **MSG-019 — Open a tool popover**
  - Given: a tool pill.
  - When: the user clicks it (or hovers in default density).
  - Then: a popover opens with the tool's details; clicking pins it, clicking again unpins, scrolling the chat closes it, Escape closes it.

- **MSG-020 — Tool pill keyboard navigation**
  - Given: a focused tool pill / open popover.
  - When: the user presses arrow keys.
  - Then: focus moves between pills in the row and across rows.

- **MSG-021 — Expanded tool density**
  - Given: tool density is "expanded".
  - When: a tool row renders.
  - Then: each tool is a full-width row with inline icon, label, title, and meta (duration/line count); clicking opens the popover (no hover-open).

- **MSG-022 — Tool popover: Read**
  - Given: a Read tool result.
  - When: the popover opens.
  - Then: it shows the file path (with optional line range and an outside-workspace icon+tooltip), line-count meta, copy-path and open-in-Sculptor actions, and the file content.

- **MSG-023 — Tool popover: Bash/Monitor**
  - Given: a Bash/Monitor tool.
  - When: the popover opens.
  - Then: it shows an optional description, the command (code style), live/elapsed duration, a copy-command action, and auto-scrolling output (with a streaming cursor while running) and a copy-output action.

- **MSG-024 — Tool popover: Grep**
  - Given: a Grep tool.
  - When: the popover opens.
  - Then: it shows the quoted pattern, search path, match-count meta, and matching lines.

- **MSG-025 — Bash status badge**
  - Given: a Bash tool.
  - When: it renders.
  - Then: a badge shows running (elapsed + spinner), success (duration + checkmark), error (duration + X), or background (with an arrow icon).

## File chips (diff tools)

- **MSG-026 — File chip stats**
  - Given: a Write/Edit tool.
  - When: the chip renders.
  - Then: it shows the filename with green "+N" (and red "−N" unless a new file); skeletons show while stats load.

- **MSG-027 — File chip executing/error**
  - Given: the file tool is running or errored.
  - When: the chip renders.
  - Then: it shows "Writing…"/"Editing…" (disabled) or error styling.

- **MSG-028 — File chip diff popover**
  - Given: a finished file chip.
  - When: the user clicks it (or hovers).
  - Then: a popover shows the file path and a syntax-highlighted unified diff with word-level highlights; it offers open-in-diff-panel (or open-in-file-view for plan/outside-workspace files) and copy-path; scrolling the chat closes it.

## Other blocks

- **MSG-029 — Error block**
  - Given: an error block.
  - When: it renders.
  - Then: a red badge with the error type and message is shown; clicking expands a traceback (when present).

- **MSG-030 — Claude-binary-missing error**
  - Given: a Claude-binary-not-found error.
  - When: it renders.
  - Then: a special layout with installation status and a link to the dependencies settings is shown (with a "Claude installed" badge when applicable).

- **MSG-031 — Retry request**
  - Given: an error is the last message and the task is not in a terminal error state.
  - When: viewing the block.
  - Then: a red "Retry Request" button is shown; clicking retries and then disables with an "already retried" tooltip.

- **MSG-032 — Warning block**
  - Given: a warning block.
  - When: it renders.
  - Then: an orange badge with the type/message is shown; clicking expands a traceback when present (non-clickable when none).

- **MSG-033 — Context summary**
  - Given: a context-compaction/clearing event.
  - When: it renders.
  - Then: a pill with a label and a truncated preview is shown; clicking opens a scrollable popover with the full summary as markdown.

- **MSG-034 — Exit-plan-mode block states**
  - Given: a plan review block.
  - When: it renders.
  - Then: it shows the appropriate state — "Plan ready for review" (pulsing dot, click opens the plan file), inline plan markdown when provided, "Plan approved" (green), "Plan review dismissed" (gray), "Plan revision requested" (orange, expandable feedback), or "Plan reviewed" (historical, no actions).

- **MSG-035 — Outside-workspace icon**
  - Given: a tool result file path outside the workspace.
  - When: it renders.
  - Then: a folder-output icon appears with a "Path outside of the workspace" tooltip.

- **MSG-036 — Search-match highlight in messages**
  - Given: an active chat search.
  - When: messages render.
  - Then: all matches are highlighted, with the active occurrence styled distinctly.

- **MSG-037 — Copy an image from the conversation**
  - Given: an image is shown in the conversation (in a message, the attachment preview, or the zoomed lightbox).
  - When: the user right-clicks the image and chooses "Copy Image".
  - Then: the image is copied to the clipboard.

---

# PANEL — Workspace side panels

## File browser

- **PANEL-001 — Browse / Changes / Commits tabs**
  - Given: the file browser panel.
  - When: the user clicks the Browse, Changes, or Commits tab.
  - Then: the corresponding view is shown; Changes and Commits show a count badge when there are changes/commits.

- **PANEL-002 — Review all**
  - Given: changes/commits exist and the Review-all feature is enabled.
  - When: the user clicks "Review all".
  - Then: a combined diff tab opens showing all files.

- **PANEL-003 — Toggle tree/flat view**
  - Given: a file list view.
  - When: the user clicks the tree/list toggle.
  - Then: the list switches between a nested tree and a flat list.

- **PANEL-004 — Collapse all folders**
  - Given: a tree with expanded folders.
  - When: the user clicks collapse-all.
  - Then: all folders collapse.

- **PANEL-005 — Refresh file tree**
  - Given: the file tree.
  - When: the user clicks refresh.
  - Then: the icon spins and the tree re-fetches.

- **PANEL-006 — File search**
  - Given: the Browse tab.
  - When: the user clicks the search icon and types.
  - Then: the header becomes a search input, the list filters in real time, ancestor folders of matches auto-expand, and "No matches" shows when empty; Escape/close exits search.

- **PANEL-007 — Expand/collapse folders**
  - Given: a folder in the tree.
  - When: the user clicks its chevron/row.
  - Then: it expands/collapses to show/hide children.

- **PANEL-008 — Open a file**
  - Given: a file in the tree/flat list.
  - When: the user clicks it.
  - Then: a diff view tab opens for that file.

- **PANEL-009 — Tree keyboard navigation**
  - Given: the tree is focused.
  - When: the user presses arrows / Enter.
  - Then: Up/Down move between visible rows, Right/Left expand/collapse folders, Enter opens the focused file.

- **PANEL-010 — File status & stats**
  - Given: files with git status.
  - When: shown in the tree.
  - Then: each shows a status letter (M/A/D/R) with a color, +added/−removed stats, a change-count badge on folders, an error badge on processing errors, and strike-through styling for deletions.

- **PANEL-011 — Focus highlight on agent file activity**
  - Given: the agent operates on a file.
  - When: the file appears in the tree.
  - Then: the tree scrolls to it, expands its ancestors, and highlights the row.

- **PANEL-012 — File context menu**
  - Given: a file/folder in the tree.
  - When: the user right-clicks it.
  - Then: a menu offers Open diff view, View file, Copy file path, Copy relative path, Open in OS, and (folders) Expand all / Collapse all, plus Close tab / Close other tabs when a diff tab is open — each performing its labeled action.

- **PANEL-013 — Empty / loading file tree**
  - Given: no files / the tree is loading.
  - When: the Browse tab is shown.
  - Then: "No files yet" / animated skeleton rows are shown.

## Changes & commit

- **PANEL-014 — Diff scope picker**
  - Given: the Changes tab with a target branch.
  - When: the user picks "All" vs "Uncommitted".
  - Then: the list shows all changes vs target or only uncommitted changes, with counts per segment.

- **PANEL-015 — Discard a change**
  - Given: a changed file with a discard control.
  - When: the user clicks it and confirms in the dialog.
  - Then: the file reverts to HEAD and leaves the changes list; Cancel keeps it.

- **PANEL-016 — Commit button states**
  - Given: the Changes tab.
  - When: changes exist / none exist.
  - Then: "Commit N changes" is enabled / disabled accordingly.

- **PANEL-017 — Quick commit**
  - Given: the commit button is enabled.
  - When: the user clicks it.
  - Then: the default commit prompt is sent to the agent.

- **PANEL-018 — Edit commit prompt**
  - Given: the commit button.
  - When: the user right-clicks it and chooses "Edit prompt…", edits, and saves.
  - Then: the commit prompt updates and the dialog closes.

## History

- **PANEL-019 — History loading / empty / error**
  - Given: the Commits tab.
  - When: history is loading / absent / failed.
  - Then: "Loading history…" / "No history available" / an error message is shown.

- **PANEL-020 — Commit graph & entries**
  - Given: commits loaded.
  - When: the tab renders.
  - Then: a commit graph with dots/lines is shown; each entry shows the first line of the message, file count, +/− stats, relative time, and short hash.

- **PANEL-021 — Expand commit files**
  - Given: a commit entry.
  - When: the user clicks it.
  - Then: it expands to list the files in that commit (each with status and stats); clicking again collapses.

- **PANEL-022 — Commit hover popover & copy hash**
  - Given: a commit entry.
  - When: the user hovers it.
  - Then: a popover shows the full message, author, date, full hash with a copy button, and stats; clicking copy copies the hash with a "Copied" indicator.

- **PANEL-023 — Open a commit's file diff**
  - Given: a commit is expanded.
  - When: the user clicks a file.
  - Then: a diff tab opens comparing that file in the commit vs its parent.

- **PANEL-024 — Merge commits & terminus**
  - Given: a merge commit / the end of history.
  - When: rendered / expanded.
  - Then: a merge indicator allows expanding the second-parent branch chain; a terminus/fork-point indicator is shown at the bottom.

## Diff panel / viewer

- **PANEL-025 — Diff tabs**
  - Given: files opened in the diff panel.
  - When: the user opens/switches/closes tabs.
  - Then: each file opens in a tab, clicking switches, the X closes (activating MRU or adjacent per setting); right-click offers Close other / Close all; tabs can be reordered; labels show the filename (full path on hover).

- **PANEL-026 — Diff view controls**
  - Given: a diff is shown.
  - When: the user toggles split/unified, line-wrapping, find, or expand.
  - Then: the layout switches side-by-side/unified, wraps or scrolls long lines, opens an in-file search, or expands the diff to full width (hiding the file browser); a close control closes the panel.

- **PANEL-027 — Diff file header**
  - Given: a diff tab.
  - When: it renders.
  - Then: it shows the breadcrumb path, filename, +/− stats, and a three-dot menu with file operations.

- **PANEL-028 — Special file states**
  - Given: a renamed/deleted/binary file.
  - When: the diff renders.
  - Then: a "Renamed from X to Y" banner, a "Deleted" banner, or a "Binary file (cannot display)" message is shown.

- **PANEL-029 — Large-diff truncation**
  - Given: a diff exceeding the line threshold.
  - When: it renders.
  - Then: a truncated diff with a "Show full diff" button is shown; clicking renders the full diff.

- **PANEL-030 — In-file search**
  - Given: a diff is shown.
  - When: the user opens find and types.
  - Then: matches are highlighted with an "X of Y" counter; Enter/Shift+Enter (or arrows) navigate; Escape/close closes it.

- **PANEL-031 — File view (full content)**
  - Given: a file opened via "View file".
  - When: the tab renders.
  - Then: the full file content is shown read-only with syntax highlighting (not a diff).

- **PANEL-032 — Combined diff view**
  - Given: the Review-all combined diff is open.
  - When: it renders.
  - Then: each file is a collapsible section with breadcrumb and +/− stats; expand/collapse-all and a "Commit N changes" button are available.

- **PANEL-033 — Markdown render toggle**
  - Given: a markdown file in the diff (rich-rendering feature).
  - When: the toggle is available.
  - Then: the user can switch between source and rendered views (toggle disabled with a hint when the feature is off).

## Terminal panel

- **PANEL-034 — Terminal tabs**
  - Given: the terminal panel.
  - When: the user clicks + / switches / double-clicks to rename / closes a tab.
  - Then: a new "Terminal N" is created / the selected terminal is shown / an inline rename input appears (Enter confirms, Escape cancels) / the tab closes (closing the last one creates a fresh replacement); right-click offers "Close others"; tabs can be reordered.

- **PANEL-035 — Terminal interaction**
  - Given: an active terminal.
  - When: the user types a command.
  - Then: input goes to the shell and output is displayed; scrollback is available.

- **PANEL-036 — Terminal unread badge**
  - Given: output arrives in a non-active terminal tab.
  - When: it occurs.
  - Then: a pulsing unread dot appears on that tab, cleared when switching to it.

- **PANEL-037 — Terminal starting state**
  - Given: a terminal is starting.
  - When: the panel mounts.
  - Then: a "Starting terminal…" message is shown.

## Notes panel

- **PANEL-038 — Edit & persist notes**
  - Given: the notes panel.
  - When: the user types.
  - Then: the content updates and is preserved when switching away and back.

- **PANEL-039 — Add notes to prompt**
  - Given: notes with content.
  - When: the user clicks "Add notes to prompt".
  - Then: the notes are inserted into the chat prompt; if the prompt already has text, a conflict dialog offers how to merge.

- **PANEL-040 — Copy notes / disabled states**
  - Given: the notes panel.
  - When: notes have content / are empty.
  - Then: the copy button copies the text / is disabled; "Add to prompt" is disabled when there are no notes or no task.

## Skills panel

- **PANEL-041 — Skill type sections**
  - Given: skills loaded.
  - When: the panel renders.
  - Then: skills are grouped by type (Custom, Sculptor, Built-in) with collapsible headers; collapsed headers show a count badge.

- **PANEL-042 — Skill hover popover**
  - Given: a skill chip.
  - When: the user hovers it.
  - Then: a popover shows the description; hovering another chip swaps content instantly; leaving closes it after a short delay.

- **PANEL-043 — Invoke a skill**
  - Given: a skill chip.
  - When: the user clicks it.
  - Then: `/skill-name` is inserted into the chat input.

- **PANEL-044 — Open skill in Sculptor**
  - Given: a custom/sculptor skill popover.
  - When: the user clicks "open in Sculptor".
  - Then: a file-view tab opens showing the skill file (built-in skills have no such option).

- **PANEL-045 — Skills search & filter**
  - Given: the skills panel.
  - When: the user opens search and types, navigates with arrows, presses Enter, or filters by type.
  - Then: the list filters in real time, the selection moves and auto-scrolls, Enter inserts the selected skill, Escape closes search, and the type-filter popover toggles which types are shown (active filters highlight the icon).

- **PANEL-046 — Skills empty / loading / error / unavailable**
  - Given: skills are loading / failed / none exist / unsupported / the agent is running.
  - When: the panel renders.
  - Then: "Loading…" / an error / "No skills found" / "Skills unavailable" is shown, and chips appear disabled while the agent is running.

## Actions panel

- **PANEL-047 — Action groups**
  - Given: actions with groups.
  - When: the panel renders.
  - Then: collapsible group headers (with count badges when collapsed) are shown, the built-in "Sculptor" group first, and ungrouped actions at the bottom.

- **PANEL-048 — Trigger an action**
  - Given: an action chip.
  - When: the user clicks it.
  - Then: an auto-submit action sends its prompt immediately; a manual action appends its prompt to the input; chips are disabled while the agent is running.

- **PANEL-049 — Queue an action**
  - Given: the agent is running and an action chip's context menu.
  - When: the user chooses "Queue message".
  - Then: the action prompt is queued instead of auto-submitted.

- **PANEL-050 — Add / edit / delete an action**
  - Given: the actions panel.
  - When: the user adds (+), edits, or deletes an action via the menu.
  - Then: an action dialog opens for add/edit (Save persists), and delete shows a confirmation; built-in actions offer no edit/delete.

- **PANEL-051 — Group management**
  - Given: the actions panel.
  - When: the user adds a group, renames a group inline, or deletes a custom group.
  - Then: a group is created (Enter confirms, Escape cancels), renamed (Enter/blur confirms), or deleted via a confirmation dialog.

- **PANEL-052 — Reorder actions & groups by drag**
  - Given: custom actions/groups.
  - When: the user drags an action or group.
  - Then: a drop indicator appears and the order updates on drop; actions can be moved between groups; built-in items are not draggable.

## Browser panel

- **PANEL-053 — Browser controls (desktop)**
  - Given: the browser panel in the desktop app.
  - When: the user enters a URL and presses Enter / clicks back / forward / reload / screenshot.
  - Then: it navigates to the URL / goes back / forward / reloads / copies a screenshot to the clipboard; back/forward/screenshot are disabled when unavailable.

- **PANEL-054 — Browser URL behavior & errors**
  - Given: the address bar.
  - When: the page navigates or an invalid URL is entered.
  - Then: the address bar follows navigation, the URL is selected on focus, an invalid URL shows an error banner, and an empty URL submit does nothing.

- **PANEL-055 — Browser web-mode placeholder**
  - Given: not running in the desktop app.
  - When: the browser panel is shown.
  - Then: a "Browser panel requires the desktop app" placeholder is shown with controls disabled.

## Panel state persistence

- **PANEL-056 — Panel state persists**
  - Given: the user has set folder-expansion, scroll position, active tab, view mode, diff view type, line-wrapping, and diff scope.
  - When: switching tabs/files and returning.
  - Then: each of these states is restored.

## Extension panels

- **PANEL-057 — Extension-contributed panel appears with a badge**
  - Given: the bundled Linear extension (enabled by default) is loaded and contributes a panel.
  - When: the user views the Panels list and opens the extension's panel.
  - Then: the panel is listed with an "extension" badge and renders its content when opened.

---

# CMDP — Command palette

## Opening, closing, search

- **CMDP-001 — Open the palette**
  - Given: the app is open on any page.
  - When: the user presses `Cmd+K` (or clicks the command icon).
  - Then: the palette opens with the input focused, commands grouped (Workspaces → Navigation → Theme & Layout → Chat → Terminal → Help), and the first row selected.

- **CMDP-002 — Open directly to the workspace switcher**
  - Given: the app is open.
  - When: the user presses `Cmd+P`.
  - Then: the palette opens on the "Go to workspace" sub-page with placeholder "Find a workspace…".

- **CMDP-003 — Toggle closed**
  - Given: the palette is open.
  - When: the user presses `Cmd+K` again.
  - Then: the palette closes without running a command.

- **CMDP-004 — Filter commands**
  - Given: the palette is open at root.
  - When: the user types a query (e.g., "theme").
  - Then: matching commands are shown (fuzzy/keyword, case-insensitive), non-matching rows and empty groups hide, and groups reorder by best match.

- **CMDP-005 — No matches**
  - Given: the palette is open.
  - When: the user types a query with no matches.
  - Then: an empty state "No matches for '{query}'" is shown.

- **CMDP-006 — Clear search restores all**
  - Given: the palette has a query.
  - When: the user clears the input.
  - Then: all commands reappear in group order with the first row selected.

- **CMDP-007 — Escape behavior**
  - Given: the palette is open.
  - When: the user presses Escape.
  - Then: a non-empty search clears first; an empty search at root closes the palette; on a sub-page it returns to root without closing.

- **CMDP-008 — Click outside closes**
  - Given: the palette is open with no pending command.
  - When: the user clicks the overlay.
  - Then: the palette closes.

## Keyboard navigation & pages

- **CMDP-009 — Arrow navigation with wrap**
  - Given: results are showing.
  - When: the user presses Down/Up.
  - Then: the selection moves and scrolls into view, wrapping at the ends.

- **CMDP-010 — Run a command**
  - Given: a command is selected.
  - When: the user presses Enter (or clicks it).
  - Then: it runs and the palette closes (unless the command keeps the palette open).

- **CMDP-011 — Run and keep open**
  - Given: a command is selected.
  - When: the user presses `Cmd+Enter`.
  - Then: it runs, the palette stays open, and focus returns to the input.

- **CMDP-012 — Enter / exit a sub-page**
  - Given: a page-opener command is selected (chevron shown).
  - When: the user presses Tab / ArrowRight (caret at input end) to enter, or Shift+Tab / ArrowLeft (caret at start) / Backspace (empty) to exit.
  - Then: the sub-page opens with a breadcrumb and updated placeholder / it returns to root; the search clears on navigation.

- **CMDP-013 — Breadcrumb on sub-pages**
  - Given: a sub-page is open.
  - When: viewing the header.
  - Then: a breadcrumb shows the page title with an X to return to root (no breadcrumb at root).

- **CMDP-014 — Disabled rows & tooltips**
  - Given: a command is unavailable in the current context.
  - When: viewing/hovering the row.
  - Then: it is greyed out and shows a reason (as a subtitle or hover tooltip), e.g., "Only one agent in this workspace", "No uncommitted changes".

- **CMDP-015 — Shortcut hints & chevrons**
  - Given: rows with a keybinding or sub-page.
  - When: viewing them.
  - Then: a key-badge shortcut and/or a right chevron appears in the trailing area (group label shown during search when no shortcut).

- **CMDP-016 — Async command spinner & close-block**
  - Given: a command performs async work.
  - When: it runs.
  - Then: the row shows a spinner; the palette refuses to close until it completes (or times out after ~30s).

## Built-in commands

- **CMDP-017 — Navigation commands**
  - Given: the palette is open.
  - When: the user runs Open home / Open settings / New workspace / New agent.
  - Then: the app navigates home / to settings / to new-workspace / creates and opens a new agent (New agent is disabled off a workspace).

- **CMDP-018 — Theme commands**
  - Given: the palette is open.
  - When: the user runs "Toggle theme" or opens "Switch theme…" and picks Light/Dark/System.
  - Then: the theme flips or is set accordingly.

- **CMDP-019 — Layout & panel commands**
  - Given: the palette is open on a workspace.
  - When: the user opens "Toggle layout…" / "Toggle panel visibility…" and runs toggle-left/right/bottom-panel, focus mode, zen mode, or a specific panel toggle.
  - Then: the corresponding panel/mode toggles (panel toggles keep the palette open; focus/zen close it).

- **CMDP-020 — Chat commands**
  - Given: the palette is open on a workspace with a chat panel.
  - When: the user runs Focus chat input / Search within chat / Jump to bottom / Toggle tool-call density.
  - Then: the input focuses / chat search opens / chat scrolls to bottom / tool rows expand or compact (the row label reflects the next action); chat commands are hidden without a chat panel.

- **CMDP-021 — Terminal & help commands**
  - Given: the palette is open.
  - When: the user runs Clear terminal / Show keyboard shortcuts / Report a problem.
  - Then: the terminal clears (hidden without a terminal panel) / the shortcuts dialog opens / the feedback form opens.

## Workspace & agent commands

- **CMDP-022 — Go to workspace switcher**
  - Given: 2+ workspaces.
  - When: the user opens "Go to workspace…" and selects one.
  - Then: a list with status dots is shown (the current workspace disabled as "Current workspace"); selecting another navigates to it.

- **CMDP-023 — Workspace tab navigation**
  - Given: 2+ workspace tabs.
  - When: the user runs Next/Previous workspace tab.
  - Then: focus moves to the next/previous tab.

- **CMDP-024 — Workspace actions sub-page**
  - Given: a workspace.
  - When: the user opens "Workspace actions…" and runs Commit changes / Create PR / Open PR / Rename / Close / Close others / Close all / Delete.
  - Then: each performs its action (Commit disabled without changes; Open PR disabled without an open PR; Delete and others as labeled).

- **CMDP-025 — Open-in sub-page**
  - Given: external apps are available and the backend is local.
  - When: the user opens "Open in…" and selects Finder / VS Code / Terminal / etc.
  - Then: the repo opens in the chosen app (the preferred app ranks first); the entry is disabled on a remote backend.

- **CMDP-026 — Go to agent switcher**
  - Given: 2+ agents in a workspace.
  - When: the user opens "Go to agent…" and selects one.
  - Then: a list is shown (current agent disabled); selecting another navigates to it; the opener is disabled with only one agent.

- **CMDP-027 — Agent actions sub-page**
  - Given: an active agent.
  - When: the user opens "Agent actions…" and runs Rename / Mark unread / Delete.
  - Then: the rename dialog opens / the agent is marked unread / a delete confirmation appears.

- **CMDP-028 — Settings sub-page**
  - Given: the palette is open.
  - When: the user opens "Go to settings…" and selects a section (Appearance, Keybindings, Experimental, …).
  - Then: the app navigates to that settings section.

- **CMDP-029 — Pointer & open-time behavior**
  - Given: the palette opens while the cursor is over a row.
  - When: the first pointer move occurs / the user later hovers a row.
  - Then: the first move is ignored (keyboard selection stays); subsequent hovers select the hovered row.

- **CMDP-030 — List resets on open & on search change**
  - Given: the palette opens or the query changes.
  - When: it happens.
  - Then: the list scrolls to the top and the first row is selected.

- **CMDP-031 — Long titles truncate**
  - Given: an agent/workspace with a very long title.
  - When: listed in the palette.
  - Then: the title truncates with "…".

---

# SET — Settings page

## Navigation & common behaviors

- **SET-001 — Section navigation**
  - Given: the settings page.
  - When: the user clicks a sidebar item (or selects from the mobile dropdown).
  - Then: the active section changes and its content is shown; sections include General, Agent, Keybindings, Panels, Dependencies, Pi, Repositories, Git, CI, File Browser, Environment Variables, Privacy, Experimental, Actions, Theme Builder.

- **SET-002 — Deep-link to a section**
  - Given: a URL with a section parameter.
  - When: the settings page loads.
  - Then: it opens directly to that section.

- **SET-003 — Active section remembered**
  - Given: the user viewed a section.
  - When: they reopen settings.
  - Then: the last-viewed section is shown.

- **SET-004 — Save feedback toast**
  - Given: the user changes a setting.
  - When: it saves successfully / fails.
  - Then: a "Setting updated" success toast / a "Failed to update setting" error toast appears.

## General

- **SET-005 — Theme appearance**
  - Given: the General section.
  - When: the user picks Light / Dark / System.
  - Then: the app appearance changes immediately.

- **SET-006 — Update channel & check/install**
  - Given: the General section.
  - When: the user picks an update channel, clicks "Check for updates", or "Install and restart".
  - Then: a toast confirms the channel change, the check shows a spinner, and install restarts the app (button shows "Restarting…").

## Agent

- **SET-007 — Default model / fast mode / effort**
  - Given: the Agent section.
  - When: the user changes the default model, toggles fast mode, or selects an effort level.
  - Then: each shows "Setting updated" and applies to new agents.

## Keybindings

- **SET-008 — Search keybindings**
  - Given: the Keybindings section.
  - When: the user types in the search field.
  - Then: the list filters by name/description.

- **SET-009 — Assign a hotkey**
  - Given: a keybinding row.
  - When: the user clicks "Click to set" and presses a combination.
  - Then: it shows "Press keys… Esc to cancel" then records and displays the formatted hotkey.

- **SET-010 — Conflict detection**
  - Given: the user assigns a hotkey already in use.
  - When: the conflict is detected.
  - Then: a warning names the conflicting action with Reassign / Cancel options.

- **SET-011 — Clear / reset keybindings**
  - Given: a keybinding (or all).
  - When: the user clicks the X on a chip / "Reset all to defaults".
  - Then: that binding / all bindings revert to default.

## Panels

- **SET-012 — Panel zone assignment & hotkey**
  - Given: the Panels section.
  - When: the user changes a panel's zone or assigns a panel hotkey.
  - Then: the panel moves zones / the hotkey is set (with conflict checking); disabled where rules/enabled-state prevent it.

- **SET-013 — Enable/disable & reset panels**
  - Given: the Panels section.
  - When: the user toggles a non-builtin panel or clicks "Reset to defaults".
  - Then: the panel appears/disappears / all panel layout settings reset.

## Dependencies

- **SET-014 — Claude CLI source mode & status**
  - Given: the Dependencies section.
  - When: the user switches Managed/Custom.
  - Then: the mode switches (brief settling spinner) and the status shows version/health (up to date, in/out of range, not installed, no path).

- **SET-015 — Claude managed install / custom path**
  - Given: the Dependencies section.
  - When: the user clicks Install/Retry (managed) or enters a path and clicks Apply (custom).
  - Then: a progress bar runs and the version updates / the path is validated and applied; active version and path are displayed.

- **SET-016 — Git status**
  - Given: the Dependencies section.
  - When: viewing the Git row.
  - Then: it shows "v{version} — Installed" or a not-installed message.

## Pi

- **SET-018 — Pi source mode, install, path, versions**
  - Given: the Pi section.
  - When: the user switches Managed/Custom, installs, or sets a custom path.
  - Then: the status (pinned/outside-pinned/not-installed/no-path), pinned & detected versions, active path, and install progress are shown; a custom-mode warning with an install command appears.

- **SET-019 — Pi API-key env vars**
  - Given: the Pi section.
  - When: the user adds or removes an env-var name.
  - Then: the variable list updates with a "Setting updated" toast.

## Repositories

- **SET-020 — Add / list repositories**
  - Given: the Repositories section.
  - When: the user clicks "Add repository".
  - Then: the add-repo dialog opens; the list shows each repo's name, path, agent count, and an accessibility warning when the path is missing.

- **SET-021 — Configure a repository**
  - Given: a repo row.
  - When: the user clicks Configure and edits the setup command or branch-naming pattern.
  - Then: the section expands; values save on blur, with "Using default"/"Reset to default" affordances for the setup command.

- **SET-022 — Remove a repository**
  - Given: a repo row.
  - When: the user clicks "Remove repo & agents" and confirms.
  - Then: a confirmation dialog (showing the agent count) deletes the repo on confirm (with a success/error toast).

## Git

- **SET-023 — Git settings**
  - Given: the Git section.
  - When: the user edits the PR-creation prompt, toggles PR status polling, sets poll interval (10–300s) and closed-workspace multiplier (1–120×), or sets the default target branch.
  - Then: each saves with a toast; polling fields disable when polling is off; values are validated to their ranges; the PR prompt has a reset-to-default.

- **SET-024 — Global defaults**
  - Given: the Git section.
  - When: the user edits the default branch-naming pattern or branch-deletion policy (Never / Delete if safe / Always).
  - Then: each saves with a toast.

## CI babysitter

- **SET-025 — CI babysitter settings**
  - Given: the CI section.
  - When: the user toggles the babysitter, sets the retry cap (1–10), or edits the pipeline-failed / merge-conflict prompts.
  - Then: each saves with a toast; the dependent fields disable when the babysitter is off; prompts have reset-to-default.

- **SET-039 — Babysitter agent selector**
  - Given: the CI section with the babysitter enabled.
  - When: the user opens the "Babysitter agent" selector.
  - Then: it offers "Most recently used" (default), Claude, Pi, and any registered terminal agent that accepts automated prompts; choosing one saves with a toast; the selector is disabled when the babysitter is off.

## File browser

- **SET-026 — File-browser settings**
  - Given: the File Browser section.
  - When: the user sets the default split ratio (20–80%), tab-close behavior, line-wrapping, default diff view, or the commit prompt.
  - Then: each saves with a toast (commit prompt has reset-to-default).

## Environment variables

- **SET-027 — Env-var settings**
  - Given: the Environment Variables section.
  - When: the user toggles "override existing variables" or clicks refresh.
  - Then: the toggle saves with a toast; the list of loaded variables (global and repo-specific) refreshes.

## Privacy

- **SET-028 — Email & telemetry**
  - Given: the Privacy section.
  - When: the user views the email (read-only) and toggles telemetry.
  - Then: enabling telemetry saves immediately; disabling opens a confirmation ("Turn telemetry off?") with a "Disabling Telemetry…" spinner, then a toast (or an error toast on failure).

## Experimental

- **SET-029 — Experimental toggles**
  - Given: the Experimental section.
  - When: the user toggles any feature (Always interrupt and send, Smooth streaming, Per-workspace panel layout, In-place workspaces, Clone workspaces, Review all, Entity mentions, Rich markdown rendering, Pi agent).
  - Then: each shows "Setting updated".

- **SET-030 — Custom backend command & timeout**
  - Given: the Experimental/Advanced section.
  - When: the user sets a custom backend command or readiness timeout.
  - Then: each saves with a "restart required" toast.

## Extensions

- **SET-038 — Manage extension sources**
  - Given: the Extensions settings section with the extension system enabled.
  - When: the user adds an extension source by URL, toggles an extension's enable/disable switch, clicks Refresh to rescan the extensions directory, or removes a user-added URL source.
  - Then: an added source appears in the list; the switch mutes/unmutes the extension without removing it; Refresh re-scans drop-in extensions; a user-added URL source can be removed while bundled/disk-discovered ones cannot; the extensions directory path is shown.

- **SET-040 — Global extension enable/disable toggle**
  - Given: the Extensions settings section (always present, since it hosts the global extension toggle).
  - When: the user toggles the global extension switch at the top of the section off, then on.
  - Then: turning it off hides the extension-management UI (add-source input and list) while the section and switch remain; turning it on reveals the management UI again.

- **SET-041 — Retry a failed extension load**
  - Given: an extension source whose row is in the error state (its load failed).
  - When: the user clicks the retry control on that row.
  - Then: the row re-attempts the load — settling back to error if it fails again, or showing the loaded extension's name and version if it now succeeds.

## Actions

- **SET-031 — Manage actions**
  - Given: the Actions section.
  - When: the user adds an action/group, edits, deletes, exports (downloads JSON), or imports (file picker).
  - Then: dialogs handle add/edit/delete with confirmations; export downloads "sculptor-actions.json" (disabled when empty); import validates and merges with a count toast.

- **SET-032 — Action dialog fields**
  - Given: the action dialog (add/edit).
  - When: the user fills Name, Prompt, Group, and the Auto-submit toggle and clicks Save.
  - Then: Save is disabled until valid; `Cmd+Enter` submits; the action is created/updated.

- **SET-033 — Reorder & regroup actions**
  - Given: custom actions/groups.
  - When: the user drags to reorder or rename a group inline.
  - Then: the order updates and the group renames with a success toast.

## Theme builder

- **SET-034 — Appearance / fonts / code theme**
  - Given: the Theme Builder section.
  - When: the user changes appearance mode, primary font, code font, or code theme.
  - Then: the UI updates to reflect each choice.

- **SET-035 — Color pickers**
  - Given: a color setting (Accent, Gray, Danger, Success, Warning, Info).
  - When: the user clicks a swatch or enters a custom hex (with a light/dark hex override toggle).
  - Then: the color applies; an invalid hex is shown in red.

- **SET-036 — Radius / scaling / panel background**
  - Given: the Theme Builder section.
  - When: the user picks a radius, scaling, or panel-background option.
  - Then: borders / overall UI size / panel translucency update accordingly.

- **SET-037 — Component gallery & reset theme**
  - Given: the Theme Builder section.
  - When: the user clicks the component-gallery button or "Reset to defaults".
  - Then: the component gallery opens / theme settings reset (with a toast).

---

# ACT — Actions feature components

- **ACT-001 — Action chip appearance & trigger**
  - Given: an action chip.
  - When: viewing/clicking it.
  - Then: it shows a play icon (auto-submit) or text-cursor icon (draft), a tooltip with the prompt on hover, and clicking executes — for a chat agent, send or append to the chat input; for a terminal agent, type-and-submit (auto-submit) or type into the terminal without submitting (draft); disabled chips ignore clicks.

- **ACT-002 — Action context menu**
  - Given: an action chip.
  - When: the user right-clicks it.
  - Then: a menu offers "Queue message" (only while the agent runs), "Edit action", a "Move to group…" submenu (current group disabled), and "Delete action" (red).

- **ACT-003 — Action dialog validation & submit**
  - Given: the action dialog (Add/Edit).
  - When: the user fills Name and Prompt, optionally picks/creates a group, toggles Auto-submit, and saves.
  - Then: Save is disabled until Name and Prompt are non-empty; `Cmd+Enter` submits when valid; fields pre-populate when editing.

- **ACT-004 — Delete action / group confirmations**
  - Given: a delete action/group request.
  - When: the dialog appears.
  - Then: it names the target (and, for a group, lists its actions and count); confirming shows a spinner and disables buttons while deleting.

- **ACT-005 — Group header rename & collapse**
  - Given: a custom group header.
  - When: the user uses its context menu to rename (inline; Enter/blur confirms, Escape cancels) or clicks the header to collapse/expand.
  - Then: the name updates / the group collapses (chevron flips, count badge shows when collapsed); renaming does not toggle collapse.

- **ACT-006 — Drag to reorder / regroup**
  - Given: custom actions/groups (built-ins are not draggable).
  - When: the user drags an action or group.
  - Then: drop indicators show before/after positions; dropping into a group moves the action there; dropping outside removes it from the group.

---

# SKILL — Skills UI components

- **SKILL-001 — Skill chip**
  - Given: a skill chip.
  - When: viewing/clicking it (or pressing Enter/Space when focused).
  - Then: it shows `/skill-name`; clicking inserts it into the editor; an optional "Open in Sculptor" button appears for custom/sculptor skills; disabled chips are not interactive; the keyboard-target chip is highlighted.

- **SKILL-002 — Skill hover content**
  - Given: a skill chip.
  - When: the user hovers/focuses it.
  - Then: a popover shows the type badge (Built-in/Sculptor/Custom), the skill id, and description; hovering another chip in the group swaps content instantly; scrolling suppresses flapping.

- **SKILL-003 — Skills search navigation**
  - Given: the skills search input (placeholder "Search skills…").
  - When: the user types, arrows, presses Enter, or clears.
  - Then: the list filters in real time, arrows move the selection, Enter inserts the selected skill, Escape/clear closes search.

---

# MENT — Mentions, pickers, path autocomplete, mention chips

## Mention chips

- **MENT-001 — File/folder mention chip**
  - Given: a file/folder mention chip in a message.
  - When: viewing/clicking/hovering it.
  - Then: it shows the icon and basename (start-truncated for long paths); clicking opens the file or reveals the folder; hovering shows a popover with the full path and an action hint ("Click to open" / "Click to reveal in file browser").

- **MENT-002 — Skill mention chip**
  - Given: a skill mention chip.
  - When: hovering it.
  - Then: a popover shows the type badge, skill id, and description; it is not clickable.

- **MENT-003 — Entity mention chip**
  - Given: an entity (repository/workspace/agent) mention chip.
  - When: viewing/clicking/hovering it.
  - Then: it shows a type-colored icon and name; clicking a workspace/agent navigates to it (repositories and deleted entities are not clickable, shown strike-through); hovering shows an entity detail popover.

- **MENT-004 — Mention detail panes**
  - Given: an agent / workspace / repository mention.
  - When: its detail popover opens.
  - Then: it shows the entity's icon, title, optional badge, body lines, and a meta footer (e.g., agent count); deleted entities show a gray icon, strike-through title, and a "no longer exists" note.

## Mention pickers

- **MENT-005 — Category picker (+ trigger)**
  - Given: the chat input.
  - When: the user types `+`.
  - Then: a category list appears (Files, Commands, Repositories, Workspaces, and Images if image upload is supported); Tab/Enter/click drills into a category.

- **MENT-006 — File picker (@ trigger)**
  - Given: a file mention session.
  - When: the user types `@` and a name.
  - Then: a list of files/folders with highlighted matches and parent paths is shown; Tab/ArrowRight/Enter drills into folders, Enter/click on a file inserts it, Shift+Tab/Escape steps back or closes; empty states show "Type to search files" / "No matching files or folders".

- **MENT-007 — Skill picker (/ trigger)**
  - Given: a skill mention session.
  - When: the user types `/` and a name.
  - Then: a list of skills with a detail pane (type badge, id, description) is shown; Tab/Enter/click inserts the skill; the detail pane hides while typing; "No matching skills" when empty.

- **MENT-008 — Entity picker**
  - Given: an entity mention session.
  - When: the user selects a type and drills in.
  - Then: sectioned lists (Repositories/Workspaces/Agents) are shown; workspaces are drillable to their agents (chevron), agents/repositories insert on Enter/click; Shift+Tab pops one level.

- **MENT-009 — Image upload from picker**
  - Given: the harness supports image upload.
  - When: the user selects the Images category.
  - Then: an image-upload dialog is triggered (the Images row is hidden when unsupported).

## Path autocomplete

- **MENT-010 — Path autocomplete dropdown & submit**
  - Given: a path input (e.g., add-repo).
  - When: the user types a path with "/" or "~", navigates directories, and submits.
  - Then: after a debounce a spinner then matching directories appear (or "No matching directories"); clicking a directory drills in; Enter (dropdown closed) or `Cmd+Enter` submits the trimmed path; Escape/Tab close the dropdown.

---

# DEV — Dev/debug panels & markdown-diff anchors

- **DEV-001 — TanStack devtools panel modes**
  - Given: the devtools panel is enabled (via the version popover).
  - When: it is shown.
  - Then: a floating or docked-bottom panel appears with a header offering Dock/Float and Close; the floating panel can be dragged and resized within the viewport; the docked panel can be resized from its top edge and pushes app content up; closing hides it.

- **DEV-002 — Markdown external links**
  - Given: a markdown link with an external protocol.
  - When: the user clicks it.
  - Then: it opens in the OS browser and shows an external-link icon.

- **DEV-003 — Markdown fragment links**
  - Given: a `#anchor` markdown link.
  - When: the user clicks it.
  - Then: navigation is prevented; a dashed-underline style and a tooltip ("In-page anchor links aren't supported yet") are shown.

- **DEV-004 — Markdown relative/unsupported links**
  - Given: a relative or unsupported-scheme markdown link.
  - When: the user clicks it.
  - Then: navigation is prevented; a broken-link icon and a tooltip ("Linked-file navigation isn't supported yet") are shown.

---

## Coverage notes

- Some behaviors are gated by feature flags / capabilities and only appear when enabled:
  entity mentions, rich markdown rendering, clone/in-place workspaces, Review-all,
  Pi agent, image upload, CI babysitter, and the dev/devtools panels. Tests should set
  the relevant flag (or assert the gated UI is absent when off).
- The home-page rows and the workspace banner reuse the same PR button component, so
  the WS-PR scenarios (WS-022…WS-032) also describe the home-row PR behavior (HOME-020).
- Status dots (running / waiting / error / ready / read / unread, plus the two-dot mixed
  state) use one shared component across tab strips, home rows, agent tabs, peek popovers,
  and the command palette; verify the same color/animation mapping in each surface.
- Animations (status-pill and subagent-pill "thinking" variants) are randomized per
  appearance; tests should assert that *an* animation is present rather than a specific one.
