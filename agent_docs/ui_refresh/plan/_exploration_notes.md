# Exploration notes — workspace UI refresh

Distilled, durable reference for the build. The design docs are the spec +
architecture substitute; this file pins them to the *actual* codebase so task
files can cite concrete paths. Re-read this instead of re-reading source when
context runs low.

## Document map (the spec/architecture substitute)

There is no `spec.md`/`architecture.md`; the `agent_docs/ui_refresh/` set plays
those roles:

- **Behavior (spec):** `goals.md` (authoritative), `user_stories.md` (story IDs).
- **Architecture:** `state_design.md`, `component_hierarchy.md`,
  `supplemental/state_atoms.md`, `supplemental/persistence_interface.md`,
  `supplemental/panel_registry.md`, `supplemental/component_tree.md`,
  `supplemental/naming_map.md`.
- **Styling:** `design_extraction.md`.
- **Test plan:** `e2e_test_plan.md`, `harness_migration.md`,
  `supplemental/test_area_audits/*`.

Requirements are traced by **story ID** (e.g. `SEC-13`), not `REQ-*`.

## Repo layout (verified)

- Backend: `sculptor/sculptor/` (Python, FastAPI). ElementIDs live in
  `sculptor/sculptor/constants.py` (a `StrEnum`, ~559–562 entries today).
- Frontend: `sculptor/frontend/` (TypeScript, Electron + React, Vite). Source
  under `sculptor/frontend/src`.
- Integration tests: `sculptor/tests/integration/frontend/` (~207 `test_*.py`),
  Playwright + pytest. Harness in `sculptor/sculptor/testing/`
  (`pages/` shells, `elements/` component POMs), fixtures in
  `sculptor/sculptor/testing/resources.py` and
  `sculptor/tests/integration/frontend/conftest.py`, shared helpers in
  `playwright_utils.py`.
- Core lib: `imbue_core/`. CLI: `tools/sculpt/`.

### Current frontend structure (today — the docking model)

- `src/App.tsx`, `src/Router.tsx`, `src/Main.tsx` — app entry/routing.
- `src/layouts/PageLayout.tsx` (+ `hooks/usePageLayoutKeyboardShortcuts.ts`) — the
  current page shell (top bar / docking host).
- `src/pages/workspace/` — `WorkspacePage.tsx`, plus `panels/`, `components/`
  (incl. `components/diffPanel/`, `chat-alpha/`), `hooks/`, `utils/`.
- `src/pages/add-workspace/` — the `/ws/new` page (to be replaced by the modal).
- `src/pages/home/`, `src/pages/settings/`, `src/pages/debug/`, `src/pages/error/`.
- `src/components/` (~149 dirs), `src/common/` (~46 dirs), `src/hooks/`,
  `src/styles/`, `src/api/`, `src/stories/`.

> The current `src` uses the **docking/zone** model. The new shell is built in new
> dirs under `src` (`components/nav`, `components/sections`,
> `pages/workspace/WorkspaceLayoutShell.tsx`, etc. per
> `supplemental/component_tree.md`); the old docking shell is deleted in Phase 7
> once unreferenced. We do **not** move the tree to `frontend_old`.

## Prototype branches (verified present, local + origin)

- `bryden/scu-1474-compact-workspace-layout` — layout redesign (sidebar, sections,
  panels, DnD, master-detail, diff viewer, history). Source of shape/styling.
- `bryden/scu-1494-rewrite-new-workspace-modal` — the new-workspace modal.
- `bryden/mobile-frontend` — mobile shell (OUT OF SCOPE here; constraint only).

Inspect prototype files without checking out:
`git show bryden/scu-1474-compact-workspace-layout:<path>` or
`git cat-file -e <branch>:<path>` to confirm existence. Verified to exist:
`components/panels/PanelSection.tsx`, `components/panels/CompactLayout.tsx`,
`components/panels/PanelDndProvider.tsx`, `components/nav/WorkspaceNavSidebar.tsx`,
`common/perf/workspaceSwitchProfiler.ts` (all `scu-1474`), and
`components/NewWorkspaceModal/NewWorkspaceModal.tsx` (`scu-1494`). Full styling map
(every component + its `.module.scss`) is in `design_extraction.md`.

## Naming map essentials (`supplemental/naming_map.md`)

New code uses `goals.md` vocabulary; do not carry prototype names forward.

- zone → **section** (left/center/right/bottom); `<zone>:split` half →
  **sub-section** (flat keyspace: `left:secondary`, etc.).
- focus / `focusedZone` → **active section / active sub-section**.
- zone visibility → **collapsed/expanded** (`sectionExpandedAtom`).
- Atoms: `zoneAssignmentsAtom`→`panelPlacementAtom`,
  `activePanelPerZoneAtom`→`activePanelPerSubSectionAtom`,
  `sectionSizePercentAtom`→`sectionSizesAtom`,
  `focusedZoneAtom`→`activeSubSectionAtom`, `maximizedZoneAtom`→`maximizedSectionAtom`.
