# User stories — workspace UI refresh

Canonical, addressable user stories for the workspace UI redesign. Derived from
`goals.md` (the behavioral source of truth). `e2e_test_plan.md` and the future
`plan.md` reference these IDs; `harness_migration.md` covers the test-harness work.

These are behavioral statements only — they never name a test, file, DOM
attribute, atom, or other implementation detail. Verification and the test/harness
mapping live in `e2e_test_plan.md`.

## How to read this

- Stories are grouped into 12 **areas**. The area is the review unit — read an
  area's one-line summary, then its stories.
- Each story has a **stable ID** (`AREA-NN`). IDs are append-only for ratified
  stories: never renumber or reuse.
- Each story is tagged with how it is verified:
  - `[e2e]` — an end-to-end integration test.
  - `[perf]` — a non-functional/performance guarantee, checked with profiling /
    render-count tooling rather than a standard e2e test (see SWITCH).
  - `[unit]` — best covered by a unit test, or otherwise not a full e2e flow.
- **A test may cover several stories, and a story may be covered by several
  tests.** The mapping in `e2e_test_plan.md` is many-to-many.
- New vocabulary (per `goals.md`): **section** (left/center/right/bottom),
  **panel**, **open vs. active** panel, **collapsed/expanded**, **maximized**,
  **active section**, **split / sub-section**, **workspace sidebar**, **workspace
  header**.

---

## SIDE — Workspace sidebar
Collapsible vertical nav on the far left replacing the old top bar.

- **SIDE-01** `[e2e]` Top link switches to the home page (a full route; you return to a workspace by clicking its sidebar row — SIDE-07. There is no closeable Home tab).
- **SIDE-02** `[e2e]` Top link opens the Cmd+K window.
- **SIDE-03** `[e2e]` Top link creates a new workspace (direct create, reusing the last-used settings — see WSC-01).
- **SIDE-04** `[e2e]` Workspaces are grouped into collapsible repository sections; a repo section can be collapsed/expanded.
- **SIDE-05** `[e2e]` A repo section's plus icon adds a new workspace (opens the dialog pre-selecting that repo — see WSC-04).
- **SIDE-06** `[e2e]` A repo section links directly to that repo's settings page.
- **SIDE-07** `[e2e]` Clicking a workspace row navigates to that workspace page.
- **SIDE-08** `[e2e]` Right-clicking a workspace row opens its context menu (existing functionality preserved).
- **SIDE-09** `[e2e]` Hovering a workspace row reveals two icons: delete workspace, and open context menu.
- **SIDE-10** `[e2e]` Bottom link switches to the Settings page (a full route; you return to a workspace by clicking its sidebar row — SIDE-07. There is no closeable Settings tab).
- **SIDE-11** `[e2e]` Bottom link reports a bug, opening the existing report-bug popover.
- **SIDE-12** `[e2e]` The current Sculptor version is shown at the bottom of the sidebar.
- **SIDE-13** `[e2e]` The sidebar can be collapsed to show only the expand-sidebar icon; on the home page it does not collide with the OS window controls (top-left).
- **SIDE-14** `[e2e]` The sidebar is resizable by dragging its right border and clamps to a minimum width.
- **SIDE-15** `[e2e]` A keyboard shortcut toggles the sidebar collapsed/expanded.
- **SIDE-16** `[e2e]` Closing or deleting a workspace optimistically updates the sidebar and rolls back on failure with an error toast.
- **SIDE-17** `[e2e]` A workspace row shows an unread indicator when the workspace has unseen agent updates.

## SEC — Sections
Four regions (left/center/right/bottom), each with a header (panel tabs + add + maximize) and a content area.

