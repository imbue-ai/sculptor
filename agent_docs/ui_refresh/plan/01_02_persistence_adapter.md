# Task 1.2: Consolidated snapshots + `LayoutPersistenceAdapter` + localStorage impl

## Goal

Build the persistence layer for the new workspace layout: the consolidated
snapshot shapes, the swappable `LayoutPersistenceAdapter` interface, and the
`LocalStorageLayoutAdapter` implementation. This is the boundary the Jotai layout
atoms (Task 1.3) read from and write to; nothing else touches storage.

## Stories addressed

PERSIST-01, PERSIST-02, PERSIST-03 (consolidated client-side persistence,
per-workspace vs. global split, survives restart); SWITCH-03 (synchronous reads
enable the no-spinner restore). No-migration rule.

## Background

**Project:** Sculptor frontend (TS + React + Jotai) under `sculptor/frontend/src`.
We are rewriting the workspace shell into the section/panel model from
`agent_docs/ui_refresh/goals.md`.

**Why a single adapter** (`agent_docs/ui_refresh/state_design.md` → "Persistence
and the swap boundary" and `supplemental/persistence_interface.md`): we are moving
toward a hosted web Sculptor that may persist layouts in a backend, so the storage
backend must be **swappable** (localStorage today → backend API later) without
reworking the state model. The model talks only to the adapter interface — never to
`localStorage` directly. Reads are **synchronous** (so the first render can restore
the layout before paint); writes are debounced/coalesced.

**Two scopes, two snapshot shapes** (`supplemental/persistence_interface.md` →
"Snapshot shapes"):
- `WorkspaceLayoutState` (one per workspace): `placement` (panel→sub-section map; a
  panel's presence = "open"), `order` (tab order per sub-section), `activePanel`
  (per sub-section), `expanded` (per section; center omitted — always expanded),
  `splits` (per section; absent = unsplit; ratio rides here), `activeSubSection`
  (`SubSectionId | null`, null → defaults to center on load).
- `GlobalLayoutState` (one total): `sectionSizes` ({left,right,bottom} percentages),
  `sidebarWidthPx`, `sidebarCollapsed`, `masterDetailListWidthPx` (shared across
  Files/Changes/Commits).

**No migration** (`goals.md` → "Persistence"; `persistence_interface.md` →
"Deletion and no backwards compatibility"): read only the new consolidated keys;
ignore old prototype keys; stop writing them.

This task depends on **Task 1.1** (`components/sections/sectionTypes.ts`), which
exports `SectionId`, `SubSectionId`, `PanelId`, and `SectionSplit`.

## Files to modify/create

- `sculptor/frontend/src/components/sections/persistence/types.ts` — new.
  `WorkspaceLayoutState`, `GlobalLayoutState`, `LayoutScope`, `LayoutSnapshotFor`.
- `sculptor/frontend/src/components/sections/persistence/LayoutPersistenceAdapter.ts`
  — new. The interface.
- `sculptor/frontend/src/components/sections/persistence/LocalStorageLayoutAdapter.ts`
  — new. The implementation + the installed singleton.
- `sculptor/frontend/src/components/sections/persistence/LocalStorageLayoutAdapter.test.ts`
  — new. Vitest.

## Implementation details

1. **`types.ts`** — define the snapshot shapes verbatim from
   `supplemental/persistence_interface.md` → "Snapshot shapes", importing
   `SectionId`/`SubSectionId`/`PanelId`/`SectionSplit` from `../sectionTypes`. Add:
   - `type LayoutScope = { kind: "workspace"; workspaceId: string } | { kind: "global" }`.
   - `type LayoutSnapshotFor<S>` conditional (workspace → `WorkspaceLayoutState`,
     global → `GlobalLayoutState`).
   - `const EMPTY_WORKSPACE_LAYOUT: WorkspaceLayoutState` and
     `const DEFAULT_GLOBAL_LAYOUT: GlobalLayoutState` constants for the
     "nothing persisted yet" case (the *default arrangement* seeding is Task 6.1;
     these are just safe empties/defaults — e.g. global sizes left/right/bottom as
     sane percentages, sidebar default width, collapsed false).
2. **`LayoutPersistenceAdapter.ts`** — the interface exactly as in
   `persistence_interface.md` → "The adapter interface": `read<S>(scope): Snapshot
   | undefined` (synchronous), `write<S>(scope, snapshot): void`
   (debounced/fire-and-forget), `remove(scope): void`, optional
   `prefetch?(scope): void`.
3. **`LocalStorageLayoutAdapter.ts`**:
   - Keys: `sculptor-layout-ws-<id>` per workspace, `sculptor-layout-global`
     (one helper `keyFor(scope)`).
   - `read` → `JSON.parse(localStorage.getItem(key))` wrapped in try/catch;
     return `undefined` on missing/parse error (never throw — a corrupt entry must
     not break startup).
   - `write` → debounce/coalesce per key (e.g. a `Map<key, snapshot>` of pending
     writes flushed on a short timer); rapid drag/resize updates collapse to one
     `setItem`. Register a `beforeunload` listener that flushes all pending writes
     synchronously.
   - `remove` → `localStorage.removeItem(key)` and drop any pending write.
   - `prefetch` → no-op (reads are already synchronous).
   - Export a module singleton `layoutPersistenceAdapter` (the installed adapter
     the atoms import). Swapping to a backend later is changing this one export.
4. Do **not** read or write any prototype/legacy keys (no `sculptor-zone-*`,
   `sculptor-tabs`, etc.).

## Testing suggestions

- Vitest with a fake `localStorage` (or jsdom's): read of a missing key →
  `undefined`; round-trip write→read returns the snapshot; corrupt JSON → `read`
  returns `undefined` and does not throw; `remove` clears it.
- Debounce: multiple `write`s to the same key within the window result in one
  underlying `setItem` with the last value; a flush (simulated `beforeunload`)
  persists pending writes.
- Run `just test-unit-frontend`.

## Gotchas

- `read` MUST be synchronous and total (never throw) — it is the source for the
  pre-paint restore in Task 6.2.
- Debounced writes can be lost on quit without the `beforeunload` flush — wire it.
- Keep the snapshot **consolidated**: one object per scope, not many keys (the
  prototype scattered keys; do not replicate).
- `GlobalLayoutState.sectionSizes` are **percentages** of the content area, not
  pixels.

## Verification checklist

- [ ] The three snapshot/scope types match `persistence_interface.md` exactly.
- [ ] `LayoutPersistenceAdapter` has `read`/`write`/`remove`/`prefetch?`.
- [ ] `LocalStorageLayoutAdapter`: synchronous tolerant `read`, debounced `write`,
  `beforeunload` flush, `remove`; exports the singleton.
- [ ] No legacy keys are read or written.
- [ ] Unit tests cover round-trip, corrupt-JSON tolerance, debounce coalescing,
  and flush; pass via `just test-unit-frontend`.
