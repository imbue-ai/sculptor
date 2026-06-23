# Task 1.3: Consolidated layout atoms, scope/switch, and narrow read slices

## Goal

Build the Jotai layout atoms: the consolidated per-workspace family + the active-
scope proxy, the global layout atom, the scope/switch atoms, and the **narrow read
slices** components subscribe to. This is the in-memory state the whole shell reads;
it is backed by the persistence adapter from Task 1.2.

## Stories addressed

PERSIST-01/02/05 (per-workspace isolation + global sizes), SWITCH-01..04
(single-write switch is the backbone of seamless switching), and the foundation
for every `SEC-*`/`PANEL-*` read.

## Background

**Project:** Sculptor frontend (TS + React + **Jotai**) under
`sculptor/frontend/src`. We are rewriting the workspace shell into the
section/panel model from `agent_docs/ui_refresh/goals.md`.

**Why Jotai, scoping, and narrow slices** (`state_design.md` → "State library" and
"Scoping: one atomic workspace switch"; `supplemental/state_atoms.md`):
- `atomFamily` keyed by workspace id gives per-workspace scoping; switching scope
  is a **single atom write**.
- Derived atoms (`selectAtom` with custom equality) give the **narrow
  subscriptions** that the memoization boundaries in `component_hierarchy.md`
  require: a component re-renders only when its exact slice changes.
- Synchronous reads make the pre-paint restore possible (the initial value comes
  straight from `adapter.read`).

**Consolidated, not scattered** (`state_design.md` → "Consolidated snapshots"):
the prototype's many per-concern families collapse into **one**
`workspaceLayoutFamily(workspaceId)` holding the whole `WorkspaceLayoutState`, plus
one `globalLayoutAtom` holding `GlobalLayoutState`. Narrow slices are *derived* from
these.

This task depends on **Task 1.1** (`sectionTypes.ts`) and **Task 1.2**
(`persistence/types.ts` shapes + `persistence/LocalStorageLayoutAdapter.ts`
exporting `layoutPersistenceAdapter`).

## Files to modify/create

- `sculptor/frontend/src/components/sections/sectionAtoms.ts` — new. Scope atoms,
  the per-workspace family + proxy, the global layout atom, and the per-workspace
  narrow read slices.
- `sculptor/frontend/src/components/layout/sidebarAtoms.ts` — new. `sidebarWidthAtom`
  and `sidebarCollapsedAtom` as writable slices of `globalLayoutAtom`.
- `sculptor/frontend/src/components/sections/sectionAtoms.test.ts` — new. Vitest.

## Implementation details

1. **Scope atoms** (`sectionAtoms.ts`), per `supplemental/state_atoms.md` → "Scope
   atoms":
   - `activeWorkspaceIdAtom: PrimitiveAtom<string | null>`.
   - `layoutScopeAtom: Atom<LayoutScope>` — derived: workspace scope when an id is
     set, else the global sentinel.
2. **Consolidated atoms:**
   - `workspaceLayoutFamily: atomFamily((workspaceId) => atom)` where each atom's
     **initial value** is `layoutPersistenceAdapter.read({kind:"workspace",
     workspaceId}) ?? EMPTY_WORKSPACE_LAYOUT`, and whose write **persists** via
     `layoutPersistenceAdapter.write(...)`. (Use a writable atom whose setter
     updates the in-memory value and calls `adapter.write` — the debounced
     coalescing lives in the adapter.)
   - `workspaceLayoutAtom: WritableAtom<WorkspaceLayoutState, [Updater], void>` —
     the **proxy** the app reads: on read/write it resolves
     `get(activeWorkspaceIdAtom)` and delegates to
     `workspaceLayoutFamily(activeId)`. When no workspace is active, back it with a
     global-sentinel entry so reads never crash.
   - `globalLayoutAtom: WritableAtom<GlobalLayoutState, ...>` — initial value from
     `adapter.read({kind:"global"}) ?? DEFAULT_GLOBAL_LAYOUT`; write persists.
