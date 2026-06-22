This document outlines a redesign of the Sculptor workspace page around a uniform panel/section model. The goal is to update Sculptor’s UI to support a vertical sidebar, revamp the panel system and reduce some of the chrome. As a part of this change, we’ve converted existing components to be a panel, including chat.

We’ve created a prototype branch of this already but need to make several changes to make this branch production ready.

This document is written from the perspective of updating the existing Sculptor to this new design.

## Design

### Workspace page layout

The new design has a workspace sidebar on the left and the workspace page content on the right.
The workspace page content has a workspace header and four workspace sections: left, center, right, bottom.
Each workspace section can render multiple panels.

The workspace header has been simplified, refer to the prototype branch to see the changes.

#### Default layout
When a user first opens Sculptor, the workspace is in the following state:
- The center section is the only visible section.
- The left section contains the files, changes and commits panel
- The bottom section contains a terminal instance.
- The right section is empty.

### Workspace sidebar

We’re replacing the existing top bar navigation with a collapsible vertical sidebar located on the left side of the screen.

The top of the side bar contains links to perform the following actions:
- Switch to the home page
- Quickly open the CMD+K window
- Create a new workspace

After the top links, we show workspaces grouped by collapse repository section. 

For each repo
- You can collapse the section
- You can add a new workspace
- You can directly go to the repo settings page

For each workspace
- You can right click to open a context menu (existing functionality)
- On hover you see an icon to delete the workspace or open the context menu
- On click, you navigate to that workspace page

The bottom of the sidebar contains the following links:
- Switch to the Settings page
- Report a bug which opens the existing report bug popover.

The bottom of the sidebar should also show the current version of Sculptor.
You can also collapse the sidebar which should only show the expand sidebar icon. We need to take careful care to show this on the home page and not collide with the application controls in the top left.
You can resize the workspace sidebar by dragging the right border.
The workspace sidebar has a minimum size and cannot be dragged smaller than that size.
There is a keyboard shortcut to toggle the sidebar collapsed or expanded state.

### Sections
The workspace page now has the following sections: left, center, right, bottom.

Functionality:
- Each section is comprised of several panels.
- Each section has a header which consists of panel tabs. It also has an area for panel content beneath the header.
- Within a section, it’s possible to add new panels or close existing panels.
- The header contains an icon to expand a given section.
- The left, right and bottom section can be collapsed and expanded with hotkeys.
- The center panel has the most recently used agent type created by default.
- The bottom panel has a terminal panel created by default.
- The left and right section can be split horizontally (top/down).
- The bottom section can be split vertically (left/right).
- There is a keyboard shortcut to cycle between active panels within a section.
- Sections can be resized by dragging on either the right, left or top border depending on the section. For example, the left section is resized by the right border and can only be resized in the x-direction.
- Section states (which panel is open) is NOT preserved between workspaces.
- Section sizes are preserved between workspaces.

#### Focus
The focused section is the last section that was interacted with, either via a keyboard shortcut that cycles focus or based on the last section a user clicked.
When cycling with the keyboard shortcut and on workspace load, the last focused section is highlighted with a temporary focus ring that fades out within ~1 second.

#### Expanded section
Expanded sections cover the entire workspace page content.
The workspace sidebar, if expanded, is still visible.
The expanded section still displays the section header but they do not show the workspace header.
When the workspace sidebar is collapsed, the show workspace sidebar icon is present in the left of the panel section and the appropriate left padding is applied for the OS window application icons (close, minimize, expand).
There is a keyboard shortcut for expanding the last focused section.

#### Section empty state
Sections display an empty state when there are no panels. 
Centered is an add panel button which opens a dropdown displaying panel options. 
There are also at most five quick actions below the add panel button that can be selected.
By default, we always show “New {recent} agent” and “New terminal” quick actions.
We reserve the last three slots for the most recently created panels that are not open.

