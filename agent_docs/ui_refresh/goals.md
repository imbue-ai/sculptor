This document outlines a redesign of the Sculptor workspace page around a uniform panel/section model. The goal is to update Sculptor’s UI to support a vertical sidebar, revamp the panel system and reduce some of the chrome. As a part of this change, we’ve converted existing components to be panels, including chat.

We’ve already built two throwaway prototype branches — `bryden/scu-1474-compact-workspace-layout` (the layout redesign) and `bryden/scu-1494-rewrite-new-workspace-modal` (the new workspace modal). Use them primarily to extract the proper styling for the different states described below; they are not a behavioral source of truth. This document is authoritative on behavior. See “Relationship to the prototype” below and the companion `design_extraction.md`.

This document is written from the perspective of updating the existing Sculptor to this new design. We are not concerned with backwards compatibility: layouts and settings created before this work do not need to be migrated, and “persisted” always refers to state created on this branch.

## Design

### Layout and terminology

The workspace page is laid out as follows:

```
┌──────────┬───────────────────────────────────────────────┐
│          │ Workspace header                              │
│ Workspace├──────────┬──────────────────┬─────────────────┤
│ sidebar  │          │                  │                 │
│          │  Left    │  Center          │  Right          │
│          │  section │  section         │  section        │
│          │          │                  │                 │
│          ├──────────┴──────────────────┴─────────────────┤
│          │ Bottom section                                │
└──────────┴───────────────────────────────────────────────┘
```

Each section has a **section header** (the row of panel tabs plus add/maximize controls) and a content area beneath it that renders the active panel.

Key terms used throughout this document:

- **Workspace sidebar** — the collapsible vertical navigation on the far left (global actions, repos, and workspaces).
- **Workspace header** — the simplified bar above the sections.
- **Section** — one of four regions (left, center, right, bottom) that groups panels. A section can be split into two sub-sections.
- **Panel** — a unit of content/functionality (agent, terminal, files, etc.) rendered inside a section.
- **Open vs. active panel** — a section can have several panels **open** at once, each shown as a tab in the section header; exactly one is **active** (its content is the one currently displayed). For example, the left section may have Files, Changes, and Commits open with Files active.
- **Collapsed vs. expanded** — the left, right, and bottom sections can be **collapsed** (hidden) or **expanded** (visible). The center section is always expanded and cannot be collapsed. Collapsing preserves a section’s open panels and active panel, which are restored when it is expanded again.
- **Empty section** — a section or split sub-section with no open panels; it shows the section empty state. This is independent of whether the section is collapsed or expanded.
- **Maximized section** — a section temporarily enlarged to cover the entire workspace page content.
- **Active section** — the section last interacted with.

### Workspace page layout

The new design has a workspace sidebar on the left and the workspace page content on the right.
The workspace page content has a workspace header and four workspace sections: left, center, right, bottom.
Each workspace section can render multiple panels.

The workspace header has been simplified. Refer to the prototype branch to see the changes.

#### Default layout
When a user first opens Sculptor, the workspace is in the following state:
- The center section is the only expanded (visible) section and contains a single agent panel of the most recently used agent type (Claude by default).
- The left section is collapsed and has the Files, Changes, and Commits panels open, with Files active.
- The bottom section is collapsed and has a single terminal panel open.
- The right section is collapsed and empty.

### Workspace sidebar

We’re replacing the existing top bar navigation with a collapsible vertical sidebar located on the left side of the screen.

The top of the sidebar contains links to perform the following actions:
- Switch to the home page
- Quickly open the Cmd+K window
- Create a new workspace

After the top links, we show workspaces grouped into collapsible repository sections.

For each repo
- You can collapse the section
- You can add a new workspace
- You can directly go to the repo settings page

For each workspace
- You can right click to open a context menu (existing functionality)
- On hover you see two icons: one to delete the workspace and one to open the context menu
- On click, you navigate to that workspace page

