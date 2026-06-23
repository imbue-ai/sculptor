# Workspace UI Refresh — Implementation Plan

## Summary

Rewrite the Sculptor workspace shell into the section/panel model from
`goals.md`: a vertical workspace sidebar, a simplified workspace header, and a
four-section grid whose every region is a uniform panel container. Chat, terminal,
files, changes, commits, review-all and the rest become panels. The shell, layout
state, persistence, registry, drag-and-drop, workspace-creation modal, and
first-run page are new code (styling/shape copied from the `scu-1474`/`scu-1494`
prototypes); the existing content surfaces (chat, xterm, diff viewer) are reused
in place; the docking layout, top bar, tabs, zones, Zen/Focus, `/btw`, Panels
settings, and `/ws/new` are deleted.

> **This plan replaces the usual spec + architecture inputs with the
> `agent_docs/ui_refresh/` document set.** Requirements are traced by **story ID**
> (`SIDE-*`, `SEC-*`, `SPLIT-*`, `PANEL-*`, `AGENT-*`, `TERM-*`, `FCC-*`,
> `REVIEW-*`, `WSC-*`, `FIRST-*`, `PERSIST-*`, `SWITCH-*`) from `user_stories.md`,
> not `REQ-*`. Open decisions the plan made on your behalf are in
> `DECISIONS_NEEDED.md`. Shared codebase facts are in `_exploration_notes.md`.

## Phases

- **Phase 1: Foundation** — state, persistence, and registry as pure,
  unit-tested modules everything else consumes.
- **Phase 2: Desktop shell + agent panel + cutover** — the sidebar, section grid,
  uniform panel container, the agent panel wrapping existing chat, and the
  workspace-route cutover, plus the harness spine (signature-stable POMs).
- **Phase 3: The rest of the panels** — terminal, the shared explorer + diff
  viewer, Files/Changes/Commits, the other registered panels, the add-panel
  dropdown and empty-state launcher, with their POMs and tests.
- **Phase 4: Interactions** — drag-and-drop (with keyboard sensor), splits,
  maximize, active section + ring, and keyboard shortcuts, with their tests.
- **Phase 5: Workspace creation + first-run** — the modal, four entry points,
  creation modes, and the empty first-run page, with their tests.
- **Phase 6: Persistence wiring + seamless switching** — adapter↔atom wiring,
  default-layout seeding, and the pre-paint switch sequence, with their tests.
- **Phase 7: Remove deprecated features** — delete the docking shell and every
  deprecated surface and its dead state/tests.
- **Phase 8: Legacy test-suite migration + rename** — execute the remaining
  `e2e_test_plan.md` migrations and the terminology rename pass.
- **Phase 9: Perf tooling + non-functional bars** — the switch profiler and
  `measure-react-renders` scenarios.
- **Phase 99: Finalize** — verify all added tests, then launch review.

## Phase Rationale

Foundation comes first because every component reads the layout/registry contract
(state → components, not the reverse). The shell + agent panel + cutover land
together in Phase 2 so the app is *usable* and the real test harness exists as
early as possible — subsequent work is then verified against the live shell.
Panels (Phase 3) and interactions (Phase 4) are layered on the working shell.
Workspace creation (Phase 5) and persistence/seamless-switching (Phase 6) build on
a populated layout. **Removal (Phase 7) is deliberately late**: in a strangler
rewrite the old shell can only be deleted once the new one fully owns the route,
so deleting earlier would break the app. The legacy test migration (Phase 8) and
the mechanical rename follow once all surfaces and POMs exist. Perf verification
(Phase 9) is last because it measures the finished interactions. Tests are not
deferred to the end: each feature phase adds its own `data-testid`s, POMs, and
CREATE tests; Phase 8 is only the *legacy* burn-down.

## Task Index

