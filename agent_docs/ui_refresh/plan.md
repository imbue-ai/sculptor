# Workspace UI refresh — execution plan

This document is the high-level execution plan for the workspace UI redesign. It
explains *how* we get from today's docking-layout workspace to the section/panel
model described in `goals.md` — the strategy, the order of work, what we copy
from the throwaway prototypes, and how we keep the app shippable throughout.

It is written in prose and stays at the altitude of approach and rationale. The
**detailed, build-ready task breakdown** lives in `plan/` (start at
`plan/00_overview.md`). The **decisions this plan made on your behalf** — the
things to confirm before or early in the build — are collected in
`plan/DECISIONS_NEEDED.md`.

`goals.md` is the source of truth for behavior; `user_stories.md` enumerates the
acceptance stories; `state_design.md`, `component_hierarchy.md`, and the
`supplemental/` docs are the architecture; `design_extraction.md` is the styling
map; `e2e_test_plan.md` and `harness_migration.md` are the test plan. This
document ties them into an executable sequence.

## What we are building

The workspace page becomes a **workspace sidebar** (a collapsible vertical nav
rail replacing the top bar) plus a **workspace header** and a **four-section
grid** (left, center, right, bottom). Every region is the same uniform
`PanelSection`, and every piece of content — chat, terminal, files, changes,
commits, review-all, and the rest — becomes a **panel** placed in a section.
Sections can be collapsed, expanded, resized, maximized, and split into two
sub-sections; panels can be opened, closed, dragged between sections, reordered,
and (for agents and terminals) renamed. Workspace creation moves from the
`/ws/new` page into a dialog, and a no-workspaces install gets a dedicated
first-run page. State is consolidated and persisted in local storage behind a
swappable adapter, and workspace switching is engineered to be visually seamless.

## Guiding strategy

**1. Rewrite the shell, reuse the content.** This is the central decision. The
*shell* — the sidebar, the section grid, the splittable sections, the panel
headers/tabs, the drag-and-drop, the layout state, the persistence, the registry,
the workspace header, the new-workspace modal, the first-run page — is genuinely
new code. The *content* — the chat surface (`chat-alpha`/`AlphaChatInterface`),
the xterm terminal container, the diff viewer, the file tree, the commit history,
review-all, the settings pages, the command palette — is **reused in place** and
wrapped in thin panel components. `goals.md` is explicit that existing
functionality is preserved and that this is a layout/behavior change, not a
rewrite of agent/terminal/diff internals. This "strangler" approach (new shell
grows around reused content; old shell is deleted once unreferenced) is what makes
the work shippable in increments and keeps ~120 content-only integration tests
valid. The alternative the architecture notes float — literally moving the
current tree to `frontend_old` and recreating `src` from scratch — is heavier,
harder to slice, and would discard the very content we are told to preserve. We do
**not** take that path. (See `plan/DECISIONS_NEEDED.md` if you want to revisit
this.)

**2. Copy styling and shape from the prototypes; rebuild behavior from
`goals.md`.** The `scu-1474` and `scu-1494` branches already implement most of the
visual design. We lift each component's `.module.scss` and structural JSX per
`design_extraction.md`, but we re-derive behavior from `goals.md`, rename
everything to `goals.md` vocabulary (`supplemental/naming_map.md`), and drop the
prototypes' dead code, brittle timing logic, and one-off hacks. The prototypes'
own notes are not trusted.

**3. Foundation before surfaces.** The state model, persistence adapter, and panel
registry are pure, unit-testable modules that everything else consumes. They come
first so the components built on top read from a stable contract. The required
**memoization boundaries** in `component_hierarchy.md` are treated as a hard
design constraint from the first component, not a later optimization.