The bottom of the sidebar contains the following links:
- Switch to the Settings page
- Report a bug which opens the existing report bug popover.

The bottom of the sidebar should also show the current version of Sculptor.
You can also collapse the sidebar which should only show the expand sidebar icon. We need to take care to show this on the home page and not collide with the application controls in the top left.
You can resize the workspace sidebar by dragging the right border.
The workspace sidebar has a minimum size and cannot be dragged smaller than that size.
There is a keyboard shortcut to toggle the sidebar collapsed or expanded state.

### Sections
The workspace page now has the following sections: left, center, right, bottom.

Functionality:
- Each section is comprised of several panels.
- Each section has a header which consists of panel tabs. It also has an area for panel content beneath the header.
- Within a section, it’s possible to add new panels or close existing panels.
- The section header contains an icon to maximize the section (see Maximized section).
- The left, right and bottom sections can be collapsed and expanded with hotkeys.
- The center section is created with an agent panel of the most recently used agent type (Claude by default).
- The bottom section has a terminal panel created by default.
- The left and right sections can be split into top/bottom sub-sections.
- The bottom section can be split into left/right sub-sections.
- The center section can be split in either direction.
- A section can have at most one split at a time (two sub-sections).
- There is a keyboard shortcut to cycle between the open panels within a section.
- Sections can be resized by dragging on either the right, left or top border depending on the section. For example, the left section is resized by the right border and can only be resized in the x-direction.
- Section sizes are global: they are shared across all workspaces. Resizing the left section in one workspace changes its size everywhere.
- Section visibility (collapsed/expanded), the set of open panels, and which panel is active are stored per workspace and are independent between workspaces. Opening the bottom section or switching the active panel in one workspace does not affect another.

#### Active section
The active section is the last section that was interacted with, either via a keyboard shortcut that cycles between sections or by clicking a section. The keyboard cycle also steps through split sub-sections.
A collapsed section cannot be the active section. When no other section qualifies (for example on workspace load), the active section defaults to the center section.
When cycling with the keyboard shortcut and on workspace load, the active section is briefly highlighted with a ring that fades out within ~2 seconds.

#### Maximized section
A maximized section covers the entire workspace page content. Only one section can be maximized at a time. When the maximized section is split, only a single sub-section is shown (not both).
The workspace sidebar, if expanded, is still visible.
The maximized section still displays its section header but it does not show the workspace header.
When the workspace sidebar is collapsed, the show-sidebar icon is present at the left of the section header and the appropriate left padding is applied for the OS window controls (close, minimize, zoom).
There is a keyboard shortcut to maximize and restore the active section.

#### Section empty state
A section (including an empty split sub-section) shows an empty state when it has no open panels.
Centered is an add panel button which opens a dropdown displaying panel options.
There are also at most five quick actions below the add panel button that can be selected.
By default, we always show a “New {recent} agent” action (the most recently used agent type, Claude by default) and a “New terminal” action.
We reserve the last three slots for the most recently closed panels (fewer are shown if there are not three). The recently-closed list is transient — it resets on reload.

#### Split sections
A section can be split into exactly two sub-sections, and a section can hold at most one split at a time.
Splits are performed by right clicking a panel and choosing the split option from the context menu (shown as “Create {direction} split and move panel”, e.g. “Create bottom split and move panel”). The chosen panel moves into the new sub-section.
The available {direction} values depend on the section: left and right sections split top/bottom, the bottom section splits left/right, and the center section supports either.
Splits remain after the last panel in a sub-section is removed; the empty sub-section shows the section empty state.
A split is closed by an option that appears on the section empty state, after which the remaining panels collapse back into a single section.

### Panels
Panels represent specific content and functionality that can be displayed inside a workspace section.
Panels can either be single or multi instance.
By default, all panels are single instance outside of the agent and terminal panels.

