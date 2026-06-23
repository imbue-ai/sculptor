# Supplemental: persistence interface

Companion to `../state_design.md` → "Persistence and the swap boundary". Defines
the consolidated snapshot shapes and the `LayoutPersistenceAdapter` boundary that
makes the storage backend swappable (localStorage today → backend API later)
without touching the state model.

## Snapshot shapes

One consolidated object per scope. These are the only things the adapter
serializes.

```ts
type WorkspaceLayoutState = {
  // Open-panel set + placement: a panel's presence here means it is "open".
  placement: Partial<Record<PanelId, SubSectionId>>;
  // Tab order within each sub-section.
  order: Partial<Record<SubSectionId, PanelId[]>>;
  // Active (shown) panel per sub-section.
  activePanel: Partial<Record<SubSectionId, PanelId>>;
  // Expanded/collapsed per section (center omitted — always expanded).
  expanded: Partial<Record<SectionId, boolean>>;
  // Split state per section (absent = unsplit). Ratio rides here (per-workspace).
  splits: Partial<Record<SectionId, SectionSplit>>;
  // The active sub-section (the focused pane); null → defaults to center on load.
  activeSubSection: SubSectionId | null;
};

type GlobalLayoutState = {
  sectionSizes: { left: number; right: number; bottom: number };  // percentages of content area
  sidebarWidthPx: number;
  sidebarCollapsed: boolean;
  // Panel-internal view prefs that are global (shared across workspaces):
  masterDetailListWidthPx: number;          // shared across Files/Changes/Commits (goals.md)
  // (diff view mode, tree/flat, etc. may be added here as global panel prefs)
};
```

Scope-addressing:

```ts
type LayoutScope =
  | { kind: "workspace"; workspaceId: string }
  | { kind: "global" };

type LayoutSnapshotFor<S extends LayoutScope> =
  S extends { kind: "workspace" } ? WorkspaceLayoutState : GlobalLayoutState;
```

## The adapter interface

The state model talks **only** to this interface — never to `localStorage` or any
backend client directly.

```ts
interface LayoutPersistenceAdapter {
  /**
   * Synchronously return the cached snapshot for a scope, or undefined if it is
   * not (yet) hydrated. MUST be synchronous — it is the source for the pre-paint
   * layout restore. (localStorage: JSON.parse; backend: in-memory prefetch cache.)
   */
  read<S extends LayoutScope>(scope: S): LayoutSnapshotFor<S> | undefined;

  /** Persist a scope's snapshot. Debounced/coalesced; fire-and-forget. */
  write<S extends LayoutScope>(scope: S, snapshot: LayoutSnapshotFor<S>): void;

  /** Drop a scope (workspace deleted). */
  remove(scope: LayoutScope): void;

  /**
   * Begin async hydration of a scope into the cache that `read` serves.
   * No-op for localStorage (already synchronous). For a backend, a GET that
   * fills the cache — call ahead of navigation so `read` finds it.
   */
  prefetch?(scope: LayoutScope): void;
}
```

The adapter is installed once (provider / module singleton). The Jotai layout
atoms call `read` for their initial value and `write` on mutation; nothing else
knows where the bytes live.

### `LocalStorageLayoutAdapter` (today)

- `read` → `JSON.parse(localStorage.getItem(key(scope)))` (synchronous).
- `write` → debounced `localStorage.setItem` (coalesce rapid drag/resize updates;
  flush pending writes on `beforeunload`).
- `remove` → `localStorage.removeItem`.
- `prefetch` → no-op (reads are already synchronous).
- Keys: one per workspace (`sculptor-layout-ws-<id>`) and one global
  (`sculptor-layout-global`). Consolidated — not the prototype's many keys.

### `BackendLayoutAdapter` (later)

- Maintains an in-memory cache (`Map<scopeKey, snapshot>`).
- `prefetch(scope)` → GET the snapshot into the cache (called on app load for the
  global scope + recent workspaces, and on navigation intent/hover for a target
  workspace).
- `read` → return from the cache synchronously (may be `undefined` → the shell
  shows last-known/stale or an in-place skeleton, then updates; never a spinner —
  `goals.md` → "Workspace switching should look seamless").
- `write` → debounced PUT.
- `remove` → DELETE.

Swapping localStorage → backend is changing which adapter is installed. No atom
or component changes.

## Restore (pre-paint)

The "first committed frame is the full layout" bar (`goals.md` → "Workspace
switching") is met because restore is a single synchronous read applied before
paint:

1. The layout atoms' initial values come from `adapter.read(scope)` synchronously
   on first access — so the very first render already has the persisted layout.
2. With a backend, `prefetch` must have populated the cache earlier; if it has
   not, the shell renders the section frames at their (global) sizes plus
   skeleton/stale content and swaps in real content when the fetch resolves.

## Switch sequence

On navigating to workspace `W`, all of the following run in the **same pre-paint
(layout-effect) flush**, so the first painted frame shows `W`'s full layout:

1. `switchActiveWorkspaceAtom({ workspaceId: W, defaultLayout })` writes
   `activeWorkspaceIdAtom = W`. Every per-workspace proxy now resolves to `W`'s
   snapshot. On first visit, the default layout is seeded (`goals.md` → "Default
   layout").
2. The panel registry is set to `W`'s static + dynamic (agent/terminal) panels.
3. The active agent is placed into the center section (or activated if already
   open); on first visit the terminal is seeded into the (collapsed) bottom
   section. (See `panel_registry.md`.)

Because these are layout effects (not passive effects), they commit before paint —
there is no frame showing the previous workspace's layout under `W`'s URL, and no
second-pass reflow.

## Deletion and no backwards compatibility

- On workspace delete, `removeWorkspaceLayoutAtom` drops the in-memory family
  entry and calls `adapter.remove({ kind: "workspace", workspaceId })`.
- **No migration.** The adapter reads only the consolidated keys/rows defined
  here. Layouts created before this work are ignored, and the rewrite stops
  writing the prototype's many separate keys (`goals.md`: *"We do not migrate or
  support layouts created before this work."*).