**4. Delete deprecated features as dead code falls out — not before.** Because the
new shell grows alongside the old one, most removals (docking layout, top bar,
tabs, zones, Zen/Focus, `/btw`, the Panels settings page, `/ws/new`,
closed-workspaces) happen *after* the new shell is the live workspace experience,
in a dedicated cleanup phase. A few self-contained removals with no replacement
dependency (the experimental "share panel sizes" setting, the tab-strip-position
setting, the per-diff expand toggle) can go earlier. The end state has **no dead
code and no stale files**, per the rewrite mandate.

**5. Client-only persistence, but swappable.** All layout state is consolidated
into one snapshot per workspace and one global snapshot, read and written through
a single `LayoutPersistenceAdapter`. Today's implementation is localStorage; the
interface is shaped so a backend adapter can be dropped in later with no atom or
component changes. No backend persistence is introduced now.

**6. Mobile is out of scope, but its constraint is honored.** Building the mobile
shell is explicitly future follow-up (`user_stories.md` → Out of scope). We do
not build `MobileWorkspaceShell` here. We *do* preserve the architectural rule
that makes it possible later: **content components never read layout/section
state** — they take data from data atoms and identity from the registry. We keep
the page-level `useIsMobile` branch point as a thin seam (see
`plan/DECISIONS_NEEDED.md`).

## Order of work (phase narrative)

The plan is organized into thin vertical slices so each phase leaves the app in a
working, testable state. Full task-by-task detail is in `plan/00_overview.md`.

**Phase 1 — State, persistence, and registry foundation.** Build the core types
(`SectionId`, `SubSectionId`, `PanelId`, `SectionSplit`), the persistence adapter
and consolidated snapshot shapes, the Jotai layout atoms (per-workspace family +
proxy, global, scope/switch) with their narrow read slices, the write-side action
atoms that enforce the invariants (center never collapses, active section must be
expanded, split self-heal, single-instance), the transient atoms (maximized, drag
preview, ring), and the panel registry (static defs + dynamic agent/terminal
derivation with component-identity caching). No UI yet; everything is exercised
with unit tests.

**Phase 2 — Desktop shell, the agent panel, and cutover.** Copy the shared design
foundation (tokens, scrollbar mixin, Radix overrides), then build the
`WorkspaceSidebar` (with the net-new resize handle, version row, and report-a-bug
entry), the `SectionGrid` + `ResizeHandle` geometry, and the uniform
`SplittableSection` / `PanelSection` / `SectionHeader` / `SectionBody` with their
memoization boundaries. Wrap the existing chat surface as the `AgentPanel` (giving
`ChatPanelContent` an explicit `taskId` prop so it no longer reads the route), then
**cut the workspace route over** to the new `WorkspaceLayoutShell` +
`WorkspaceHeader` with a minimal default layout (center agent visible; other
sections present but empty for now). This phase also rewrites the harness spine
(`project_layout.py`, `task_page.py`) to drive the new surfaces while keeping
method signatures stable — a compatibility shim so the large body of
content-only tests survives the cutover — and adds the first sidebar/section
ElementIDs and POMs.

**Phase 3 — The rest of the panels.** Wrap the terminal as `TerminalPanel`; build
the shared `ExplorerLayout` + embeddable `DiffViewer` (with the configuration
icons relocated into the triple-dot menu) and the three independent
Files/Changes/Commits panels on top of it; build the remaining registered panels
(Review-all, Actions, Skills, Browser, Notes) with no enable/disable machinery;
and build the add-panel dropdown and the section empty-state launcher. The area's
POMs and CREATE/migrate tests land with the features.

**Phase 4 — Interactions.** The single app-level `PanelDndProvider` (with a
`KeyboardSensor` + drag handle added for both accessibility and Playwright
drivability), split creation/closing with the per-section direction rules and
self-heal, maximize/restore and its presentation (header hidden, OS
window-control padding), the active-section selection and the rebuilt ~2s ring
fade, and the keyboard shortcuts (collapse/expand, cycle sections, cycle panels,
maximize, sidebar toggle, new agent/terminal, panel focus) wired through the
keybindings settings page.