| File | Task | Phase | Stories |
|------|------|-------|---------|
| `01_01_core_layout_types.md` | Core layout types + keyspace helpers | 1 | SEC-*, SPLIT-* (foundation) |
| `01_02_persistence_adapter.md` | Snapshot shapes + `LayoutPersistenceAdapter` + localStorage impl | 1 | PERSIST-01..03, SWITCH-03 |
| `01_03_layout_atoms.md` | Consolidated layout atoms, scope/switch, narrow read slices | 1 | PERSIST-01/02/05, SWITCH-* |
| `01_04_action_atoms.md` | Write-side action atoms + invariants | 1 | SEC-05..08, SPLIT-*, PANEL-07/15 |
| `01_05_transient_atoms.md` | Maximized / drag-preview / active-ring transient atoms | 1 | SEC-11/13/21, PANEL-08..10 |
| `01_06_panel_registry.md` | Panel registry: static defs + dynamic agent/terminal + identity cache | 1 | PANEL-01/05/15, AGENT-02, SWITCH-02 |
| `02_01_design_foundation.md` | Copy tokens / scrollbar mixin / Radix overrides from prototype | 2 | (styling foundation) |
| `02_02_workspace_sidebar.md` | `WorkspaceSidebar` + resize + version + report-bug + sidebar atoms | 2 | SIDE-01..14, SIDE-17 |
| `02_03_section_grid.md` | `SectionGrid` + `ResizeHandle` geometry/clamps | 2 | SEC-17, SEC-22, SEC-01 (frame) |
| `02_04_panel_section.md` | `SplittableSection`/`PanelSection`/`SectionHeader`/`SectionBody` + memo boundaries | 2 | SEC-09, SWITCH-02/05 |
| `02_05_agent_panel.md` | `AgentPanel` wrapping existing chat + dynamic agent wiring | 2 | AGENT-01..03, AGENT-09 |
| `02_06_layout_shell_cutover.md` | `WorkspaceLayoutShell` + `WorkspaceHeader` + route cutover | 2 | SEC-01, SIDE-13, AGENT-01 |
| `02_07_harness_spine.md` | Rewrite `project_layout`/`task_page` POMs (shim) + first ElementIDs/POMs + smoke tests | 2 | SIDE-01/07, SEC-01 |
| `03_01_terminal_panel.md` | `TerminalPanel` wrapping xterm + dynamic terminal wiring + close-confirm | 3 | TERM-01..04 |
| `03_02_explorer_layout_diff_viewer.md` | Shared `ExplorerLayout` + embeddable `DiffViewer` (triple-dot menu) | 3 | FCC-02/04/05/06/07 |
| `03_03_files_changes_commits.md` | Files / Changes / Commits panels | 3 | FCC-01..07, REVIEW-* deps |
| `03_04_static_panels.md` | Review-all / Actions / Skills / Browser / Notes panels (no enable/disable) | 3 | REVIEW-01/02, PANEL-05/15 |
| `03_05_add_panel_dropdown_empty_state.md` | `AddPanelDropdown` + `EmptySectionState` quick actions | 3 | PANEL-01..05, PANEL-12, SEC-19 |
| `03_06_fcc_tests.md` | FCC POMs (DiffViewer/ExplorerLayout) + FCC CREATE/migrate tests | 3 | FCC-01..07 |
| `03_07_agent_terminal_panel_tests.md` | PanelTab POM + agent/terminal panel CREATE/migrate tests | 3 | AGENT-01..09, TERM-01..05, PANEL-07/11/14 |
| `04_01_dnd_provider.md` | `PanelDndProvider` + KeyboardSensor + drag handle + dropzones | 4 | PANEL-08..10, PANEL-16 |
| `04_02_splits.md` | Split create/close, direction rules, self-heal | 4 | SPLIT-01..06 |
| `04_03_maximize.md` | Maximize/restore + presentation (header hide, OS padding) | 4 | SEC-13..16, SEC-21, SPLIT-06 |
| `04_04_active_section_ring.md` | Active section selection + rebuilt ~2s ring fade | 4 | SEC-10..12 |
| `04_05_keyboard_shortcuts.md` | Section/panel/sidebar/agent shortcuts + keybindings settings | 4 | SEC-05..08/12/15/20, SIDE-15, PANEL-06/13, WSC-02 |
| `04_06_interaction_tests.md` | Split/empty-state POMs + SEC/SPLIT/PANEL-DnD CREATE tests | 4 | SEC-05..22, SPLIT-01..06, PANEL-08..10/16 |
| `05_01_new_workspace_modal.md` | New-workspace modal + form + branch field (copy `scu-1494`) | 5 | WSC-05, WSC-06, WSC-07 |
| `05_02_creation_entry_points.md` | Four entry points + creation modes + source-branch + MRU | 5 | WSC-01..04, WSC-08..11 |
| `05_03_empty_first_run.md` | Empty first-run page + disabled-nav state | 5 | FIRST-01..05 |
| `05_04_creation_tests.md` | Dialog/first-run POMs + `create_workspace()` shim + WSC/FIRST tests | 5 | WSC-01..11, FIRST-01..05 |
| `06_01_persistence_wiring.md` | Adapter↔atom wiring + default-layout seeding | 6 | SEC-01..04, PERSIST-01..05 |
| `06_02_seamless_switch.md` | Pre-paint switch sequence + dynamic-panel placement | 6 | SWITCH-01..04, SEC-18, PERSIST-02 |
| `06_03_persistence_tests.md` | Adapter unit tests + PERSIST + SWITCH e2e tests | 6 | PERSIST-01/03/04/05, SWITCH-03/04 |
| `07_01_remove_docking_shell.md` | Delete docking layout / top bar / tabs / zones / side-toggle | 7 | (removal) |
| `07_02_remove_deprecated_features.md` | Delete Zen/Focus / `/btw` / Panels page / share-sizes / tab-strip-pos / expand toggle | 7 | (removal) |
| `07_03_remove_creation_page_and_legacy_nav.md` | Delete `/ws/new` / closed-workspaces / Component Gallery + their tests | 7 | (removal) |
| `08_01_migrate_sidebar_nav_tests.md` | Sidebar/nav legacy migration (UPDATE/REWRITE/DELETE) | 8 | SIDE-01..17 |
| `08_02_migrate_panel_content_tests.md` | Agent/terminal + FCC content-test migration (UPDATE-in-place) | 8 | AGENT-*, TERM-*, FCC-* |
| `08_03_terminology_rename.md` | Mechanical rename pass (files / fns / `@user_story` / POM methods) | 8 | (vocabulary) |
| `09_01_perf_tooling.md` | Switch profiler + `measure-react-renders` scenarios | 9 | SWITCH-01/02/05, SEC-18, PERSIST-02 |
| `99_01_verify_all_tests.md` | Run all tests added in this plan, iterate to green | 99 | (verification) |
| `99_02_launch_review.md` | Launch the review agent | 99 | (handoff) |

## How to execute

Run via `/sculptor-workflow:build` (it reads this index, builds a TODO, and
applies `implement_task.md` per task), or execute the files in order by hand. Each
task file is self-contained: read just that file plus the source it names. The open
decisions are **resolved** — `DECISIONS_NEEDED.md` records the final answers (the
build commits once per task, so the work lands as one PR of semantic commits per
Decision A3).
