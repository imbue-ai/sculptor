# Task 2.6: WorkspaceLayoutShell + WorkspaceHeader + cut the workspace route over

## Goal

Assemble the new shell — `WorkspaceLayoutShell` (workspace header + section grid)
and `WorkspaceHeader` — and **cut the workspace route over** from the old docking
layout to the new shell, with the sidebar as global chrome and a minimal working
default layout (center agent visible). After this task the app *is* the new shell.

## Stories addressed

SEC-01 (center is the expanded section with an agent), SIDE-13 (sidebar visible as
global chrome), AGENT-01 (chat renders in center). Lays the route foundation for
all later phases.

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md` using the
**strangler** strategy (`agent_docs/ui_refresh/plan.md`): the new shell becomes the
live route now; the old docking shell is deleted later (Phase 7) once unreferenced.

**The shell tree** (`component_hierarchy.md` → "The workspace layout shell";
`supplemental/component_tree.md`):
```
AppShell
├─ WorkspaceSidebar                (global chrome, Task 2.2)
└─ WorkspacePage  (useIsMobile branch)
   └─ WorkspaceLayoutShell
      └─ PanelDndProvider          (full impl Task 4.1; a pass-through stub here)
         ├─ WorkspaceHeader        (hidden when a section is maximized — Task 4.3)
         └─ SectionGrid            (Task 2.3 → SplittableSection/PanelSection, Task 2.4)
```

**What to copy** (`design_extraction.md` → "Layout shell & workspace header"):
- `pages/workspace/components/WorkspaceBanner.tsx` + `.module.scss` →
  `pages/workspace/WorkspaceHeader.tsx` — the simplified header (branch pill,
  section toggles, drag spacer). **Re-home the PR button + diff summary** onto the
  header per `goals.md`.

**Current route/shell to replace:** today the workspace renders through
`src/layouts/PageLayout.tsx` (top bar / docking host) and
`src/pages/workspace/WorkspacePage.tsx`. Re-point `WorkspacePage` to render
`WorkspaceLayoutShell`, and render `WorkspaceSidebar` as global chrome (check
`src/App.tsx`/`src/Router.tsx` for where the page shell mounts). **Leave the old
`PageLayout`/docking files in place for now** (they are deleted in Phase 7 once
nothing imports them) — but the workspace route must no longer use them.

**Mobile seam** (`user_stories.md` → out of scope; `plan.md` → strategy): keep a
`useIsMobile()` branch in `WorkspacePage` as a **no-op seam** (always renders the
desktop `WorkspaceLayoutShell` for now). Do not build `MobileWorkspaceShell`.

This task depends on **Tasks 2.2 (sidebar), 2.3 (SectionGrid), 2.4
(SplittableSection/PanelSection), 2.5 (AgentPanel)**, and the foundation atoms.
Full default-layout seeding (left Files/Changes/Commits, bottom terminal) is **Task
6.1**; here seed a **minimal** default (center holds the active agent; left/right/
bottom present but collapsed/empty) so the app is usable.

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/WorkspaceLayoutShell.tsx` (+ `.module.scss`)
  — new.
- `sculptor/frontend/src/pages/workspace/WorkspaceHeader.tsx` + `.module.scss` — new
  (from `WorkspaceBanner`).
- `sculptor/frontend/src/pages/workspace/WorkspacePage.tsx` — modify: render
  `WorkspaceLayoutShell` (behind the `useIsMobile` no-op seam) instead of the
  docking layout.
- `sculptor/frontend/src/common/hooks/useLayoutMode.ts` — new. `useIsMobile()` /
  `useLayoutMode()` (always desktop for now).
- `sculptor/frontend/src/App.tsx` / `Router.tsx` — modify: mount `WorkspaceSidebar`
  as global chrome for the relevant routes.
- `sculptor/frontend/src/components/sections/PanelDndProvider.tsx` — new **stub**
  (renders children; full dnd in Task 4.1).

## Implementation details

1. Build `WorkspaceLayoutShell`: wrap `WorkspaceHeader` + `SectionGrid` in the
   `PanelDndProvider` stub. Hide `WorkspaceHeader` when `maximizedSectionAtom` is
   set (the maximized presentation detail is finished in Task 4.3; here just gate the
   render).
2. Build `WorkspaceHeader` from `WorkspaceBanner`: branch pill, section
   collapse/expand toggles, drag spacer; **move the PR button + diff-summary
   getters** here (they currently live near the banner/task page — grep and re-home).
3. Re-point `WorkspacePage` to `WorkspaceLayoutShell` via the `useIsMobile` seam.
   Mount `WorkspaceSidebar` globally (it renders for every route per
   `component_hierarchy.md`).
4. Seed a **minimal** default layout so cutover yields a working app: ensure the
   active workspace's active agent panel is placed in `center` and center is
   expanded; other sections may be empty/collapsed. (The full SEC-01..04 default —
   left Files/Changes/Commits active=Files, bottom terminal, right empty — is Task
   6.1.)
5. Keep the old docking files on disk but **unreferenced** by the workspace route.
6. Verify the app launches and a workspace shows the sidebar + a center agent panel.
   Use `/auto-qa-changes` or `just frontend` for a manual look.

## Testing suggestions

- The smoke e2e for cutover (sidebar renders; center shows the agent; navigate to a
  workspace via a sidebar row) lands in **Task 2.7** alongside the harness spine.
- Many legacy tests will start exercising the new shell after this cutover — the
  harness shim in Task 2.7 keeps the content-only majority green; the rest migrate in
  Phase 8.

## Gotchas

- This is the **risky cutover**. Expect a window where some legacy tests assert
  removed surfaces (top bar/tabs) — that is handled by Task 2.7 (shim) + Phase 8
  (migration), not by reverting.
- Do not delete the old docking/`PageLayout` files yet (Phase 7) — just stop routing
  through them.
- Keep `useIsMobile` a real seam but a no-op (desktop only) — do not build the mobile
  shell.
- The `PanelDndProvider` here is a stub; do not implement dnd (Task 4.1).
- Re-home the PR button + diff summary — don't drop them.

## Verification checklist

- [ ] `WorkspaceLayoutShell` renders `WorkspaceHeader` + `SectionGrid` inside the
  `PanelDndProvider` stub; header hides when maximized.
- [ ] `WorkspaceHeader` has the branch pill, section toggles, and the re-homed PR
  button + diff summary.
- [ ] `WorkspacePage` renders the new shell via the `useIsMobile` no-op seam;
  `WorkspaceSidebar` is global chrome.
- [ ] App launches; a workspace shows sidebar + center agent panel.
- [ ] Old docking files remain on disk but are unreferenced by the workspace route.
- [ ] `just check` passes.