**Phase 5 — Workspace creation and first-run.** Copy the `scu-1494` modal and
form (title, auto-growing prompt, breadcrumb context pills, branch-name pill,
footer), wire the four entry points (sidebar direct-create reusing last settings,
`Cmd/Meta+T`, `Cmd+K`, repo-section `+`) and the creation modes/source-branch/MRU
behavior, and build the empty first-run page with its disabled-navigation state.

**Phase 6 — Persistence wiring and seamless switching.** Connect the adapter to
the atoms (hydrate, debounced flush, scope removal), seed the full default layout
on first visit (center agent, left Files/Changes/Commits, bottom terminal, right
empty), and implement the pre-paint switch sequence so the first committed frame
of a switch already shows the full layout at persisted sizes with no spinner.

**Phase 7 — Remove deprecated features and dead code.** Delete the docking layout,
top bar, tab strip, panel zones, and side-toggle bar; Zen/Focus, `/btw`, the
Panels settings page and its enable/disable machinery, the share-sizes and
tab-strip-position settings, and the per-diff expand toggle; the `/ws/new` route,
the closed-workspaces pill/dropdown, and the Component Gallery. Their ElementIDs
and dedicated tests go with them. (The **TanStack devtools panel is kept** — only
the Component Gallery is removed.)

**Phase 8 — Legacy test-suite migration and the rename pass.** Execute the bulk
of `e2e_test_plan.md` that the feature phases did not already cover: the
route-to-feature UPDATE long tail, the sidebar/row and dialog REWRITEs, the
file-browser/diff/history MIGRATE-and-consolidate, and finally the mechanical
terminology rename (file names, test functions, `@user_story` strings, POM
methods) as its own commit.

**Phase 9 — Perf tooling and the non-functional bars.** Carry the workspace-switch
profiler forward and define the `measure-react-renders` scenarios that verify the
`[perf]` stories (zero layout-shift on switch, ≤1 mount per panel per switch,
memoized re-renders during drag/resize, global sizes in the first frame).

**Phase 99 — Finalize.** Run every test the plan added and iterate to green, then
launch the review agent.

## Delivery

This ships as **one pull request** off `bryden/tungsten-seriema`, not a stack of
per-phase PRs. The work is split into **semantic commits** — the build commits once
per task (per `implement_task.md`), so each commit is a coherent, independently
reviewable unit, and a per-commit review tool can walk them like a stack of small
PRs while everything lands in a single PR. Keep commits atomic (one logical change
each) and ordered by the phase sequence above; the mechanical terminology rename
(Phase 8) is deliberately its own commit so it reviews as "rename only."

## What we copy from the prototypes

`design_extraction.md` is the authoritative map; at a high level we copy, **as
styling/shape only**, and rename to `goals.md` vocabulary:

- **Shared foundation first:** `styles/tokens.css`, `styles/_scrollbar.scss`,
  `styles/radix-overrides.css`, and the relevant `index.css` additions. Everything
  else depends on these tokens.
- **Sidebar:** `WorkspaceNavSidebar` and `CollapsedSidebarToggle` — then add the
  net-new resizable handle + minimum width, and relocate the existing
  `VersionDisplay` and `ReportProblemPopover` (both on `main`) into the sidebar
  bottom.
- **Sections/tabs/splits/empty-state/DnD:** `PanelSection`, `SectionTabBar`,
  `SplittableSection`, `ResizeHandle`, `EmptyPanelLauncher`, `PanelDndProvider`,
  `CompactLayout` — copying the visual treatment (including the active-section ring
  CSS) but rebuilding the brittle ring timing.
- **Workspace header:** `WorkspaceBanner` — re-homing the PR button and diff
  summary.
