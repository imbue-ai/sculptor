# Workspace Grouping

## Mocks

See [mocks.html](./mocks.html) for interactive HTML mocks illustrating
the user flows described below (Variant B — tinted container — is the
chosen direction and default tab; Variants A and C are kept as an
exploration record). [mocks.context.md](./mocks.context.md) records the
mock session's decisions and rejected alternatives.

## Overview

An experimental feature that lets users organize related workspaces into
**groups** in the sidebar. A group is a visual collection of workspaces —
modeled after Dia browser's tab groups — so users working across several
related workspaces (e.g. a feature split across stacked branches, or a
fleet of agents attacking one problem) can see and manage them as a unit.

A group has a name and a color, can collapse/expand, and nests inside a
repo section (`repo > group > workspaces`). Groups are purely a
container: they organize workspaces, they never own or delete them.

Groups are also the default container for CLI-driven work: any workspace
created via `sculpt` is born inside its own new group, and `sculpt` can
create and manage groups directly.

The feature is **experimental**: gated behind Sculptor's existing
experimental-settings mechanism (a `UserConfig` flag), off by default;
users opt in.

## User Scenarios

### Create a group from a workspace

User right-clicks a workspace row in the sidebar and picks **New group
from workspace**. A rounded, accent-tinted group card appears in place,
wrapping that workspace (REQ-MENU-2, REQ-UI-1). The group gets an
indexed default name ("Group 1", "Group 2", …) and the next color from
the curated palette (REQ-GROUP-6, REQ-GROUP-7); the user renames it via
the group menu whenever they like.

### Add a workspace to an existing group

User right-clicks a loose workspace and hovers **Add to group ›**. A
submenu lists the repo's existing groups, each with its color dot, with
**New group…** at the bottom (REQ-MENU-2). Picking a group moves the
workspace into that group's card.

### Drag a workspace into / out of / within a group