Functionality:
- Panels can be placed in any one of the four sections.
- Panels can be opened and closed. When a panel is closed it no longer appears in the section header.
- Panels can be dragged to other sections and re-ordered within their existing section. Dragging onto a collapsed section shows a dropzone and expands the section on drop, appending the panel. A split section shows its per-sub-section dropzones only while the split exists.
- Each panel can expose its own keyboard shortcuts which are active when the panel is focused.
- Each panel can define its own actions that are displayed in a right click context menu.
- Panels can also expose functionality that can be accessed in Cmd+K.
- Every multi instance panel can be renamed; single instance panels cannot.
- Keyboard shortcuts can be configured to focus a single instance panel or the last active multi instance panel. All panel keyboard shortcuts (panel-specific actions and focus bindings) are configured on the keybindings settings page.

#### Adding a panel
Each section header renders a plus button which opens a dropdown. Panels added from a section’s dropdown are created in that section.
The dropdown has recent agent creation pinned to the top with its default keyboard binding (Cmd+Shift+T) visible.
The new-agent keyboard binding (and adding an agent via Cmd+K) always creates the agent in the center section — and in the center’s original sub-section when the center is split — regardless of which section is active.
There is a sub-dropdown menu to create an agent of a different type.
A new terminal option is directly beneath these two options.
There is no bare “Terminal” agent type: a raw shell is the “New terminal” panel, and terminal-running agents come from registered programs (e.g. the Claude Code CLI).
Every single instance panel that is not already open is listed below.

Panels can also be added via Cmd+K.
There’s an option to “Add panel” which takes you to a submenu where you select the location and then are presented with the list of valid panels for that location.

#### Agent Panel
The agent panel displays the existing agent/chat interface.
All existing functionality is essentially preserved with the addition that workspaces can now support zero, one or multiple agents at once. (Today a workspace requires at least one agent; this design relaxes that requirement — see Non-functional Behavior.)
It’s possible for a user to have one agent in the center section and another in the right section.
When a user closes an agent panel it’s equivalent to deleting that agent, so closing shows the same confirmation dialog as deleting an agent does today.

#### Terminal Panel
The terminal panel functions the same as before except workspaces can now support zero, one or multiple terminals at once.
When a user closes a terminal panel it’s equivalent to closing that terminal, and (for now) closing shows a confirmation dialog.

#### Files, Changes and Commits
Previously, files and changes and commits were a part of a single panel while the diff/file viewer was its special pseudo panel. These changes convert the existing “file browser” panel to its own individual panels.
Each panel renders its own unique diff/file viewer.
Each panel has a sidebar that consists of the file browser, the changes file browser, or the commit history list.
The sidebar can be resized by dragging and has a minimum size.
The size of the sidebar is shared between each of these panels.
The sidebar visibility can be toggled and the icon is displayed in the file viewer header.
The file viewer is always visible and displays an empty state when no file is selected.
All existing icons and options for configuring the panels have been moved into the triple dot menu in the file viewer header.

See the prototype for a faithful recreation of this.

#### Review all
Review all has been split into its own panel. It is a single instance panel with no default section (it is not opened by default, like the browser panel). All existing functionality is preserved.

### Workspace creation
Workspaces can be created in the following ways:
- The new workspace button in the workspace sidebar
- The new workspace keyboard shortcut (default: Cmd/Meta+T)
- The Cmd+K window
- The plus icon in a repo section in the workspace sidebar

The first option directly creates a new workspace, reusing the previously selected settings: repo, source branch, new branch, agent type, and initialization strategy.
All other modes open the new workspace dialog. When opened from a repo section’s plus icon, the dialog pre-selects that repo and uses the default workspace title.

#### New workspace dialog
The new workspace page is removed and replaced by the new workspace form and dialog.

