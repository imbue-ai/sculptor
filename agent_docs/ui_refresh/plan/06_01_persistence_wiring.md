# Task 6.1: Wire adapter ↔ atoms + seed the full default layout

## Goal

Connect the persistence adapter to the layout atoms end-to-end (hydrate, debounced
flush, scope removal) and implement the **full default-layout seeding** on a
workspace's first visit.

## Stories addressed

SEC-01 (center = one agent of the recent type), SEC-02 (left collapsed: Files/Changes/
Commits open, Files active), SEC-03 (bottom collapsed: one terminal), SEC-04 (right
collapsed + empty), PERSIST-01 (per-workspace arrangement stored + isolated),
PERSIST-02 (global layout stored + shared), PERSIST-03 (persists across restart),
PERSIST-05 (per-workspace isolation).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**The default layout** (`goals.md` → "Default layout"; SEC-01..04): on first open, the
center section is the only expanded section with one agent panel of the recent type
(Claude by default); the left section is collapsed with Files/Changes/Commits open and
Files active; the bottom section is collapsed with one terminal; the right section is
collapsed and empty (Actions/Skills/Notes default to right *when opened*, but nothing
is open at first run).

**Wiring** (`state_design.md` → "Persistence and the swap boundary";
`supplemental/persistence_interface.md`): the atoms already read their initial value
from `adapter.read` (Task 1.3) and persist on write (debounced in the adapter, Task
1.2). This task confirms the full loop — hydrate on first access, debounced flush,
flush on `beforeunload`, `remove` on workspace delete — and implements the
**default-layout seeding** inside `switchActiveWorkspaceAtom` (Task 1.3 left the
extension point): when a workspace's family entry is empty (first visit), seed the
default `WorkspaceLayoutState`.

**No migration** (`goals.md`; `persistence_interface.md`): read only the new
consolidated keys; old keys are ignored; stop writing them.

This task depends on **Tasks 1.2 (adapter), 1.3 (atoms + `switchActiveWorkspaceAtom`
extension point), 1.4 (`removeWorkspaceLayoutAtom`), 1.6 (registry)**, and the panels
(Phase 3) so the default placement references real panel ids.

## Files to modify/create

- `sculptor/frontend/src/components/sections/sectionAtoms.ts` — modify
  `switchActiveWorkspaceAtom`: seed the default `WorkspaceLayoutState` on first visit.
- `sculptor/frontend/src/components/sections/persistence/defaultLayout.ts` — new:
  build the default `WorkspaceLayoutState` (center = active agent; left = files/changes/
  commits, active files, collapsed; bottom = a terminal, collapsed; right = empty,
  collapsed) and the default `GlobalLayoutState` if not already in `persistence/types.ts`.
- Confirm `removeWorkspaceLayoutAtom` (Task 1.4) calls `adapter.remove` on workspace
  delete (wire it into the existing workspace-delete flow — grep the delete handler).

## Implementation details

1. **Default seeding:** `defaultLayout.ts` produces a `WorkspaceLayoutState` with
   `placement`/`order`/`activePanel`/`expanded` set so: center has the active
   `agent:<taskId>` and is expanded; left has `files`/`changes`/`commits` with `files`
   active and `expanded.left = false`; bottom has one `terminal:<wsId>:<n>` with
   `expanded.bottom = false`; right empty + `expanded.right = false`; no splits;
   `activeSubSection` = center. (The dynamic agent/terminal ids are resolved at seed
   time from the active task / a seeded terminal — see Task 6.2 for the placement of
   the active agent + the first-visit terminal seed.)
2. `switchActiveWorkspaceAtom`: when the family entry is empty for `workspaceId`, seed
   the default and write it; otherwise leave the restored snapshot untouched.
3. Confirm the **global** snapshot (sizes/sidebar/explorer list width) hydrates from
   `adapter.read({kind:"global"})` and persists on change (PERSIST-02).
4. Wire workspace delete → `removeWorkspaceLayoutAtom` → `adapter.remove`.
5. Confirm the debounced flush + `beforeunload` flush actually persist (PERSIST-03);
   nothing reads/writes legacy keys.

## Testing suggestions

- PERSIST/default e2e land in **Task 6.3** (`test_layout_persistence.py`,
  `test_layout_persistence_regression.py`) + the SEC-01..04 default assertions in
  `test_section_default_layout.py` (Task 6.3). Adapter-level unit tests (the
  per-workspace-vs-global split, the no-migration rule) are a cheaper surface than full
  e2e — exercise the adapter directly (Task 6.3).

## Gotchas

- Seed the default **only on first visit** (empty family entry) — never clobber a
  restored snapshot.
- The default's dynamic ids (agent/terminal) must resolve to the workspace's actual
  active agent + a seeded terminal (Task 6.2 handles placement/seed timing) — don't
  hardcode ids.
- Global sizes/sidebar/explorer list width are **global** — one snapshot shared across
  workspaces (PERSIST-02).
- No migration — ignore legacy keys; stop writing them.

## Verification checklist

- [ ] First visit seeds the SEC-01..04 default (center agent; left files/changes/
  commits active=files collapsed; bottom terminal collapsed; right empty collapsed).
- [ ] Per-workspace snapshots hydrate/persist + are isolated; global snapshot is shared
  (PERSIST-01/02/05).
- [ ] Workspace delete calls `adapter.remove`; restart persists the arrangement
  (PERSIST-03).
- [ ] No legacy keys read/written.
- [ ] `just check` passes (e2e in Task 6.3 / 4.6).
