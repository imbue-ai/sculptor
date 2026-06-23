# Task 1.6: Panel registry — static defs + dynamic agent/terminal + identity cache

## Goal

Build the panel registry: the `PanelDefinition` shape, the static single-instance
panel definitions, the dynamic agent/terminal panel derivation for the active
workspace, and — critically — the **component-identity cache** that keeps a live
panel from remounting when the registry rebuilds. Also wire the layout↔registry
join atom `activePanelComponentInSubSectionAtom`.

## Stories addressed

PANEL-01/05/15 (the panel set; single-instance default; multi-instance agent/
terminal), AGENT-02 (zero/one/many agents), SWITCH-02 (≤1 mount per panel per
switch — the identity cache is the mechanism).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the
workspace shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**The registry is the join point** (`state_design.md` → "Panel registry";
`component_hierarchy.md` → "The panel registry and dynamic panels";
`supplemental/panel_registry.md`) between layout state (which references panels by
id) and content (which renders them). Two layers:
- **Static panels** (single-instance): `files` (default left), `changes` (left),
  `commits` (left), `review-all` (no default section), `actions` (right), `skills`
  (right), `browser` (no default section), `notes` (right).
- **Dynamic panels** (multi-instance, for the *active* workspace only):
  `agent:<taskId>` (default `center`, wraps chat, close = delete confirmation) and
  `terminal:<wsId>:<index>` (default `bottom`, wraps xterm, close = confirmation).
  Derived from the task/terminal data atoms and merged into the registry at
  runtime.

**No enable/disable** (`panel_registry.md`; `naming_map.md` → "Deleted"): there is
**no** `enabled`/`defaultEnabled`/`isBuiltin` flag — the Panels settings page is
gone.

**Component identity must be cached by id** (`panel_registry.md` → "Dynamic
panels"; `component_hierarchy.md` memo table → `SectionBody`): rebuilding the
registry on every task tick must **never** remount a live agent/terminal panel.
The bound component per panel id is cached so `SectionBody` (Task 2.4) sees a stable
component reference.

This task depends on **Task 1.1** (`sectionTypes.ts`) and **Task 1.3**
(`activePanelIdInSubSectionAtom`, `workspaceLayoutAtom`,
`activeWorkspaceIdAtom`). The **actual panel components** (AgentPanel,
TerminalPanel, FilesPanel, …) are built in Phases 2–3; here the registry references
them through a **registration indirection** so this task does not forward-depend on
components that don't exist yet.

## Files to modify/create

- `sculptor/frontend/src/components/sections/registry/panelRegistry.ts` — new.
  `PanelDefinition`, `PanelKind`, the static metadata, the component-registration
  map, and the `panelRegistryAtom`.
- `sculptor/frontend/src/components/sections/registry/dynamicPanels.tsx` — new.
  Agent/terminal derivation + the per-id component cache.
- `sculptor/frontend/src/components/sections/registry/panelRegistry.test.ts` — new.
  Vitest.

## Implementation details

1. **`PanelDefinition`** (panel_registry.md → "Panel definition"):
   `{ id: PanelId; displayName: string; icon: LucideIcon; kind: "static" |
   "agent" | "terminal"; defaultSection?: SubSectionId; component: ComponentType;
   tabIcon?: ReactNode; contextMenuActions?: ContextMenuItem[] }`. Note
   `defaultSection` is **optional** (review-all and browser have none). **No
   `enabled` field.**
2. **Component registration indirection:** export
   `registerPanelComponent(id: PanelId, component: ComponentType): void` and an
   internal `Map<PanelId, ComponentType>`. The static panel modules (Phase 3) and
   the agent/terminal wrappers (Phase 2/3) call this at import time. The registry
   composes static metadata + the registered component. (This avoids Phase 1
   importing components that don't exist; a panel with no registered component yet
   renders nothing / a placeholder.)
3. **Static metadata:** an array of the eight static panels with id/displayName/
   icon/kind:"static"/defaultSection per the table above (review-all & browser:
   `defaultSection` undefined). Pick lucide icons consistent with today's usage.
4. **Dynamic derivation** (`dynamicPanels.tsx`): given the active workspace's task
   list and terminal list (from the existing task/terminal data atoms — find them
   under `src/pages/workspace` / `src/common` state; name them in a comment), build
   `agent:<taskId>` and `terminal:<wsId>:<index>` definitions. **Cache the bound
   component per id** in a `Map<PanelId, ComponentType>`: the first time an
   `agent:<taskId>` is seen, create and store the component that renders the agent
   panel for that task id; on subsequent rebuilds return the cached reference.
   Evict entries whose task/terminal no longer exists.
5. **`panelRegistryAtom`** — derived: static defs (with registered components) +
   dynamic defs for the active workspace. (Or a primitive atom kept in sync by a
   hook in Task 6.2 — choose derived for purity; if data atoms aren't easily read
   synchronously, expose a `useSyncPanelRegistry` hook instead and document it.)
6. **`activePanelComponentInSubSectionAtom(ss): Atom<ComponentType | undefined>`** —
   the join slice referenced by `state_atoms.md` and `component_tree.md`: reads
   `activePanelIdInSubSectionAtom(ss)` (Task 1.3) and resolves the component from
   the registry, returning a **stable** reference per panel id. Memoize per `ss`.
   This is the atom `SectionBody` subscribes to.

## Testing suggestions

- Vitest: the static registry contains the eight panels with the correct
  `defaultSection` (review-all/browser undefined); single-instance flag is correct
  (only agent/terminal are multi-instance); dynamic derivation yields
  `agent:<taskId>`/`terminal:<wsId>:<n>` ids; **the cached component reference for a
  given id is identical across two registry rebuilds** (the key SWITCH-02
  guarantee); a removed task evicts its entry.
- Run `just test-unit-frontend`.

## Gotchas

- The identity cache is the whole point — if you build the component inline each
  rebuild (`() => <AgentPanel .../>`), `SectionBody` remounts the chat on every
  task tick. Cache by id and return the same reference.
- **No `enabled`/`isBuiltin`** anywhere.
- Dynamic panels are derived for the **active** workspace only (their ids embed the
  task/terminal identity, so they can't be static config).
- review-all and browser are **not** open by default and have **no** default
  section; agents are **not** offered in any "re-add" list (closing ends them).

## Verification checklist

- [ ] `PanelDefinition` has no `enabled`/`defaultEnabled`/`isBuiltin`.
- [ ] Eight static panels with correct defaults; agent/terminal dynamic derivation.
- [ ] Component identity cached per id; stable across registry rebuilds (tested).
- [ ] `activePanelComponentInSubSectionAtom(ss)` resolves a stable component per
  panel id.
- [ ] Unit tests pass via `just test-unit-frontend`.