3. **Narrow read slices** (`supplemental/state_atoms.md` → "Read-side narrow
   slices") — all derived from `workspaceLayoutAtom` via `selectAtom` with custom
   equality, and **per-key slices memoized in a module-load `Map`** so the same
   atom instance is reused per key:
   - `panelsInSubSectionAtom(ss): Atom<readonly PanelId[]>` (ordered open panels;
     shallow-array equality).
   - `activePanelIdInSubSectionAtom(ss): Atom<PanelId | undefined>`.
   - `isSectionExpandedAtom(s): Atom<boolean>` (center always true).
   - `sectionSplitForSectionAtom(s): Atom<SectionSplit | undefined>`.
   - `isSplitHalfAtom(ss): Atom<boolean>`.
   - `activeSubSectionAtom: Atom<SubSectionId | null>`.
   - `isActiveSubSectionAtom(ss): Atom<boolean>`.
   - Global slices: `sectionSizesAtom: Atom<{left;right;bottom}>`,
     `masterDetailListWidthAtom: WritableAtom<number,...>` (derived from
     `globalLayoutAtom`).
   - (`activePanelComponentInSubSectionAtom` joins layout + registry and is defined
     in **Task 1.6**, not here.)
4. **`switchActiveWorkspaceAtom`** (write-only) skeleton, per
   `supplemental/state_atoms.md` and `persistence_interface.md` → "Switch
   sequence": writes `activeWorkspaceIdAtom = workspaceId`. The **default-layout
   seeding** on first visit and the registry/dynamic-panel placement are wired in
   Task 6.1/6.2 — here, define the atom and write the id; leave a clearly marked
   extension point (a `defaultLayout` param accepted but only applied if the
   family entry is empty). Document the dependency in a comment (no change
   narration — present-tense: "first visit seeds the default layout; see Task 6.1").
5. **`sidebarAtoms.ts`:** `sidebarWidthAtom` / `sidebarCollapsedAtom` as
   `focusAtom`/`selectAtom`-style writable slices of `globalLayoutAtom`
   (`sidebarWidthPx` / `sidebarCollapsed`), so the sidebar (global chrome) reads/
   writes one global snapshot.

## Testing suggestions

- Vitest with a Jotai store (`createStore`) and the localStorage adapter (or a
  test adapter): writing `activeWorkspaceIdAtom` flips every per-workspace slice to
  the new workspace's snapshot in one read; slices return reference-stable values
  when the underlying field is unchanged (custom equality verified by subscribing
  and counting notifications); two workspace ids keep independent placement
  (PERSIST-05).
- `sectionSizesAtom` reflects `globalLayoutAtom` and is shared regardless of active
  workspace (PERSIST-02).
- Run `just test-unit-frontend`.

## Gotchas

- **Memoize per-key slice atoms in a `Map` created at module load.** Creating a new
  derived atom inside a component render (or per call without caching) causes Jotai
  re-render loops — the prototype's `atoms.ts` documents this. Each
  `xAtom(key)` call must return the same atom instance for the same key.
- Use **custom equality** on array/object slices (shallow array equality for panel
  lists) so unrelated mutations to the consolidated snapshot do not notify a slice.
- The proxy must resolve the active scope on **each** read/write (do not capture a
  workspace id at module load).
- Do not persist transient state here (maximize/drag/ring live in Task 1.5).

## Verification checklist

- [ ] `workspaceLayoutFamily` + `workspaceLayoutAtom` proxy + `globalLayoutAtom`,
  all backed by the Task 1.2 adapter.
- [ ] All narrow slices from `state_atoms.md` present and memoized per key in a Map.
- [ ] Switching `activeWorkspaceIdAtom` atomically flips per-workspace slices; two
  workspaces stay isolated; global slices are shared.
- [ ] `sidebarAtoms.ts` exposes width/collapsed as writable global slices.
- [ ] Unit tests pass via `just test-unit-frontend`.