With sidebar drag-and-drop landed (PR #309, SCU-1702), the
user drags a loose workspace onto a group card; the card lights up with
an accent ring, stronger tint, and a dashed drop slot, and the drop adds
the workspace as a member (REQ-DND-1). Dragging a member out into the
loose list releases it from the group without deleting anything
(REQ-DND-3) — and if it was the last member, the group dissolves
(REQ-GROUP-8). Dragging within the group reorders members via an
insertion line (REQ-DND-2). The whole group card is itself draggable to
re-order it among the repo section's children (REQ-DND-4).

### Manage a group from its menu

Hovering the group header reveals a "⋯" trigger; right-click works too
(REQ-MENU-1). The text-only menu offers **New workspace in group**,
**Rename…**, **Collapse group**, a color-swatch row, and **Ungroup**.
Picking a swatch retints the card immediately (REQ-MENU-4). **New
workspace in group** runs the normal new-workspace flow for the repo and
the resulting workspace lands in the group (REQ-MENU-3).

### Collapse and expand

Clicking the chevron (or **Collapse group**) shrinks the group to just
its header card — name and color only, no member preview, no count
(REQ-UI-3). Expanding restores the member rows. Collapse state survives
app restarts.

### Ungroup

User picks **Ungroup** from the group menu. The container dissolves and
its workspaces return to the repo's loose list. No workspace is deleted;
there is no "delete group" action at all (REQ-GROUP-4).

### CLI-driven work is born grouped

User (or an orchestrating agent) runs `sculpt run "fix the flaky test"`.
The new workspace + agent appear in the sidebar already wrapped in a
fresh group with a CLI badge and an automatically assigned color
(REQ-CLI-2, REQ-CLI-3), streamed live to the UI (REQ-GROUP-3). The user
can rename, recolor, add siblings, or ungroup it like any other group.

### Managing groups from the terminal

An orchestrating script fans three workspaces out into one shared
group: the first `sculpt run` auto-creates the group and returns its id;
the two siblings join it with `sculpt run --group <id>`; `sculpt group
list --json` shows the result (REQ-CLI-1, REQ-CLI-2, REQ-CLI-4). A lone
utility workspace that shouldn't be grouped uses `--no-group`. The JSON
output is stable and documented via `sculpt schema` like existing
commands.

### Workspace deletion inside a group

User deletes a workspace that belongs to a group. The workspace goes
through the normal delete flow and simply disappears from the group's
card (REQ-GROUP-5). If it was the group's last member, the group
auto-dissolves — a group never exists empty (REQ-GROUP-8).

### Feature flag off

With the experimental flag off (the default), the sidebar renders
exactly as today — no group cards, no new menu items (REQ-FLAG-2). If
groups were created and the flag is later disabled, the sidebar goes
flat but group data is retained; re-enabling the flag brings the groups
back (REQ-FLAG-3). While off, `sculpt group` commands fail with a clear
"enable the workspace-groups experiment" error and workspace creation
behaves as if `--no-group` were always passed (REQ-FLAG-4).

## Requirements

### Group model & lifecycle

- **REQ-GROUP-1**: Users MUST be able to collect workspaces into a named,
  colored group. A group belongs to exactly one repo (project) and MUST
  only contain workspaces of that repo.
- **REQ-GROUP-2**: A workspace MUST belong to at most one group.
- **REQ-GROUP-3**: Groups MUST be persisted by the backend as shared
  state: the sidebar and the `sculpt` CLI MUST see the same groups, and
  group changes MUST stream to the UI in real time via the existing
  unified-stream mechanism.
- **REQ-GROUP-4**: **Ungroup** MUST dissolve the group and release its
  members back to the repo's loose list. It MUST NOT delete workspaces.
  There MUST NOT be a "delete group" action.
- **REQ-GROUP-5**: Deleting a workspace MUST remove its group membership;
  groups MUST NOT show stale/deleted members.
- **REQ-GROUP-6**: New groups MUST get an indexed default name ("Group
  1", "Group 2", … — index scoped per repo), renameable at any time via
  the group menu. The same scheme applies to CLI-created groups.
- **REQ-GROUP-7**: New groups MUST get an automatic color by cycling a
  curated palette (~8 Radix accent colors) per repo, so sibling groups
  are visually distinct. The context-menu swatch row SHOULD offer the
  same curated palette.
- **REQ-GROUP-8**: A group MUST always contain at least one workspace:
  every creation path requires an initial member, and a group whose
  last member leaves (workspace deleted, dragged out, or removed via
  CLI) MUST auto-dissolve. Empty groups MUST NOT exist.
- **REQ-GROUP-9**: Frontend group mutations MUST follow the
  state-ownership rules in `docs/development/review/sculptor.md`
  (SCU-1120): backend-owned facts change through the canonical mutation
  hooks with real failure paths — never an optimistic store write with
  a fire-and-forget HTTP call.

### Sidebar UI

- **REQ-UI-1**: A group MUST render as a rounded, accent-tinted card with
  a faint colored border wrapping its header and member rows (mock
  Variant B), nested inside the repo section. Loose workspaces MUST
  continue to render directly under the repo header alongside groups.
- **REQ-UI-2**: The group header MUST show only a chevron, a color
  swatch, and the name — no workspace count and no group-level
  run/status indicator.
- **REQ-UI-3**: A collapsed group MUST shrink to its header card only (no
  member preview). Collapse state SHOULD persist across restarts,
  following the existing repo-section collapse pattern.
- **REQ-UI-4**: Workspace rows inside a group MUST keep their existing
  behavior (status dot, navigation, rename, hover actions, context
  menu).
- **REQ-UI-5**: Long group names MUST truncate with an ellipsis without
  breaking the card layout.

### Menus

- **REQ-MENU-1**: The group menu MUST open from a hover "⋯" trigger on
  the header and from right-click. Items are text-only (no leading
  icons): *New workspace in group*, *Rename…*, *Collapse group*, a
  color-swatch row, *Ungroup*.
- **REQ-MENU-2**: The workspace context menu MUST gain two grouping
  actions: **New group from workspace** and **Add to group ›**, where the
  submenu lists the repo's existing groups (with color dots) plus a
  **New group…** entry.
- **REQ-MENU-3**: **New workspace in group** MUST create a workspace in
  the group's repo and place it in the group.
- **REQ-MENU-4**: Selecting a color swatch MUST retint the group
  immediately.

### Drag and drop (extends the landed sidebar reorder model)

Sidebar manual re-ordering landed with PR #309 (SCU-1702). The model
this feature extends: repo sections and the workspace rows within each
are separate vertical dnd-kit sortable lists, draggable by pointer and
by keyboard (focus → Space → arrows → Space); each drop materializes
the full visible order into `sidebarOrder` in the global layout
snapshot ("stored-first": stored ids render first, unstored items
follow alphabetically, stale ids are skipped on read). Landed drags are
deliberately locked to their parent container — moving a workspace
*between* containers (loose list ↔ group card) is new interaction
ground this feature breaks.

- **REQ-DND-1**: Dropping a workspace onto a group card MUST add it as a
  member, with a drop affordance (accent ring, stronger tint, dashed
  drop slot).
- **REQ-DND-2**: Members MUST be reorderable within a group via an
  insertion line. Member visual order persists in the sidebar-order
  layout snapshot following the landed stored-first convention — the
  backend owns *membership*, the frontend layout owns *visual order*
  (`sculpt group show` lists members without implying sidebar order).
- **REQ-DND-3**: Dragging a member out of the group into the loose list
  MUST release its membership and MUST NOT delete the workspace (last
  member out dissolves the group per REQ-GROUP-8).
- **REQ-DND-4**: A group MUST be draggable as a single unit, and groups
  MUST participate in the manual sidebar ordering exactly like loose
  workspace rows — a repo section's children (group cards + loose
  workspaces) form one re-orderable lane with no forced groups-first
  placement.
- **REQ-DND-5**: Group-membership drags MUST NOT regress the landed
  same-list reorder interactions, and SHOULD be operable through the
  landed keyboard drag path as well as by pointer.

### sculpt CLI

- **REQ-CLI-1**: A `sculpt group` command family MUST exist following the
  existing typer sub-app pattern: create (requires one or more initial
  workspace ids, per REQ-GROUP-8), list, show, rename, add / remove a
  workspace, and ungroup — each with `--json` output, entries in the
  `sculpt schema` registry, and respx-based unit tests.
- **REQ-CLI-2**: Every workspace-creating `sculpt` flow (`sculpt run`
  and `sculpt workspace create`) MUST auto-create a new group for the
  workspace by default, and MUST support `--group <id>` (join an
  existing group instead) and `--no-group` (create the workspace
  loose).
- **REQ-CLI-3**: A CLI-created group MUST be visually identifiable in the
  sidebar (CLI badge) and get an automatically assigned color.
- **REQ-CLI-4**: CLI outputs for workspace/agent creation MUST include
  the group id when a group was created or targeted.

### Experimental gating

- **REQ-FLAG-1**: The feature MUST be gated behind a `UserConfig`
  experimental flag, default off, toggleable in Settings like existing
  experimental features.
- **REQ-FLAG-2**: With the flag off, the sidebar and menus MUST render
  exactly as today.
- **REQ-FLAG-3**: Disabling the flag MUST NOT destroy group data: groups
  are hidden while off and reappear when the flag is re-enabled.
- **REQ-FLAG-4**: While the flag is off, `sculpt group` commands MUST
  fail with a clear error directing the user to enable the experiment,
  and workspace-creating commands MUST NOT auto-create groups (as if
  `--no-group` were passed).

## Non-Goals

- **Cross-repo groups.** Groups are scoped to a single repo section.
- **Nested groups.** No groups inside groups.
- **Group chrome extras.** No workspace count and no aggregate run-state
  on the header; no member preview on collapsed groups (all explicitly
  removed during mock iteration).
- **Deleting workspaces via group actions.** Groups only organize; a
  group goes away only via Ungroup or by emptying out (REQ-GROUP-8),
  never by deleting its workspaces.
- **Empty groups.** A group cannot exist without members — no empty-card
  state, no "drag workspaces here" placeholder (cut when the ≥1-member
  invariant was adopted; the mock's empty-state card is superseded).
- **Building sidebar drag-and-drop itself.** Manual re-ordering landed
  separately (PR #309, SCU-1702); this feature defines the
  group-specific drop behaviors on top of it.
- **Dia features that don't map:** pinning groups, "Chat with group",
  duplicate group, move-to-window, closed-group archival.

## Open Questions

- **Naming collision with existing code:** the landed sidebar code
  already uses "group" for *repo sections* — `RepoGroup`,
  `sidebarWorkspaceGroupsAtom` (which holds repo groups),
  `collapsedRepoGroupsAtom`, `reorderSidebarRepoGroupAtom`. The
  architecture phase must pick non-colliding names for workspace
  groups, and decide whether to rename the repo-section code for
  clarity.
- **Layout snapshot extension:** how `SidebarOrderState` grows to
  represent a repo section's mixed children (group cards + loose
  workspaces) plus per-group member order. New fields must stay
  optional or bump `LAYOUT_SNAPSHOT_VERSION` so snapshots persisted
  before the feature still load (see the existing optional-field
  precedents in `persistence/types.ts`).
