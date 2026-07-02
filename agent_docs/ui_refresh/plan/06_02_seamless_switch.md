# Task 6.2: Pre-paint switch sequence + dynamic-panel placement

## Goal

Implement the workspace-switch sequence so the **first committed frame** of a switch
already shows the full layout at persisted sizes — no spinner, no layout shift, no
duplicate mounts — by running the scope flip, registry swap, and dynamic-panel
placement in a single pre-paint (layout-effect) flush.

## Stories addressed

SWITCH-01 (`[perf]` zero layout-shift; sidebar/header/section headers/frames present
in the first frame), SWITCH-02 (`[perf]` ≤1 mount per panel per switch), SWITCH-03
(no spinner — prefetch or stale-then-update), SWITCH-04 (re-entry preserves what the
user was looking at), PERSIST-04 (Home→back round-trip stability — built on SWITCH-04's
re-entry preservation; regression-tested in Task 6.3), SEC-18/PERSIST-02 (`[perf]`
global sizes in the first frame).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**The switch sequence** (`supplemental/persistence_interface.md` → "Switch sequence";
`state_design.md` → "Scoping: one atomic workspace switch"; `component_hierarchy.md`):
on navigating to workspace `W`, all of the following run in the **same pre-paint
(layout-effect) flush**:
1. `switchActiveWorkspaceAtom({workspaceId: W, defaultLayout})` writes
   `activeWorkspaceIdAtom = W` — every per-workspace proxy now resolves to `W`'s
   snapshot (seeded on first visit, Task 6.1).
2. The panel registry is set to `W`'s static + dynamic (agent/terminal) panels.
3. The active agent is placed into center (or activated if already open); on first
   visit the terminal is seeded into the (collapsed) bottom section.

Because these are **layout effects** (not passive effects), they commit before paint —
no frame shows the previous workspace's layout under `W`'s URL, and no second-pass
reflow. The synchronous `adapter.read` (Task 1.2) makes the first render already have
the persisted layout.

**The hooks** (`supplemental/component_tree.md` → "Hooks wiring"):
- `usePerWorkspacePanelLayout(workspaceId)` — layout effect; writes
  `switchActiveWorkspaceAtom` so the active scope follows the route in one pre-paint
  commit.
- `useWorkspaceLayoutBootstrap({workspaceId, agentId})` — layout effect; places the
  active agent into center and seeds the bottom terminal on first visit.
- `useWorkspaceDynamicPanels(workspaceId)` — derives agent/terminal panel defs and
  feeds the registry (Task 1.6).

**No spinner** (`goals.md` → "Workspace switching should look seamless"; SWITCH-03):
content is prefetched, or last-known/stale content (or an in-place skeleton) is shown
and updated when it resolves — never a spinner. The `DiffSkeleton` (static, no
shimmer) is the skeleton treatment.

This task depends on **Tasks 1.3 (scope/switch), 1.6 (registry + identity cache), 2.4
(SectionBody resolved-component boundary), 2.6 (shell), 6.1 (default seeding)**.

## Files to modify/create

- `sculptor/frontend/src/common/state/hooks/usePerWorkspacePanelLayout.ts` — new.
- `sculptor/frontend/src/pages/workspace/hooks/useWorkspaceLayoutBootstrap.ts` — new.
- `sculptor/frontend/src/components/sections/registry/useWorkspaceDynamicPanels.ts`
  (or `.tsx`) — new (feeds `panelRegistryAtom` from Task 1.6).
- `sculptor/frontend/src/pages/workspace/WorkspacePage.tsx` /
  `WorkspaceLayoutShell.tsx` — mount the three hooks in the right order.
- Prefetch wiring: call `adapter.prefetch` (no-op for localStorage) on navigation
  intent/hover (a seam for the future backend adapter).

## Implementation details

1. Mount the three hooks as **layout effects** so the scope flip + registry swap +
   agent placement all commit in one pre-paint flush. Order: scope first
   (`usePerWorkspacePanelLayout`), then registry (`useWorkspaceDynamicPanels`), then
   bootstrap placement (`useWorkspaceLayoutBootstrap`).
2. `usePerWorkspacePanelLayout(workspaceId)`: on route change, write
   `switchActiveWorkspaceAtom({workspaceId, defaultLayout})` (Task 6.1 seeds default
   on first visit).
3. `useWorkspaceDynamicPanels(workspaceId)`: derive agent/terminal defs (Task 1.6)
   and set the registry; the identity cache keeps live panels from remounting
   (SWITCH-02).
4. `useWorkspaceLayoutBootstrap`: on first visit, place the active agent into center
   and seed a terminal into the collapsed bottom section; on revisit, activate the
   active agent if present. Pulse the active-section ring on entry (`jumpToSectionAtom`,
   Task 4.4) per SEC-11.
5. SWITCH-04: re-entry restores the persisted `activeSubSection` + active panels (from
   the snapshot) — "preserve what the user was looking at."
6. SWITCH-03: never show a spinner — render the section frames at their (global) sizes
   + skeleton/stale content, swap in real content when ready.
7. Add the `adapter.prefetch` seam on navigation intent/hover (no-op today).

## Testing suggestions

- SWITCH-03/04 e2e land in **Task 6.3** (`test_seamless_switch.py`): no spinner
  (skeleton/stale-then-update); last-view preserved. The `[perf]` bars (SWITCH-01/02/05,
  SEC-18, PERSIST-02) are **not** Playwright tests — they are verified in **Task 9.1**
  via the workspace-switch profiler + `measure-react-renders`.

## Gotchas

- The three steps must run in **layout effects** (pre-paint), not passive effects, or
  you get a frame of the old layout / a reflow (SWITCH-01).
- The registry rebuild must reuse cached component identities (Task 1.6) or panels
  remount (SWITCH-02) and streaming agents drop state.
- Never show a spinner (SWITCH-03) — frames-at-sizes + skeleton/stale.
- Keep the `prefetch` seam even though localStorage's is a no-op — it's the backend
  swap point.

## Verification checklist

- [ ] `usePerWorkspacePanelLayout` / `useWorkspaceLayoutBootstrap` /
  `useWorkspaceDynamicPanels` mounted as ordered layout effects.
- [ ] Switch flips scope + registry + placement in one pre-paint flush; ring pulses on
  entry; re-entry restores the last view.
- [ ] No spinner; section frames render at persisted sizes immediately.
- [ ] `prefetch` seam present (no-op for localStorage).
- [ ] `just check` passes; SWITCH-03/04 e2e in Task 6.3; `[perf]` bars in Task 9.1.
