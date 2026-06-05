# Compact Workspace Layout

## Overview

This is a functional prototype/spike of a redesigned layout for the
Sculptor workspace page. The driving design goal is for the workspace
to feel **compact and clean** — strip away the chrome (left sidebar,
right sidebar, bottom bar) and reduce the number of always-visible
icons.

The redesign covers several intertwined changes:

- **Strip the chrome.** Remove the left sidebar, right sidebar, and
  bottom bar. Reduce per-panel icons — this iteration **removes** the
  secondary icons and records them in a doc; relocating them into
  three-dot overflow menus is a follow-up.
- **Vertical navigation sidebar** replaces the horizontal tab bar. Top
  bar icons become a vertical list with text labels, followed by repos
  and their workspaces (grouped by repo). Settings and Help anchor to
  the bottom, separated from the repo/workspace list by flexible space.
  A toggle for the sidebar sits next to the window controls
  (close/minimize/maximize).
- **Split the file browser** into three separate panels: Files,
  Changes, and Commits.
- **Three panel zones** — Left, Right, and Bottom — around a Center
  that is always Chat. The Bottom zone is special: it hosts only the
  terminal.
- **Panel sections.** A panel section is a collection of panels. Each
  panel is a single tab; only one panel is active per section. A plus
  button opens a dropdown to add panels that aren't currently visible.
- **WorkspaceBanner becomes the top bar**, spanning the width minus the
  sidebar. The PR/MR dropdown is removed (the PR button has no dropdown
  in any state). The bar also gains a terminal toggle and Left/Right
  section toggles, and the RepoSegment (folder icon) moves beside the
  target-branch selector.
- **Simplify the diff/file viewer** to show one file at a time.
- **Split view for chat** — make it possible to view chat side-by-side.

### Scope & success bar

This is a functional spike, not a throwaway mock: all four of the
following should hold when it's working —

1. The layout **looks compact and clean** (the visual redesign lands).
2. The **panel system actually works** — open/close panels, switch
   tabs, the plus-dropdown, terminal in the bottom zone.
3. **Chat split view works** (functional, not just visually present).
4. **Everything still works** — all existing workspace features remain
   reachable through the new layout; nothing is lost, just reorganized.

Backward-compatibility with the old layout is **not** a concern — the
old layout can be replaced outright. Panel/zone/section state is
persisted via **localStorage** to keep things simple. The user is
specifically interested in surfacing **UX edge cases** that the new
structure could introduce (these will accumulate in Open Questions and
edge-case scenarios).

## User Scenarios

### Scenario: A clean first launch
On a fresh load, the workspace shows the vertical nav sidebar, the
full-width top bar, a single chat in the Center, and the **Left
section** with Files/Changes/Commits (Files active). The Right section
and the Bottom terminal are collapsed. (REQ-DEFAULT-1)

### Scenario: Navigating workspaces by repo
The user opens the sidebar. At the top are Home, Search, and New
Workspace. Below, repos are listed as collapsible headers; expanding
one reveals its workspaces, each with a status dot (REQ-NAV-3/5). The
user clicks a + on a repo header to start a new workspace in that repo
(REQ-NAV-4). Settings and Help sit anchored at the bottom (REQ-NAV-6).
The user collapses the sidebar via the toggle by the window controls;
it hides entirely and two icons remain at the top-bar's left
(REQ-NAV-7).

### Scenario: Opening a file to view its diff
The user selects the Changes panel in the Left section and clicks a
changed file. The Center splits: chat on one side, the single-file diff
viewer on the other (REQ-CENTER-2/3). Only that one file is shown, with
no tab/scope row above it (REQ-CENTER-4). Closing the diff returns the
Center to full-width chat.

### Scenario: Comparing two agents (chat split)
The user right-clicks an agent tab and chooses **Split** (REQ-CHAT-2).
The Center shows two chats side-by-side, divided by a line
(REQ-CHAT-4), each a different agent with independent scroll and input
(REQ-CHAT-1). Closing one pane collapses back to a single chat.

### Scenario: Reviewing all changes
The user clicks the **+** on the Right section and adds **Review All**.
The Right section opens showing the combined multi-file diff
(REQ-CENTER-5). They could instead have added it to the Left.

### Scenario: (edge cases — the user is specifically interested in
these; to be surfaced during mocks/build)
- Tight width: chat hits its clamp, so opening Left + Right + a center
  diff forces sections to give space rather than crushing chat
  (REQ-PERSIST-3).
- A section's only panel is closed — does the section collapse?
- Splitting chat (2 agents) then opening a file — one chat pane is
  swapped for the diff (REQ-CENTER-3).

## Requirements

> Grounding note: a panel/docking system already exists
> (`DockingLayout`, `PanelDefinition` registry, `zoneAssignmentsAtom` /
> `activePanelPerZoneAtom` / `zoneOrderAtom` Jotai atoms persisted to
> localStorage). This redesign reshapes that system rather than
> building a new one. The file browser is already three decoupled
> components (`FileTree`, `ChangesTabContent`, `HistoryTabContent`).