- The prototype's many per-concern atomFamilies **collapse into one**
  `workspaceLayoutFamily(workspaceId)` (consolidated snapshot).
- **Deleted outright** (do not port): `expandedPanelIdAtom` (old expand/review
  mode), `sectionSizesSharedAtom` (share-sizes setting), `tabStripPositionAtom`,
  `panelEnabledAtom`/`defaultEnabled`/`isBuiltin` (Panels page), `zoneSizesAtom`,
  `bottom-left`/`bottom-right` zones, Zen/Focus/`/btw` atoms.

## State model essentials (`state_design.md` + `supplemental/state_atoms.md`)

- Library: **Jotai** (kept). `atomFamily` keyed by workspace id; narrow slices via
  `selectAtom` + custom equality; per-`SubSectionId`/`SectionId` slice atoms
  memoized into a module-load `Map` (a new atom per render causes re-render loops).
- Three scope buckets: **Global** (section sizes, sidebar width/collapsed,
  master-detail list width — persisted, shared), **Per-workspace** (expanded set,
  placement, order, active panel, splits, active sub-section — persisted, isolated),
  **Transient** (maximized, drag preview, ring — never persisted).
- Flat keyspace: `SectionId = left|center|right|bottom`;
  `SubSectionId = SectionId | ${SectionId}:secondary`. Helpers `toSecondary`,
  `toSection`, `isSecondary`.
- Switching workspaces = a single write to `activeWorkspaceIdAtom` via
  `switchActiveWorkspaceAtom`; proxies resolve the active scope per read/write.