#### Split sections
Splits can be performed by right clicking on a panel and accessing it via the context menu (shown as “Split {direction} and move panel").
Splits remain after the last panel is removed.
Splits are closed by a new option that appears on the section empty state.

### Panels
Panels represent specific content and functionality that can be displayed inside a workspace section.
Panels can either by single or multi instance. 
By default, all panels are single instance outside of the agent and terminal panels.

Functionality:
- Panels can be placed in any one of the four sections.
- Panels can be opened and closed. When a panel is closed it now longer appears in the section header.
- Panels can be dragged to other sections and re-ordered in their existing section.
- Each panel can expose its own keyboard shortcuts which are active when the panel is focused.
- Each panel can define its own actions that are display in a right click context menu.
- Panels can also expose functionality that can be accessed in CMD+k.
- Every multi instance panel can be renamed, single instance panels cannot.
- Keyboard shortcuts can be configured to focus a single instance panel or the last active multi instance panel.

#### Adding a panel
Each section header renders a plus button which opens a dropdown. 
The dropdown has recent agent creation pinned to the top with a default keyboard binding (cmd+shift+t) visible.
The new agent keyboard binding always creates an agent in the center section.
There is a sub-dropdown menu to create an agent of a different type.
A new terminal tab is directly beneath these two options.
Every other non-visible single instance panel option is included below.

Panels can also be added via CMD+k.
There’s an option to “Add panel” which takes you to a submenu where you select the location and then are presented with the list of valid panels.

#### Agent Panel
The agent panel displays the existing agent/chat interface.
All existing functionality is essentially preserved with the addition that workspaces can now support zero, one or multiple agents at once.
It’s possible for a user to have one agent in the center section and another in the right section.
When a user closes an agent panel it’s equivalent to deleting that agent.

#### Terminal Panel
The terminal panel functions the same as before except workspaces can now support zero, one or multiple terminals at once.
When a user closes a terminal panel it’s equivalent to closing that terminal.

#### Files, Changes and Commits
Previously, files and changes and commits were a part of a single panel while the diff/file viewer was its special pseudo panel. These changes convert the existing “file browser” panel to its own individual panels.
Each panel renders its own unique diff/file viewer.
Each panel has a sidebar that consists of the file browser, the changes file browser, or the commit history list.
The sidebar can be resized by dragging and has a minimum size.
The size of the sidebar is shared between each of these panels.
The sidebar visibility can be toggled and the icon is displayed in the file viewer header.
The file viewer is always visible and displays an empty state when now file is selected.
All existing icons and options for configuring the panels has been move into the triple dot menu in the file viewer header.

See the prototype for a faithful recreation of this.

#### Review all
Review all has been split into its own panel. All existing functionality is preserved.

### Workspace creation
Workspaces can be created in the following way:
- The new workspace button in the workspace sidebar
- The new workspace keyboard shortcut (default: cmd/meta+T)
- The CMD+K window
- The plus icon in a repo section in the workspace sidebar

The first option directly creates a new workspace with the previously selected settings in the workspace.
All other modes of creation open the new workspace dialog.

#### New workspace dialog
The new workspace page is removed and replaced by the new workspace form and dialog.

An existing prototype branch can be found at: `bryden/scu-1494-rewrite-new-workspace-modal`. 
Just refer to the changes in `sculptor/frontend/src/components/NewWorkspaceModal` to preserve the styling from that branch.
The rest of the changes likely clash with the changes in this body of work and can be ignored.

#### Empty workspace state
When there are no workspaces, default to the sidebar open with a special page rendering the new workspace form.
It is still possible to navigate to the settings page but all other navigation is disabled.
The prompt for this first workspace defaults to the existing /sculptor:help prompt we use on new workspace creation.
Once a workspace is created, we display the full workspace page (including the sidebar) and navigate you to that workspace in the default state.

## Non-functional Behavior

### Workspace switching should look seamless
- No delayed or duplicated renders.
- Avoid shifting the layout after rendering. Load layout first and display skeletons if needed.
- Avoid waiting for content to arrive. Either prefetch or display stale content and update after loading.
- Prefer to preserve whatever the user was last looking at on re-entry.

### Persistence
- UI state is consolidated and preserved in local storage.
- Existing layouts should be persisted on restart

### Minimize re-renders
- Proper components are memoized so expensive re-renders are skipped when dragging and dropping panels or resizing sections.

## Features to deprecate

- Zen mode
- Focus mode
- Existing docking layout
- Settings
	- Experimental settings for sharing panel sizes between workspaces
    - Panels setting page

## Deviations from the prototype

- Add panel previously relied on CMD+k but we’re moving to using a dropdown

