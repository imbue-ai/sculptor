# Supplemental: panel registry

Companion to `../component_hierarchy.md` → "The panel registry and dynamic
panels". Defines panel definitions, kinds, and the add/close/rename lifecycle, per
`goals.md` → "Panels".

## Panel definition

```ts
type PanelKind = "static" | "agent" | "terminal";

type PanelDefinition = {
  id: PanelId;                       // "files" | "agent:<taskId>" | "terminal:<wsId>:<n>"
  displayName: string;
  icon: LucideIcon;
  kind: PanelKind;                   // default "static"
  defaultSection?: SubSectionId;     // where it lands by default (review-all/browser: none)
  component: ComponentType;          // the content; decoupled from the shell
  tabIcon?: ReactNode;              // e.g. agent live status dot
  contextMenuActions?: ContextMenuItem[];   // goals.md → "Panels": right-click actions
  // Keyboard shortcuts + Cmd+K entries are attached via the keybindings registry,
  // configured on the KEYBINDINGS settings page (NOT the deprecated Panels page).
};
```

There is **no** `enabled` / `defaultEnabled` / `isBuiltin` flag — the Panels
settings page is deprecated (`goals.md` → "Features to deprecate"), so panels are
registered statically with no user enable/disable. See `naming_map.md` → "Deleted".

## Static panels (single-instance)

From `goals.md` → "Files, Changes and Commits" / "Review all" / "Panels":

| id | Display | Default | Notes |
|---|---|---|---|
| `files` | Files | left | explorer: file tree + diff viewer |
| `changes` | Changes | left | uncommitted/branch changes + diff viewer |
| `commits` | Commits | left | commit history + diff viewer |
| `review-all` | Review All | (none) | not open by default; combined multi-file diff |
| `actions` | Actions | right | |
| `skills` | Skills | right | |
| `browser` | Browser | (none) | not open by default |
| `notes` | Notes | right | |

Files/Changes/Commits are now **separate panels**, each with its own
explorer (a file-list/changes/commit-history sidebar + its own diff/file
viewer). The file-list sidebar width is **shared** across the three (global —
`persistence_interface.md` → `GlobalLayoutState.explorerListWidthPx`). Each is
single-instance.

## Dynamic panels (multi-instance)

Agents and terminals are the **only** multi-instance panels (`goals.md` →
"Panels"). They are per-workspace and derived from the task/terminal data atoms,
then merged into the registry for the *active* workspace:

- **Agent panel** — id `agent:<taskId>`, kind `"agent"`, default section `center`.
  Wraps the existing chat interface — renders `<ChatPanelContent taskId={taskId}/>`
  (the chat takes an explicit `taskId` prop, decoupled from the route). A workspace
  may have zero, one, or many
  agents (`goals.md` → "Agent Panel"; the zero-agent case is the empty center
  section). Closing an agent panel deletes the agent → shows the existing delete
  confirmation.
- **Terminal panel** — id `terminal:<wsId>:<index>`, kind `"terminal"`, default
  section `bottom`. Wraps the xterm container. Closing closes the terminal → shows
  a confirmation (for now).

Component identities are **cached by id** so rebuilding the registry on every task
tick never remounts a live agent/terminal panel (a hard requirement for "each
panel mounts at most once per switch").

Multi-instance panels are **renamable**; single-instance panels are not
(`goals.md` → "Panels").

## Adding a panel

`goals.md` → "Adding a panel". Each section header's "+" opens a **dropdown**
(not the cmdk overlay — we reuse only the AddPanel row styling, per
`design_extraction.md`):

- Pinned: "New {recent} agent" with its Cmd+Shift+T binding, then "New terminal",
  then every single-instance panel not already open.
- The new-agent keyboard binding and the Cmd+K "add agent" entry always create the
  agent in the **center** section (and the center's primary sub-section when the
  center is split), regardless of the active section.
- Cmd+K also offers "Add panel" → choose location → valid panels for that location.

The empty-section launcher (`goals.md` → "Section empty state") shows a centered
add-panel button plus up to five quick actions: always "New {recent} agent" and
"New terminal", then up to three most-recently-closed panels (transient — the
list resets on reload).

## Closing / moving

- Closing a panel removes it from `placement` (returns it to the unplaced pool,
  where the "+" offers it again). Closing the last panel leaves the section (or
  split sub-section) expanded showing the section empty state — see the
  invariants in `state_atoms.md` → "Write-side action atoms".
- Agents/terminals are **not** offered in the "+" re-add list (closing ends them;
  there is no "reopen" pool) — only single-instance panels are.
- Panels drag between sections and reorder within a section via the single
  `PanelDndProvider` (`component_hierarchy.md` → "Drag-and-drop architecture").
