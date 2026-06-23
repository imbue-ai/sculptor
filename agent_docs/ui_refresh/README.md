# Workspace UI refresh — document index

This folder holds the design and execution documents for the **Sculptor workspace
UI redesign**: a uniform panel/section model with a vertical workspace sidebar, a
simplified workspace header, and chat/terminal/files converted into panels.

The work is a **rewrite of the workspace shell** (not a refactor) that reuses the
existing content surfaces (chat, terminal, diff viewer) and deletes the deprecated
chrome (docking layout, top bar, tabs, zones, Zen/Focus, the `/btw` popup, the
Panels settings page, the `/ws/new` page). Two throwaway prototype branches back
it — `bryden/scu-1474-compact-workspace-layout` (layout) and
`bryden/scu-1494-rewrite-new-workspace-modal` (the modal) — used as a source of
*styling and shape only*, never behavior.

## Reading order

1. **`goals.md`** — start here. The authoritative description of the new design
   and behavior. Everything else serves it.
2. **`user_stories.md`** — the same behavior as addressable, testable stories
   (`SIDE-*`, `SEC-*`, `SPLIT-*`, `PANEL-*`, `AGENT-*`, `TERM-*`, `FCC-*`,
   `REVIEW-*`, `WSC-*`, `FIRST-*`, `PERSIST-*`, `SWITCH-*`).
3. **`state_design.md`** + **`component_hierarchy.md`** — the architecture: the
   state model and the React component tree that consumes it.
4. **`design_extraction.md`** — the styling map: which prototype components and
   styles to copy forward.
5. **`e2e_test_plan.md`** + **`harness_migration.md`** — the test plan and the
   page-object / ElementID / fixture migration it requires.
6. **`plan.md`** — the high-level execution plan (prose).
7. **`plan/`** — the detailed, self-contained implementation task files (start at
   `plan/00_overview.md`).

## Documents

### Behavior (source of truth)

| File | What it is |
|------|------------|
| `goals.md` | The redesign's authoritative behavior spec: sidebar, sections, panels, splits, maximize, active section, workspace creation, persistence, non-functional bars, features to deprecate. |
| `user_stories.md` | 12 areas of stable, append-only story IDs derived from `goals.md`. Behavioral only — names no implementation detail. The review/verification unit. |

### Architecture

| File | What it is |
|------|------------|
| `state_design.md` | The UI state model: global vs. per-workspace vs. transient scope; the flat sub-section keyspace; Jotai atom design; consolidated persistence behind a swappable adapter; how the model meets the non-functional bars; mobile-readiness. |
| `component_hierarchy.md` | The React component tree: the shell, the uniform `PanelSection`, the drag-and-drop architecture, and the **required memoization boundaries**. |
| `supplemental/state_atoms.md` | Concrete Jotai atom inventory and signatures (types, scope atoms, narrow read slices, write-side action atoms + invariants, transient atoms, registry atoms). |
| `supplemental/persistence_interface.md` | `WorkspaceLayoutState` / `GlobalLayoutState` snapshot shapes, the `LayoutPersistenceAdapter` interface, the localStorage adapter, the pre-paint restore + switch sequence, deletion / no-migration rules. |
| `supplemental/panel_registry.md` | `PanelDefinition`, the static panel set, dynamic agent/terminal derivation + component-identity caching, and the add/close/rename lifecycle. |
| `supplemental/component_tree.md` | The intended final file layout under `sculptor/frontend/src` and the exact narrow subscription each memoized component holds. |
| `supplemental/naming_map.md` | The prototype → rewrite rename table (vocabulary, atoms/types retained, and state deleted outright). |

### Styling

| File | What it is |
|------|------------|
| `design_extraction.md` | A styling-only catalog of the prototype components/`.module.scss` worth copying forward, plus an explicit "do not copy" list. |

### Testing

| File | What it is |
|------|------------|
| `e2e_test_plan.md` | The consolidated plan to bring the ~207-file frontend integration suite in line with the redesign: CREATE / DELETE / REWRITE / UPDATE / RENAME / MIGRATE per file, plus the story→test coverage map. |
| `harness_migration.md` | The page-object, ElementID, fixture, and terminology changes the redesign forces on the test harness; the drag-and-drop testability decision; the perf tooling. |
| `supplemental/test_area_audits/sidebar_nav.md` | Per-file audit: top bar + tabs → sidebar + navigation. |
| `supplemental/test_area_audits/sections_panel_layout.md` | Per-file audit: sections, splits, drag-and-drop, empty state (mostly net-new). |
| `supplemental/test_area_audits/agent_terminal_panels.md` | Per-file audit: agent + terminal tab bars → shared panel-tab + add-panel-dropdown POMs. |
| `supplemental/test_area_audits/workspace_creation.md` | Per-file audit: `/ws/new` page → modal + empty first-run. |

### Execution

| File | What it is |
|------|------------|
| `plan.md` | The high-level execution plan in prose: strategy, phase narrative, what to copy from the prototypes, testing approach, risks. |
| `plan/` | The detailed implementation plan — a folder of self-contained task files (`00_overview.md` is the task index). Modeled on the `/sculptor-workflow:plan` output. **Note:** this folder is gitignored (`.gitignore` excludes `agent_docs/**/plan/`), so it exists locally but is not committed by default — see `plan/DECISIONS_NEEDED.md` → C6 to track it. |
| `plan/DECISIONS_NEEDED.md` | The strategy/design decisions — **resolved** (final answers recorded). The A/B/C IDs are referenced by the task files. |

## Conventions

- **`goals.md` wins.** Where any document (including a prototype) disagrees with
  `goals.md`, `goals.md` is correct.
- **The prototypes are shape/styling references only.** Their in-branch notes
  (`agent_docs`, test plans) are brainstorms and are not trustworthy.
- **Vocabulary is fixed** by `goals.md` and `supplemental/naming_map.md`: section
  (left/center/right/bottom), sub-section, panel, open vs. active panel,
  collapsed/expanded, maximized, active section, split, workspace sidebar,
  workspace header. No "zone", "focus mode", "docking", or "tab" (meaning a
  panel) in new code.
- **No backwards compatibility.** Layouts created before this work are not
  migrated; "persisted" means state created on this branch.