- **Panels & viewer:** `MasterDetailPanel`/`MasterDetailTreeHeader` (→ `ExplorerLayout`/`ExplorerTreeHeader`), the
  `fileBrowser` tree, the `diffPanel` set (assembling the triple-dot menu from
  `DiffViewMenuItems` + tree options), and the `historyPanel` commit graph; the
  `AgentPanel`/`TerminalPanel` wrappers around the existing chat/xterm surfaces;
  the add-panel **row styling** from `AddPanelPalette` rendered as a **dropdown**
  (not the cmdk overlay).
- **New workspace modal & first-run (`scu-1494`):** `NewWorkspaceModal`,
  `NewWorkspaceForm`, `BranchNameField`, the inline first-run form, and the
  `/sculptor:help` prompt prefill.

And we explicitly **do not** copy: the cmdk add-panel overlay as the add surface,
the focus-ring timing logic, the hardcoded font sizes / Radix `!important` hacks /
Chromium-only `field-sizing`, and inlined title-bar padding constants.

## Testing approach

`goals.md` requires end-to-end coverage for user-facing behavior, and the suite
is large (~207 integration files). The approach:

- **A compatibility shim, not a big-bang break.** The harness spine
  (`project_layout.py`, `task_page.py`) is rewritten in Phase 2 to drive the new
  sidebar/section surfaces while keeping method signatures stable, and the
  load-bearing `create_workspace()` helper (≈177 importers) keeps its exact
  signature with rewritten internals. This keeps the content-only majority green
  through cutover.
- **Tests land with their feature.** Each feature phase adds its `data-testid`
  ElementIDs (then `just generate-api`), its area POMs, and the net-new CREATE
  tests that prove the feature.
- **The legacy suite migrates by area** (Phase 8) per `e2e_test_plan.md`:
  UPDATE harness-path, REWRITE replaced surfaces, MIGRATE-and-consolidate the
  file-browser/diff/history tests into the new panel files, DELETE removed
  features, and a final mechanical RENAME pass as its own commit.
- **Drag-and-drop is made driveable** by adding a `KeyboardSensor` + drag handle
  to the DnD provider — Playwright drives the real sensor pipeline rather than
  synthesizing pointer drags.
- **Non-functional bars use tooling, not Playwright.** The `[perf]` stories are
  verified with the workspace-switch profiler and the `measure-react-renders`
  skill, tracked as a perf checklist.

Per `.sculptor/testing.md`, integration tests run via the `/run-integration-test`
skill (never `pytest` directly), and any new `ElementIDs` require
`just generate-api`. Purely visual states are verified with screenshots, not
layout-asserting tests.

## Key risks and how the sequence addresses them

- **Cutover breaks the world.** Mitigated by the strangler approach + the harness
  shim: the new shell becomes the route in Phase 2 with the agent panel already
  working, and signature-stable POMs keep most tests passing. The window where the
  legacy suite is partially red is bounded and burned down area-by-area.
- **Re-render cascades during drag/resize/switch.** Mitigated by treating the
  memoization boundaries in `component_hierarchy.md` as a first-class requirement
  from Phase 2, and verifying with the render-count tooling in Phase 9.
- **Seamless switching regressions.** Mitigated by building the pre-paint,
  single-read switch sequence deliberately in Phase 6 and validating with the
  switch profiler (zero layout-shift, ≤1 mount per panel).
- **Live panels remounting on every task tick.** Mitigated by the component
  identity cache in the registry (Phase 1) and the `SectionBody` subscription to
  the *resolved component* (Phase 2).
- **Scope creep from the prototypes.** Mitigated by treating them as styling-only
  and renaming to `goals.md` vocabulary; the "do not copy" list is explicit.

## Where to go next

- **Build-ready detail:** `plan/00_overview.md` (the task index) and the numbered
  task files beside it. Each task file is self-contained. (The `plan/` folder is
  gitignored per repo convention — it lives locally and is consumed by
  `/sculptor-workflow:build`; `plan/DECISIONS_NEEDED.md` → C6 explains how to track
  it if you want it committed.)
- **Decisions to confirm:** `plan/DECISIONS_NEEDED.md`.