The dialog collects a workspace title, a prompt, the repo, the source branch, a new branch name, the agent type, and the initialization strategy (worktree by default; clone and in-place opt-in). Creating the workspace also creates its first agent of the chosen type, seeded with the prompt — today’s creation form has no prompt, so the dialog adds one. A “keep open” option keeps the dialog open after creation for rapid multi-create: the title, prompt, and branch name reset, while the repo, agent type, initialization mode, source branch, and the per-prompt agent settings (model, effort, fast mode) are retained. Plan mode is the exception — it is a per-task choice and resets on each create.

The styling comes from the `scu-1494` prototype’s `sculptor/frontend/src/components/NewWorkspaceModal` (see “Relationship to the prototype”); the rest of that branch can be ignored.

#### Empty workspace state
When there are no workspaces, default to the sidebar open with a special page rendering the new workspace form.
The sidebar still renders its repo area: if there are no repos, it shows an “Add a repo” button; if a repo exists but has no workspaces, it shows “No workspaces yet” beneath that repo.
Navigation is otherwise disabled. The only available destinations are the new workspace form and the Settings page; Cmd+K and the global keyboard shortcuts are disabled in this state to keep it simple.
The prompt for this first workspace defaults to the existing /sculptor:help prompt we use on new workspace creation.
Once a workspace is created, we display the full workspace page (including the sidebar) and navigate you to that workspace in the default state.

## Non-functional Behavior

### Workspace switching should look seamless
- No delayed or duplicated renders.
- Avoid shifting the layout after rendering. Load layout first and display skeletons if needed.
- Avoid waiting for content to arrive. Either prefetch or display stale content and update after loading.
- Prefer to preserve whatever the user was last looking at on re-entry.

Acceptance bars:
- On switch, the sidebar, workspace header, every section header, and the section frames at their persisted sizes are present in the first committed frame — no second-pass resize or reflow. This can be verified with the workspace-switch profiler (zero layout-shift frames).
- Each panel mounts at most once per switch (no duplicate mounts), verifiable with the render-count tooling.
- The layout never shows a spinner: content is prefetched, and when it is not ready the last-known content or an in-place skeleton is shown and then updated.
- Error and retry states for file/diff loading still need to be defined.

### Workspaces without agents
- A workspace can exist with zero agents. Today the system requires at least one agent; this design must relax that so the center section can be empty and show the section empty state.

### Persistence
- UI state is consolidated and preserved in local storage (see the per-workspace vs. global rules under Sections).
- Layouts created on this branch persist across app restarts: if you open and arrange sections in a workspace, you see the same arrangement after restarting. We do not migrate or support layouts created before this work.

### Minimize re-renders
- Proper components are memoized so expensive re-renders are skipped when dragging and dropping panels or resizing sections.

### Out of scope
This redesign reuses the existing styling and components where possible and focuses on layout and behavior. It does not change agent or terminal internals or backend behavior. Persistence stays client-side (local storage); no backend persistence is introduced. Theming and responsive/mobile behavior beyond a minimum window width are out of scope.

## Features to deprecate

- Zen mode
- Focus mode
- Existing docking layout
- Settings
	- Experimental settings for sharing panel sizes between workspaces
    - Panels setting page
- The open/closed-workspace distinction (the closed-workspaces pill and dropdown). All workspaces appear in the sidebar; "archived workspaces" may be revisited later as a separate design.

## Relationship to the prototype

Two throwaway prototype branches back this work:
- `bryden/scu-1474-compact-workspace-layout` — the layout redesign (sidebar, sections, panels).
- `bryden/scu-1494-rewrite-new-workspace-modal` — the new workspace modal.

Use them primarily to extract the proper styling for the states described in this document; they are not a production base.

- This document is the source of truth for behavior. Where a prototype and this document differ, this document wins.
- The prototypes’ in-branch notes (their `agent_docs`, test plans, and similar markdown) are brainstorms that frequently do not match the actual code or intended behavior. Treat them as references only; do not anchor to them.
- The concrete styles and components worth copying are enumerated in the companion `design_extraction.md`.
- The execution approach — including which components and styling to copy forward — is covered separately in `plan.md`.