### Panel zones & sections (REQ-ZONE-*)
- **REQ-ZONE-1:** There MUST be three peripheral panel zones — Left,
  Right, Bottom — plus a Center.
- **REQ-ZONE-2:** Left and Right each hold **exactly one panel
  section** (one tab strip, one active panel) for this iteration. The
  existing top/bottom vertical sub-split within a side is removed.
- **REQ-ZONE-3:** The Bottom zone is special — it hosts **only the
  terminal** (no panel section / plus-dropdown). Existing terminal
  multi-tab behavior is preserved within it.
- **REQ-SECTION-1:** A panel section is a collection of panels. Each
  panel is a single tab; **only one panel is active** per section.
- **REQ-SECTION-2:** A section has a **plus button** that opens a
  dropdown listing panels not currently visible in that section, to
  add them.
- **REQ-SECTION-3:** A section **never auto-collapses**. It can sit
  **open and empty**, showing just its + button (with an empty hint).
  Collapsing/expanding a section is always **explicit** via its
  toggle.

### Center: chat + diff (REQ-CENTER-*)
- **REQ-CENTER-1:** The Center always hosts Chat.
- **REQ-CENTER-2:** The single-file **diff/file viewer shares the
  Center with chat** (it is not a side panel). When a file is opened,
  the diff appears in the Center alongside chat.
- **REQ-CENTER-3:** The Center is a **2-pane split, maximum**. Pane A
  is always a chat. Pane B is **either** the diff/file viewer **or** a
  second agent's chat — the two are mutually exclusive. Opening a file
  while already split into two chats swaps one chat pane for the diff.
- **REQ-CENTER-4:** The diff/file viewer MUST show **one file at a
  time**. Drop the multi-file tab/scope row at the top of the viewer.
- **REQ-CENTER-5:** The combined **"Review All" view becomes its own
  panel** (registered like Files/Changes/Commits), rather than a tab
  inside the single-file diff viewer. It is **not visible by default**;
  the user adds it to the **Left or Right** section via that section's
  **+ dropdown**. It shows the combined multi-file diff.

### Panels & file browser split (REQ-PANEL-*)
- **REQ-PANEL-1:** The current `FileBrowserPanel` (three tabs:
  Browse/Changes/Commits) is split into **three separate panels** —
  **Files**, **Changes**, **Commits** — each registered in the panel
  registry. (Their underlying components — `FileTree`,
  `ChangesTabContent`, `HistoryTabContent` — are already decoupled.)
- **REQ-PANEL-2:** The set of panels addable via a section's **+
  dropdown** includes Files, Changes, Commits, **Review All**,
  **Browser**, and any other existing side panels (Actions, Skills,
  Notes) not currently in that section.

### Chat split (REQ-CHAT-*)
- **REQ-CHAT-1:** The user MUST be able to split the Center chat into
  two chats side-by-side, each showing a **different agent (task)** in
  the workspace, with independent scroll and input.
- **REQ-CHAT-2:** Split is triggered from the **agent tab right-click
  context menu** ("Split" option). Closing a pane **collapses** back to
  a single chat.
- **REQ-CHAT-3:** The agent tabs **stay below the chat content** (their
  current placement), **restyled to match the terminal tabs** (visual
  consistency with the bottom-zone terminal tab strip).
- **REQ-CHAT-4:** When split, a **divider line** is drawn between the
  two chats (matching the DiffSplitContainer divider).

### Vertical navigation sidebar (REQ-NAV-*)
Replaces the horizontal workspace tab bar and the top-bar icon cluster.
- **REQ-NAV-1:** The sidebar is a vertical list with **text labels**
  (not icon-only). Top to bottom: a top action list, then repos with
  their workspaces, then Settings + Help anchored to the bottom with
  **flexible space** between the workspace list and the bottom items.
- **REQ-NAV-2:** The **top action list** contains: **Home**, **Command
  Palette / Search**, and **New Workspace**.
- **REQ-NAV-3:** Workspaces are **grouped by repo** under
  **collapsible repo headers** (collapsed state persists). No grouping
  exists today — the current tab list is flat.
- **REQ-NAV-4:** Each repo header has a **+ to create a new workspace**
  in that repo (in addition to the top-list New Workspace).
- **REQ-NAV-5:** Each workspace row shows its **status dot**
  (unread/activity), as the current tabs do.
- **REQ-NAV-6:** Settings and Help anchor at the **bottom** of the
  sidebar.
- **REQ-NAV-7:** A **sidebar toggle** sits next to the window controls
  (close/minimize/maximize). Collapsing the sidebar **hides it
  entirely**; the top bar then shows two icons on its left (sidebar
  toggle + Left-section toggle, per REQ-TOPBAR-5).
- **REQ-NAV-8:** The notion of **"closed" workspaces is removed** — all
  workspaces appear in their repo group; the separate closed-workspaces
  pill goes away.

### Top bar (WorkspaceBanner) (REQ-TOPBAR-*)
- **REQ-TOPBAR-1:** The WorkspaceBanner becomes the **full-width top
  bar**, spanning the width minus the sidebar.