- **SEC-01** `[e2e]` Default layout: the center section is the only expanded section and holds one agent panel of the most-recently-used type (Claude by default).
- **SEC-02** `[e2e]` Default layout: the left section is collapsed with Files, Changes, Commits open and Files active.
- **SEC-03** `[e2e]` Default layout: the bottom section is collapsed with one terminal panel open.
- **SEC-04** `[e2e]` Default layout: the right section is collapsed and empty. (Actions, Skills, and Notes default to the right section *when opened*, but nothing is open there at first run.)
- **SEC-05** `[e2e]` The left section collapses/expands via hotkey; collapsing preserves its open panels and active panel, restored on expand.
- **SEC-06** `[e2e]` The right section collapses/expands via hotkey.
- **SEC-07** `[e2e]` The bottom section collapses/expands via hotkey.
- **SEC-08** `[e2e]` The center section is always expanded and cannot be collapsed.
- **SEC-09** `[e2e]` Each section header shows its panel tabs plus add and maximize controls.
- **SEC-10** `[e2e]` The active section is the last one interacted with (click or cycle hotkey); a collapsed section cannot be active; on load it defaults to center.
- **SEC-11** `[e2e]` On cycle and on workspace load, the active section is briefly ring-highlighted, fading within ~2s.
- **SEC-12** `[e2e]` A cycle hotkey steps between sections, including split sub-sections.
- **SEC-13** `[e2e]` Maximizing the active section makes it cover the entire workspace page content; only one section can be maximized at a time.
- **SEC-14** `[e2e]` A maximized section still shows its section header but hides the workspace header; the sidebar, if expanded, stays visible.
- **SEC-15** `[e2e]` A hotkey maximizes and restores the active section.
- **SEC-16** `[e2e]` When maximized with the sidebar collapsed, the show-sidebar icon appears at the left of the section header with OS-window-control padding.
- **SEC-17** `[e2e]` A section is resizable by dragging the appropriate border (e.g. the left section by its right border, x-axis only).
- **SEC-18** `[perf]` Section sizes are global: resizing a section in one workspace changes its size in all workspaces.
- **SEC-19** `[e2e]` An empty section (or empty split sub-section) shows the empty state: a centered add-panel button plus up to five quick actions (always "New {recent} agent" and "New terminal", then up to three most-recently-created-but-closed panels).
- **SEC-20** `[e2e]` A hotkey cycles between the open panels within a section; it wraps at the ends and is a no-op in an empty or single-panel section.
- **SEC-21** `[e2e]` Maximize is transient: it is not persisted, so reloading the app returns to the normal (non-maximized) layout.
- **SEC-22** `[e2e]` Section resize clamps to min/max: the sides have a minimum width, the center keeps a larger minimum width, and the sides give way before the center shrinks.

## SPLIT — Split sub-sections
A section can be split into exactly two sub-sections (at most one split per section).

- **SPLIT-01** `[e2e]` Splitting is done by right-clicking a panel and choosing "Create {direction} split and move panel"; the chosen panel moves into the new sub-section.
- **SPLIT-02** `[e2e]` Available directions depend on the section: left/right sections split top/bottom, the bottom section splits left/right, the center supports either.
- **SPLIT-03** `[e2e]` A section can hold at most one split at a time.
- **SPLIT-04** `[e2e]` A split remains after the last panel in a sub-section is removed; the empty sub-section shows the section empty state.
- **SPLIT-05** `[e2e]` A split is closed via an option on the empty state, after which the remaining panels collapse back into a single section.
- **SPLIT-06** `[e2e]` When a split section is maximized, only one sub-section is shown.

## PANEL — Panels (generic)
A panel is a unit of content placeable in any section. Single-instance by default; agent and terminal are multi-instance.

