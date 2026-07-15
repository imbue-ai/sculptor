# Workspace Grouping — Architecture

Implementation contract for the spec in [spec.md](./spec.md). Each build
stage follows this document; deviations get recorded here first.

## Data model (backend)

- **`WorkspaceGroupID`** (`sculptor/sculptor/primitives/ids.py`): new
  `ObjectID` subclass, tag `wsg`.
- **`WorkspaceGroup(DatabaseModel)`** (`sculptor/sculptor/database/models.py`):
  - `object_id: WorkspaceGroupID`
  - `organization_reference: OrganizationReference`
  - `project_id: ProjectID` — groups are repo-scoped (REQ-GROUP-1)
  - `name: str` — default `"Group N"`, N = per-project index (REQ-GROUP-6)
  - `color: str` — Radix accent name (REQ-GROUP-7)
  - `created_via_cli: bool = False` — drives the sidebar CLI badge (REQ-CLI-3)
  - `is_deleted: bool = False` — soft delete, matching Workspace
  - Standard automanaged two-table pattern + Alembic migration.
- **Membership lives on the workspace**: `Workspace.group_id:
  WorkspaceGroupID | None = None` (migration adds the column to
  `workspace` + `workspace_latest`). At-most-one group per workspace
  (REQ-GROUP-2) is structural; member *sets* stream with the workspaces
  the frontend already receives.
- **Auto-dissolve (REQ-GROUP-8)**: any transaction that clears a
  workspace's `group_id` (remove, ungroup, workspace delete, move to
  another group) checks the source group's remaining live members and
  soft-deletes the group at zero. Same transaction — never a follow-up
  write.

## API (backend)

All endpoints enforce `enable_workspace_groups`; when the flag is off
they return HTTP 409 with a stable error code
`workspace_groups_disabled` (REQ-FLAG-4).

| Endpoint | Behavior |
|---|---|
| `POST /api/v1/workspace-groups` | Create. Body: `project_id`, `workspace_ids` (min 1, REQ-GROUP-8), optional `name`, `color`, `created_via_cli`. Server fills name ("Group N") and color (cycle curated palette by count of live groups in the project). Workspaces already in another group move; source groups auto-dissolve if emptied. |
| `GET /api/v1/workspace-groups?project_id=` | List live groups (optionally per project). |
| `GET /api/v1/workspace-groups/{id}` | Show, including member workspace ids. |
| `PATCH /api/v1/workspace-groups/{id}` | Rename / recolor (`name?`, `color?`). |
| `POST /api/v1/workspace-groups/{id}/workspaces` | Add member (body `workspace_id`; must be same project). |
| `DELETE /api/v1/workspace-groups/{id}/workspaces/{workspace_id}` | Remove member; auto-dissolve at zero. |
| `DELETE /api/v1/workspace-groups/{id}` | Ungroup (REQ-GROUP-4): clear members' `group_id`, soft-delete the group. Never deletes workspaces. |

- **Streaming (REQ-GROUP-3)**: `WorkspaceGroup` rides the existing
  `CompletedTransaction → UserUpdate` path (a `workspace_groups` field
  beside the workspaces list). No new stream types.
- **Flag**: `enable_workspace_groups: bool = False` on `UserConfig`
  (`sculptor/sculptor/config/user_config.py`), toggle in Settings with
  the other experimental flags.
- **Workspace create endpoints are untouched** — the CLI composes
  create-workspace + create-group (see below).

## Curated palette

Eight Radix accents, cycled per project by the backend and shown as the
swatch row by the frontend (REQ-GROUP-7):

```
blue, green, orange, purple, pink, teal, amber, red
```

Single source of truth backend-side (constant exported through the API
schema); the frontend swatch row uses the generated constant/type, not
its own list. `color` accepts any Radix accent name so future palettes
don't break old rows.

## sculpt CLI

