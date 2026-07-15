# Workspace Grouping — Mock Context

## Description

Workspace Grouping (experimental, behind a feature flag) lets users collect
related workspaces into a named, colored **group** in the Sculptor sidebar —
modeled after Dia browser's tab groups. A group manages several workspaces
attacking one feature as a single unit: it has a name, a color, and can be
collapsed/expanded. Workspaces can be dragged in and out (drag-and-drop
re-ordering is being built separately; assume it exists). A right-click
context menu on the group header offers actions like *New workspace in group*,
*Rename*, color swatches, and *Ungroup*.

Groups nest **inside** a repo section — the hierarchy is `repo > group >
workspaces`. Loose (ungrouped) workspaces still sit directly under the repo
header. Groups are also the default container for CLI-driven work: any
workspace created via the `sculpt` CLI is born inside its own new group.

The mock explores three end-to-end variants of the group's sidebar chrome and
covers the edge/empty states: a collapsed group, a single-workspace group,
a CLI-born group, and long-name truncation, plus the right-click context menu.

## Variants explored

- **Variant A — Colored left rail.** Group is a header row (chevron + color dot
  + name + count); its members are indented with a colored vertical rail down
  the left edge. Lightest "folder" feel. Collapsed shows name + rail + a
  stacked status-dot member preview.
- **Variant B — Tinted container.** The whole group (header + members) sits in a
  rounded, accent-tinted card with a faint colored border — the most literal
  read of Dia's group card. Collapsed shrinks to just the header card with a
  member preview row (favicon-analog: status dot + name).
- **Variant C — Labeled divider.** Lightest touch: a thin colored rule with a
  small uppercase color-label; members below indent normally. No container, no
  rail. Scales cleanly to many groups.

## Decisions

- **Group chrome = Variant B (tinted container).** The group renders as a
  rounded, accent-tinted card with a faint colored border wrapping the header
  and its member workspaces, so a group reads as a single draggable object.
  Chosen as the most literal read of Dia's group card. `mocks.html` now opens
  on the B tab by default (A/C kept as record).
- **Keep the group chrome minimal.** The group header shows only the chevron,
  a color swatch, and the name — **no workspace count** and **no group-level
  run/status indicator**. (Individual workspace rows keep their own status dots;
  that's existing sidebar behavior, unrelated to grouping.)
- **Collapsed = header only.** A collapsed group shrinks to just its header
  card (name + color). No member preview, no count, no aggregate state.
- **Group menu is text-only.** No leading icons on menu items. Contents:
  *New workspace in group*, *Rename…*, *Collapse group*, a color-swatch row,
  and *Ungroup*.
- **Ungroup, never delete.** There is no "delete group" action. A group is only
  a container; *Ungroup* dissolves it and releases its workspaces back to the
  repo — it never deletes workspaces.
- **Group menu opens from a hover "⋯" (and right-click).** The group header
  reveals a triple-dot menu trigger on hover, mirroring the workspace-row "⋯".
- **Groups are created from a workspace.** The workspace right-click menu gains
  two grouping actions at the top: **New group from workspace** (wraps it in a
  fresh group) and **Add to group ›** (move it into an existing group).
- **"Add to group ›" opens a submenu** listing the repo's existing groups (each
  with its color dot), followed by a **New group…** entry at the bottom.
  Picking a group moves the workspace into it.
- **Groups act as drag-and-drop targets.** (Sidebar D&D is built separately.)
  - Dropping a workspace onto a group card adds it as a member; the target
    lights up with an accent ring + stronger tint and shows a dashed drop slot.
  - A group can be created empty and shows a dashed "Drag workspaces here"
    prompt until its first member lands.
  - Members reorder within a group via an insertion line (lifted row dims).
  - Dragging a member out (into the loose list) releases it from the group —
    consistent with Ungroup, it never deletes the workspace.

## Rejected Alternatives

- **Variant A — Colored left rail.** Lighter/folder-like (color dot + vertical
  rail down members). Not chosen: reads more like an indent guide than a
  contained group; the container framing of B better matches the "manage as a
  unit" goal. Revisit if B's tint feels too heavy at scale.
- **Variant C — Labeled divider.** Near-weightless colored rule + uppercase
  label, no container. Not chosen: too quiet to make a group feel like an
  object you drag workspaces into. Revisit if the sidebar needs to hold many
  groups without visual weight.

## Tweaks Log

- Requested: Which direction resonates (A / B / C / blend)?
  Changed: User chose Variant B. Made B the default tab, recorded it under
  Decisions, moved A and C to Rejected Alternatives (HTML for all three kept).
- Requested: Simplify B — drop the workspace count and group run-state, remove
  "delete group" (keep only Ungroup), add a workspace right-click action to
  create a group from a workspace, drop the icons in the context menu, and show
  a triple-dot menu on hover.
  Changed: Removed all count badges and the collapsed member-preview/status from
  B (collapsed is now header-only). Rewrote the group menu as text-only (no
  icons), dropped "Delete group & workspaces", kept Ungroup, and anchored it to
  a hover "⋯" trigger on the header. Added a new edge-state card showing the
  workspace menu with "New group from workspace" + "Add to group ›". Updated the
  B intro copy and edge-state notes to match.
- Requested: Mock drag-and-drop and flesh out "Add to group".
  Changed: Added a "Creating & joining groups" section to Variant B with the
  workspace menu and an open "Add to group ›" submenu (existing groups w/ color
  dots + "New group…"). Added a "Drag & drop" section with four states: drop a
  workspace into a group (accent ring + dashed slot + floating drag chip), empty
  group awaiting first drop, reorder within a group (insertion line + dimmed
  row), and drag a member out of a group back to the loose list.