- **PANEL-01** `[e2e]` The section header's `+` opens a dropdown; panels added from it are created in that section.
- **PANEL-02** `[e2e]` The dropdown pins recent-agent creation at the top with its default binding (Cmd+Shift+T) visible.
- **PANEL-03** `[e2e]` The dropdown has a sub-menu to create an agent of a different type.
- **PANEL-04** `[e2e]` "New terminal" appears directly beneath the agent options.
- **PANEL-05** `[e2e]` Every single-instance panel that is not already open is listed below. The single-instance panels are: Files, Changes, Commits, Review All, Skills, Browser, and (slated for deprecation in favor of plugin support) Actions and Notes. Agents and terminals are multi-instance and are **not** offered in this re-add list (closing them ends them; there is no reopen pool).
- **PANEL-06** `[e2e]` The new-agent binding (Cmd+Shift+T) and adding an agent via Cmd+K always create the agent in the center section (the center's original sub-section when split), regardless of the active section.
- **PANEL-07** `[e2e]` Closing a panel removes it from the section header.
- **PANEL-08** `[e2e]` A panel can be dragged to another section and re-ordered within its section.
- **PANEL-09** `[e2e]` Dragging onto a collapsed section shows a dropzone and expands the section on drop, appending the panel.
- **PANEL-10** `[e2e]` A split section shows its per-sub-section dropzones only while the split exists.
- **PANEL-11** `[e2e]` Multi-instance panels (agent, terminal) can be renamed; single-instance panels cannot.
- **PANEL-12** `[e2e]` A panel can be added via Cmd+K → "Add panel" → choose location → choose from the valid panels for that location.
- **PANEL-13** `[unit]` A panel exposes its own keyboard shortcuts (active when focused) and a focus binding; all are configured on the keybindings settings page.
- **PANEL-14** `[e2e]` A panel exposes its own actions in a right-click context menu and its own functionality in Cmd+K.
- **PANEL-15** `[e2e]` All panels are single-instance by default except agent and terminal.
- **PANEL-16** `[e2e]` Reordering panel tabs within a section persists across collapse→expand and workspace switch.

## AGENT — Agent panel
The existing agent/chat interface as a panel.

- **AGENT-01** `[e2e]` The agent panel renders the existing agent/chat interface with all existing functionality preserved.
- **AGENT-02** `[e2e]` A workspace can have zero, one, or multiple agents at once (relaxing today's "at least one agent" requirement).
- **AGENT-03** `[e2e]` A user can have one agent in the center section and another in the right section simultaneously.
- **AGENT-04** `[e2e]` Closing an agent panel deletes that agent and shows the same confirmation dialog as deleting an agent does today. Closing the last agent leaves the center section empty (it is not auto-replaced).
- **AGENT-05** `[e2e]` Two agents streaming work at the same time render and update independently — neither blocks, drops, or overwrites the other.
- **AGENT-06** `[e2e]` The agent panel tab's context menu exposes diagnostics actions (copy session id, transcript path, agent id, agent name), disabled when the agent has no session.
- **AGENT-07** `[e2e]` The agent panel tab's status indicator reflects read/unread and running/waiting; marking an agent unread persists across switches while it is unfocused.
- **AGENT-08** `[e2e]` Optimistic agent deletion: the panel tab disappears instantly; a backend failure rolls back the deletion with an error toast and a retry affordance.
- **AGENT-09** `[e2e]` Agent tab numbering reuses the lowest available number after an agent is deleted.

## TERM — Terminal panel

- **TERM-01** `[e2e]` The terminal panel works as before; a workspace can have zero, one, or multiple terminals.
- **TERM-02** `[e2e]` Closing a terminal panel closes that terminal and (for now) shows a confirmation dialog. *(New: terminal close has no confirmation today.)*
- **TERM-03** `[e2e]` Terminal tab numbering reuses the lowest available number after a terminal is closed.
- **TERM-04** `[e2e]` Closing a terminal panel kills its backend shell process (not just disconnects); other terminals are unaffected.
- **TERM-05** `[e2e]` Registered terminal-agent programs can be created from the agent-type sub-menu, run their program in the terminal, reflect their status on the tab, and resume (or start fresh) across restart. (There is no bare "Terminal" agent type — a raw shell is the "New terminal" panel, TERM-01.)

## FCC — Files / Changes / Commits panels
The old single file-browser panel split into three independent panels, each with its own diff/file viewer. File/diff load error and retry states are unchanged — the redesign keeps whatever behavior exists today (if there is none, there is none).

- **FCC-01** `[e2e]` Files, Changes, and Commits are three separate panels (previously one file-browser panel plus a diff pseudo-panel).
- **FCC-02** `[e2e]` Each panel renders its own diff/file viewer.
- **FCC-03** `[e2e]` Each panel has a sidebar: the file browser, the changes file browser, or the commit history list, respectively.
- **FCC-04** `[e2e]` The panel sidebar (the master-detail list) is resizable with a minimum size; its width is shared across all three panels and is global across workspaces.
- **FCC-05** `[e2e]` The sidebar visibility can be toggled via an icon in the file-viewer header.
- **FCC-06** `[e2e]` The file viewer is always visible and shows an empty state when no file is selected.
- **FCC-07** `[e2e]` All previous icons/options for configuring these panels are moved into the triple-dot menu in the file-viewer header.

## REVIEW — Review-all panel

- **REVIEW-01** `[e2e]` Review-all is its own single-instance panel with no default section (not opened by default, like the browser panel).
- **REVIEW-02** `[e2e]` All existing review-all functionality is preserved.

## WSC — Workspace creation
Four entry points; one direct-create and three that open the dialog.

- **WSC-01** `[e2e]` The sidebar's new-workspace button directly creates a workspace, reusing the previously selected settings (repo, source branch, agent type, init strategy) and auto-generating a new branch name. If branch auto-generation is off or unavailable, it opens the dialog instead.
- **WSC-02** `[e2e]` The new-workspace keyboard shortcut (default Cmd/Meta+T) opens the new-workspace dialog.
- **WSC-03** `[e2e]` Cmd+K opens the new-workspace dialog.
- **WSC-04** `[e2e]` A repo section's plus icon opens the dialog pre-selecting that repo with the default workspace title.
- **WSC-05** `[e2e]` The dialog provides the new-workspace form: title, auto-growing prompt textarea, a breadcrumb row of context pills (repo / agent type / mode / branch), and a footer ("keep open" switch, Cmd+Enter hint, Create).
- **WSC-06** `[e2e]` The branch-name field is a monospace pill with sanitization, a shuffle button, and a stable error slot.
- **WSC-07** `[e2e]` The old new-workspace page (`/ws/new`) is removed and replaced by the dialog.
- **WSC-08** `[e2e]` Because direct create auto-generates a unique branch (WSC-01), a branch-name collision is only possible when the user types a branch name in the dialog, where it is surfaced as an inline error (worktree and clone modes) and leaves no stale workspace state.
- **WSC-09** `[e2e]` The dialog offers creation-mode / initialization-strategy selection (worktree by default; clone and in-place opt-in), with mode-appropriate branch-field behavior (clearing the branch works on the base branch; entering one creates a new branch).
- **WSC-10** `[e2e]` A workspace can be created from a non-default source branch via the branch selector.
- **WSC-11** `[e2e]` The dialog's project/repo selector can register a new repo and remembers the most-recently-used project.

## FIRST — Empty first-run / empty workspace state
What a user with no workspaces sees.

- **FIRST-01** `[e2e]` With no workspaces, the app defaults to the sidebar open and a special page rendering the new-workspace form.
- **FIRST-02** `[e2e]` The sidebar still renders its repo area: an "Add a repo" button if there are no repos; "No workspaces yet" beneath a repo that has none.
- **FIRST-03** `[e2e]` Navigation is otherwise disabled — only the new-workspace form and Settings are reachable; Cmd+K and global keyboard shortcuts are disabled in this state.
- **FIRST-04** `[e2e]` The first-workspace prompt defaults to the existing `/sculptor:help` prefill.
- **FIRST-05** `[e2e]` After creating the first workspace, the full workspace page (with sidebar) is shown and the user is navigated to that workspace in the default state.

## PERSIST — Persistence
Client-side (local storage); no backend persistence. No migration of pre-branch layouts.

- **PERSIST-01** `[e2e]` The full per-workspace arrangement is stored per workspace and is independent between workspaces: section visibility (collapsed/expanded), panel placement, tab order, the active panel per sub-section, split state, and the active section/sub-section.
- **PERSIST-02** `[perf]` The global layout is stored globally and shared across all workspaces: section sizes, sidebar width, sidebar collapsed state, and the shared master-detail list width (cross-references SEC-18, FCC-04).
- **PERSIST-03** `[e2e]` A layout arranged on this branch persists across app restarts (same arrangement after restart).
- **PERSIST-04** `[e2e]` Round-trip stability: with the right section expanded and a terminal panel added, navigating to Home and back to the workspace leaves the agent panel intact — no panel/agent disappears.
- **PERSIST-05** `[e2e]` Opening a section or switching the active panel in one workspace does not affect another workspace.

## SWITCH — Seamless workspace switching (non-functional)
Switching workspaces should look seamless. These are mostly verified with perf tooling, not standard e2e.

- **SWITCH-01** `[perf]` On switch, the sidebar, workspace header, every section header, and the section frames at their persisted sizes are present in the first committed frame — no second-pass resize/reflow (zero layout-shift).
- **SWITCH-02** `[perf]` Each panel mounts at most once per switch — no duplicate mounts.
- **SWITCH-03** `[e2e]` The layout never shows a spinner: content is prefetched, or last-known content / an in-place skeleton is shown and then updated.
- **SWITCH-04** `[e2e]` Re-entering a workspace preserves whatever the user was last looking at.
- **SWITCH-05** `[unit]` Components are memoized so expensive re-renders are skipped when dragging/dropping panels or resizing sections.

---

## Removed behaviors
The redesign removes these; they have no user stories. Their tests are deleted — see `e2e_test_plan.md`.

- Zen mode and Focus mode.
- The old docking / panel-zone layout (top-right / bottom-right zones, "Move to zone", side-toggle bar).
- The experimental "share panel sizes between workspaces" setting (superseded by the global-size rule, SEC-18).
- The Panels settings page (and the per-panel enable/disable machinery).
- The `/btw` popup.
- The per-diff "expand"/fullscreen toggle — there is no diff-specific fullscreen; users maximize the section instead (SEC-13/15).
- The open/closed-workspace distinction (the closed-workspaces pill and dropdown). All workspaces simply appear in the sidebar; "archived workspaces" may be revisited later as a separate design. *(Pending a matching update to `goals.md`.)*

## Out of scope (future follow-up)

- **Mobile / responsive shell** — mobile and responsive behavior beyond a minimum window width is out of scope for this work and tracked as future follow-up. (Content components stay shell-agnostic — they never read layout state — which keeps the "keep behavior" bucket valid when that work happens.)