- New `tools/sculpt/sculpt/commands/group.py` typer sub-app: `create
  --workspace <id>... [--name] [--color]`, `list [--repo]`, `show`,
  `rename`, `add <group> <ws>`, `remove <group> <ws>`, `ungroup` — each
  with `--json`, `sculpt schema` registry entries, respx unit tests
  (REQ-CLI-1).
- `sculpt run` / `sculpt workspace create` gain `--group <id>` and
  `--no-group`; default is auto-group: after workspace creation, POST a
  new group with `created_via_cli=true` (REQ-CLI-2/3). Outputs carry
  `group_id` (REQ-CLI-4).
- **Disabled-flag asymmetry (REQ-FLAG-4)**: explicit group intent
  (`sculpt group *`, `--group`) surfaces the `workspace_groups_disabled`
  error; implicit auto-group catches it and proceeds loose with a
  one-line note.
- Client regenerated via `just generate-sculpt-client`.

## Frontend

- **Types**: `just generate-api` after the backend stage.
- **State ownership (REQ-GROUP-9)**: groups arrive via the unified
  stream; mutations go through canonical hooks in
  `src/common/state/mutations/` with real failure paths. No optimistic
  Jotai writes with fire-and-forget HTTP.
- **Naming collision**: the new entity is `WorkspaceGroup` everywhere.
  The landed repo-section atom `sidebarWorkspaceGroupsAtom` (which
  holds `RepoGroup`s) is renamed `sidebarRepoGroupsAtom` in the data
  layer stage; new group code uses `workspaceGroup*` prefixes.
- **Ordering (`SidebarOrderState`, `persistence/types.ts`)**: the
  existing `workspaces[projectId]` lane becomes the repo section's
  *mixed children* order — workspace ids and group ids share the lane
  (distinguishable by `ws_`/`wsg_` prefixes; old snapshots contain only
  workspace ids and stay valid — no version bump). A new optional
  `groupMembers?: Partial<Record<string, Array<string>>>` map stores
  member order per group, same stored-first semantics.
- **Collapse**: per-group boolean in localStorage, mirroring
  `collapsedRepoGroupsAtom` (`sculptor-collapsed-workspace-groups`).
- **UI (REQ-UI-1, Dia-style)**: a group renders as a header row
  (chevron + accent-tinted name + always-visible "⋯", no swatch) plus member
  rows indented one level deeper, all direct participants of the repo
  section's flat lane, wrapped in an always-visible accent box (rest +
  hover shades) whose padding insets the row pills; a selected member
  re-stamps the app accent so it looks identical to a selected loose
  row. Text-only menu per REQ-MENU-1; workspace context menu carries
  the two grouping actions (REQ-MENU-2); CLI badge is a small text chip
  on the header.
- **D&D (the flat-lane model, REQ-DND-1..7)**: each repo section is ONE
  flat `SortableContext` whose items are the visible rows (loose rows,
  group headers, member rows); membership is *projected from position*
  by a pure module (`sidebarDropProjection.ts`) shared by the
  drag-over preview, the keyboard path, and the drop commit. During a
  drag every projection re-renders the lane (the sorting strategy is a
  no-op; sortable transforms would slide rows without moving the group
  boxes wrapping them), so the in-flow placeholder always sits at the
  projected slot and a group's box always wraps exactly its rows,
  while an axis-locked `DragOverlay` copy rides the rail under the
  pointer. Group-edge slots resolve geometrically — inside while the
  pointer is within the box's vertical extent (inset a few px at the
  edges so between-box drops don't demand pixel aim), outside in the
  gaps; keyboard drags default inside with Left/Right flipping
  (REQ-DND-6). Drops apply membership + order optimistically with
  rollback + toast on failure (REQ-DND-7). Repo sections stay an outer
  sortable list, keeping cross-repo drops structurally impossible.

## Build stages

1. Backend entity + API + flag + streaming (+ backend tests)
2. CLI (after `just generate-sculpt-client`)
3. Frontend data layer (after `just generate-api`)
4. Frontend UI (cards, menus, colors, collapse)
5. Sidebar D&D extension
6. Integration tests + full gate