- **REQ-TOPBAR-2:** The **Left-section toggle** sits on the **left** of
  the top bar; the **Right-section toggle** sits on the **right**.
- **REQ-TOPBAR-3:** The **terminal toggle** sits on the **right** of
  the top bar.
- **REQ-TOPBAR-4:** The **repo metadata (RepoSegment)** is placed to
  the **right of the target-branch selector** (experimental
  placement). RepoSegment collapses to a **folder icon** that opens its
  existing dropdown.
- **REQ-TOPBAR-5:** When the sidebar is collapsed, the left of the top
  bar shows just **two icons** (sidebar toggle + Left-section toggle).
  When a panel section is already open, its corresponding toggle icon
  need not be shown.
- **REQ-TOPBAR-6:** The top bar **retains** the **branch name**,
  **target-branch selector**, and **diff summary** (file-change
  counts) from today's WorkspaceBanner, reflowed into the full-width
  bar.
- **REQ-TOPBAR-7:** The **PR/MR button has no dropdown in any state**.
  No PR → a **create-PR/MR button**; open PR → a **link** to the PR;
  merged/closed → a disabled-looking link. The open-PR detail dropdown
  (pipeline status, reviews, comments) is **dropped**.
- **REQ-TOPBAR-8:** **No progressive-collapse work this iteration.**
  Going full-width should relieve the space pressure; we'll ship
  without the current `useProgressiveCollapse` priority logic and see
  how it feels. Re-introducing graceful collapse for narrow widths is a
  **follow-up task** (see Open Questions).

### Reduce icons / three-dot menus (REQ-ICONS-*)
- **REQ-ICONS-1:** For this iteration, **remove** the secondary
  per-panel icons rather than relocating them into three-dot menus.
  Specifically remove the **file browser** icons: flat-list toggle,
  collapse-all, search, refresh.
- **REQ-ICONS-2:** Maintain a **doc listing every removed icon/action**
  (e.g. `agent_docs/compact-workspace-layout/removed-icons.md`) so they
  can be reintroduced behind three-dot context menus later.

### Default layout (REQ-DEFAULT-*)
- **REQ-DEFAULT-1:** On first load (empty localStorage):
  - **Center:** a single chat.
  - **Left section:** visible, containing **Files, Changes, Commits**
    (one active — Files).
  - **Right section:** **empty and collapsed** (user can add Browser or
    Review All via its + dropdown).
  - **Bottom (terminal):** collapsed.

### Persistence (REQ-PERSIST-*)
- **REQ-PERSIST-1:** **Visibility** is **per-workspace** — each
  workspace remembers which sections/panels are open, the active panel,
  sidebar collapsed state, and repo-group collapse. (Builds on the
  existing `usePerWorkspacePanelLayout` option.)
- **REQ-PERSIST-2:** **Section sizes are shared (global)** and stored
  as a **percentage of the screen** — chat, file/diff viewer,
  Left/Right sections.
- **REQ-PERSIST-3:** Sizes are **clamped** so the chat can only shrink
  so far; when space is tight, other sections **adjust smartly** rather
  than letting chat collapse. (A `CENTER_PANEL_MIN_WIDTH_PX` clamp
  already exists to build on.)
- **REQ-PERSIST-4:** All of the above persists via **localStorage**.

## Non-Goals

- **Backward-compatibility** with the existing layout. The old layout
  can be removed/replaced; we do not need a feature flag or a way to
  toggle back.
- **Building the three-dot overflow menus** this iteration. We
  **remove** the secondary icons and record them in a doc
  (REQ-ICONS-2); wiring them into three-dot context menus is deferred.
- **Vertical stacking of two sections within a side.** One section per
  side this iteration (possible later experiment).
- **Closed-workspaces concept.** Removed entirely (REQ-NAV-8), not
  reworked.
- **3-pane center.** The center is 2 panes max (REQ-CENTER-3).

## Open Questions

- **Top bar exact arrangement.** Placements are decided
  (REQ-TOPBAR-2..7) but the precise left-to-right order, spacing, and
  what shows when collapsed vs. open is best nailed down in the mock.
- **Agent-tab restyle details.** REQ-CHAT-3 fixes placement (below the
  chat) and intent (match terminal tabs); exact styling settled in the
  mock/build. Whether each pane gets its own strip in a 2-chat split,
  or one shared strip drives both, is a minor detail to settle in the
  mock.

## Follow-up Tasks (deferred, not this iteration)

- **Top-bar graceful collapse for narrow widths** (REQ-TOPBAR-8). Ship
  full-width without progressive collapse first; revisit if it feels
  cramped on small windows.
- **Three-dot overflow menus** — reintroduce the removed per-panel
  icons (tracked in `removed-icons.md`, REQ-ICONS-2) behind three-dot
  context menus.
- **Split a side into two sections** — start with one section per side
  (REQ-ZONE-2); may experiment later with splitting a side into two.
  Noted so the structure doesn't preclude it.