- Invariants enforced inside write-side action atoms: center never collapses;
  collapsing the active section reassigns active (default center); split self-heal
  (emptying a half closes the split; guard the reload window where a dynamic panel
  is assigned but its task/terminal source hasn't loaded); single-instance add
  activates in place.
- `RING_VISIBLE_MS = 2000`.

## Persistence essentials (`supplemental/persistence_interface.md`)

- One `WorkspaceLayoutState` per workspace + one `GlobalLayoutState`. Shapes are in
  the doc.
- All reads/writes go through `LayoutPersistenceAdapter`
  (`read` synchronous, `write` debounced, `remove`, optional `prefetch`).
  `LocalStorageLayoutAdapter` today: keys `sculptor-layout-ws-<id>` and
  `sculptor-layout-global`; debounce writes; flush on `beforeunload`.
- Pre-paint restore: layout atoms' initial values come from `adapter.read(scope)`
  synchronously; the switch sequence runs in one layout-effect flush (switch scope
  → set registry → place active agent / seed bottom terminal on first visit).
- **No migration.** Read only the new consolidated keys; stop writing old keys.

## Registry essentials (`supplemental/panel_registry.md`)

- `PanelDefinition { id, displayName, icon, kind: static|agent|terminal,
  defaultSection: SubSectionId, component, tabIcon?, contextMenuActions? }`. **No**
  `enabled`/`defaultEnabled`/`isBuiltin`.
- Static single-instance: `files` (left), `changes` (left), `commits` (left),
  `review-all` (none), `actions` (right), `skills` (right), `browser` (none),
  `notes` (right).
- Dynamic multi-instance: `agent:<taskId>` (center, wraps chat, close = delete
  confirm), `terminal:<wsId>:<n>` (bottom, wraps xterm, close = confirm). Derived
  from task/terminal data atoms for the active workspace; **component identities
  cached by id** (no remount on registry rebuild). Multi-instance panels are
  renamable; single-instance are not.
- Files/Changes/Commits share a global master-detail list width
  (`GlobalLayoutState.masterDetailListWidthPx`).

## Component tree essentials (`component_hierarchy.md` + `supplemental/component_tree.md`)

Intended final layout under `sculptor/frontend/src`:

- `components/nav/WorkspaceSidebar.tsx`, `CollapsedSidebarToggle.tsx`;
  `components/layout/sidebarAtoms.ts`.
- `components/sections/`: `SectionGrid.tsx` (← `CompactLayout`),
  `SplittableSection.tsx`, `PanelSection.tsx`, `SectionHeader.tsx`
  (← `SectionTabBar`), `SectionBody.tsx`, `EmptySectionState.tsx`
  (← `EmptyPanelLauncher`), `ResizeHandle.tsx`, `AddPanelDropdown.tsx`,
  `PanelDndProvider.tsx`, `sectionAtoms.ts`, `sectionActions.ts`,
  `persistence/{LayoutPersistenceAdapter,LocalStorageLayoutAdapter,types}.ts`,
  `registry/{panelRegistry,dynamicPanels}.tsx`.
- `pages/workspace/`: `WorkspacePage.tsx` (useIsMobile branch),
  `WorkspaceLayoutShell.tsx`, `WorkspaceHeader.tsx` (← `WorkspaceBanner`),
  `panels/` (AgentPanel, TerminalPanel, FilesPanel, ChangesPanel, CommitsPanel,
  ReviewAllPanel, ActionsPanel, SkillsPanel, BrowserPanel, NotesPanel,
  MasterDetailPanel).
- `common/hooks/useLayoutMode.ts`;
  `common/state/hooks/usePerWorkspacePanelLayout.ts`.

**Required memoization boundaries (hard requirement):** `SectionGrid` (sizes /
expand-collapse) → memoized `SplittableSection` (its split slice) → memoized
`PanelSection` (narrow per-sub-section flags) → memoized `SectionHeader`
(displayed-panel-ids + active id + ghost) + memoized `SectionBody` (resolved
active panel *component*, identity-cached). `PanelDndProvider` subscribes to the
**stable** dragged-panel id, not the moving preview. Per-section ring is its own
slice. Full subscription list in `supplemental/component_tree.md`.

## Test harness essentials (`harness_migration.md` + audits)

- Section/panel selectors keyed by the flat sub-section keyspace; suffix the
  `SubSectionId` at the `data-testid` level (e.g. `${SECTION_HEADER}-left:secondary`)
  rather than minting `*_SECONDARY` enum members.
- **Rewrite (keep signatures = shim):** `pages/project_layout.py` (tab API →
  sidebar + section API; keep cross-cutting survivors), `pages/task_page.py` (banner
  → header; agent-tab-bar → panel-tab POM; file-browser/changes/history/diff bundle
  → three panel POMs + shared viewer). The load-bearing
  `playwright_utils.start_task_and_wait_for_ready` → `create_workspace()` **keeps its
  signature** (≈177 importers); rewrite internals only.
- **New POMs:** `workspace_sidebar.py`, `workspace_section.py` (+ `PanelTab`),
  `section_split.py`, `add_panel_dropdown.py` (shared), `panel_empty_state.py`,
  `new_workspace_dialog.py`, `empty_first_run.py`, plus refactored
  `diff_viewer.py` + `master_detail_panel.py` + `files_panel.py`/`changes_panel.py`
  /`commits_panel.py`.
- **Delete POMs:** `panel_zones.py`, `zen_mode.py`, `btw_popup.py`,
  `settings_panels.py`, `pages/add_workspace_page.py`.
- **DnD testability:** add a `KeyboardSensor` + drag handle to `PanelDndProvider`;
  wrap in a `drag_panel_to_section()` helper. (Built in Phase 4.)
- ElementID add/remove lists are in `harness_migration.md` §2 and each audit's §5;
  run `just generate-api` after edits.
- Perf: carry forward `common/perf/workspaceSwitchProfiler.ts` (`ws-switch.*`
  marks); use the `measure-react-renders` skill for SWITCH-02/05.

## Conventions (`.sculptor/*` + `CLAUDE.md` + style guide)

- Pre-commit (only when committing, not while iterating): `just format`,
  `just check` (lint + types + ratchets), `just test-unit`. Ratchets:
  `just ratchets` / `just ratchets-broken`.
- Type generation: **`just generate-api`** after any `ElementIDs` change (TS types
  are generated from backend models).
- Integration tests: use the **`/run-integration-test`** skill, never `pytest`
  directly. Write tests via `/write-integration-test`; debug via
  `/debug-integration-test`; deterministic agent behavior via `FakeClaude`. Manual
  /visual QA via `/auto-qa-changes`.
- Unit tests: `just test-unit` (`test-unit-backend` / `test-unit-frontend`).
  Frontend unit = Vitest, next to source.
- Frontend: `IconButton`s in a `Flex` need `gap="2"` (Radix hover negative
  margins). Use design tokens (see `/frontend-design-tokens`); read
  `docs/development/style_guide.md` and `docs/development/style/frontend.md`.
- Comments: present-tense rationale, no change-narration (style guide).
- Commit trailer: `Co-authored-by: Sculptor <sculptor@imbue.com>`. Commit/PR text
  is world-readable — scrub PII/internal refs (`CLAUDE.md`).
- Branch: `bryden/tungsten-seriema` (this work); main branch is `main`.

## Cross-cutting decisions baked into this plan

All resolved (2026-06-23) — see `DECISIONS_NEEDED.md` for the full record. The
load-bearing ones:

1. **Strangler rewrite** (reuse content, replace shell) — not a `frontend_old`
   move.
2. **Harness shim** (signature-stable POMs) so content-only tests survive cutover;
   legacy suite migrated by area, not big-bang.
3. **Mobile out of scope**; keep the shell-agnostic-content constraint + a thin
   `useIsMobile` seam.
4. **Closing the last agent leaves the center empty** (AGENT-04 / AGENT-02), not
   auto-create — and the **zero-agent workspace is fully supported end-to-end**
   (backend "≥1 agent" relaxed + a zero-agent fixture).
5. **Terminal close shows a confirmation** (TERM-02, new).
6. **Delete the Component Gallery, KEEP the TanStack devtools panel** (and
   `test_tanstack_devtools_panel.py`).
7. **No bare "Terminal" agent type** — raw shell = "New terminal" panel.
8. **Delivery = one PR split into semantic commits** (per-task commits;
   per-commit review), not stacked per-phase PRs.
