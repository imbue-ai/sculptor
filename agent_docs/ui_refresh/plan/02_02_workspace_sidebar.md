# Task 2.2: Workspace sidebar (rail, repo groups, rows, resize, version, report-bug)

## Goal

Build the `WorkspaceSidebar` — the collapsible vertical nav rail that replaces the
old top bar — by copying the prototype's structure/styling and rebuilding behavior
from `goals.md`. Includes the net-new resizable handle + minimum width and the
relocated version row and report-a-bug entry.

## Stories addressed

SIDE-01 (home link), SIDE-02 (Cmd+K link), SIDE-03 (new-workspace button — direct
create, see Task 5.2), SIDE-04 (collapsible repo groups), SIDE-05 (repo `+`
add-workspace), SIDE-06 (repo settings), SIDE-07 (row → navigate), SIDE-08
(row right-click context menu), SIDE-09 (row hover: delete + menu icons), SIDE-10
(Settings link), SIDE-11 (report a bug), SIDE-12 (version), SIDE-13 (collapse to
icon; no OS-control collision on home), SIDE-14 (resize + min width), SIDE-17
(row unread indicator). Sidebar toggle hotkey (SIDE-15) is wired in Task 4.5.

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the
workspace shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.
The sidebar is **global chrome** rendered for every route
(`component_hierarchy.md` → "Top-level tree").

**What to copy** (`design_extraction.md` → "Workspace sidebar (scu-1474)"):
- `components/nav/WorkspaceNavSidebar.tsx` + `.module.scss` → rename to
  `components/nav/WorkspaceSidebar.tsx`. The rail: drag gutter with
  `getTitleBarLeftPadding()` for macOS traffic lights, top nav pills (active =
  `--accent-a3`/`--accent-11`), collapsible repo groups (hover-revealed actions via
  `:focus-within`/`[data-state=open]`), workspace rows (28px pill, `--space-5`
  indent, hover `--gray-a3`, active `--accent-a3`, hover-reveal delete + menu icons).
- `components/nav/CollapsedSidebarToggle.tsx` + `.module.scss` — the show-sidebar
  icon when collapsed.
- `components/InlineRenameInput.tsx` (reused later by panel-tab rename).
- `components/statusDot/StatusDot.module.scss` — workspace status dots.

**Net-new (NOT in the prototype)** (`design_extraction.md` ⚠️ note): the
**resizable sidebar + minimum width** (prototype rail is fixed 240px, no handle),
and the **version row + "Report a bug" entry in the sidebar bottom**. Build the
resize handle and **relocate the existing `VersionDisplay` and
`ReportProblemPopover` (both on `main`)** into the sidebar bottom. Find them on
`main`: grep for `VersionDisplay` and `ReportProblemPopover`/`ReportProblem` under
`sculptor/frontend/src/components`.

**State:** read/write `sidebarWidthAtom` and `sidebarCollapsedAtom` from
`components/layout/sidebarAtoms.ts` (Task 1.3 — writable slices of the global
layout snapshot, so width/collapsed persist globally). The workspace/repo data
comes from the existing data atoms used by today's home page and nav — reuse them
(grep `useWorkspaces`/`useProjects`/`getWorkspaceRows`).

**Reuse the existing row model:** `sidebar_nav.md` audit notes a `WORKSPACE_ROW`
surface already exists in `pages/home_page.py`
(`PlaywrightHomePage.get_workspace_rows()` + `WORKSPACE_ROW`,
`WORKSPACE_ROW_BRANCH`, `WORKSPACE_ROW_CONTEXT_MENU_DELETE`). The sidebar rows are
the successor — mirror that row shape so the POM (Task 2.7) reuses it.

This task depends on **Task 1.3** (`sidebarAtoms.ts`) and **Task 2.1** (tokens).

## Files to modify/create

- `sculptor/frontend/src/components/nav/WorkspaceSidebar.tsx` + `.module.scss` — new
  (copied/renamed from the prototype).
- `sculptor/frontend/src/components/nav/CollapsedSidebarToggle.tsx` + `.module.scss`
  — new.
- `sculptor/frontend/src/components/InlineRenameInput.tsx` (+ `.module.scss`) — copy
  if not already present on `main`.
- `sculptor/sculptor/constants.py` — add the sidebar `ElementIDs` (then
  `just generate-api`).

## Implementation details

1. Copy the prototype sidebar + collapsed toggle structure and `.module.scss`;
   rename to `WorkspaceSidebar`. Keep the `getTitleBarLeftPadding()` **helper**
   (don't inline numbers) for the macOS traffic-light gutter so the collapsed
   sidebar on the home page does not collide with the OS window controls (SIDE-13).
2. **Top links** (SIDE-01/02/03): home (route to home page), Cmd+K (opens the
   command palette — reuse the existing palette open path), new-workspace button
   (Task 5.2 wires direct-create; here render the button + testid).
3. **Repo groups** (SIDE-04/05/06): collapsible per-repo sections with a plus
   (add-workspace → dialog, Task 5.2) and a settings link (route to that repo's
   settings).
4. **Workspace rows** (SIDE-07/08/09/17): click → navigate to the workspace;
   right-click → context menu (Task 2.7/8.1 build the menu POM; render the menu
   here reusing today's workspace context-menu actions); hover → reveal delete +
   menu icons; unread indicator via `data-has-unread` (reuse today's attribute).
5. **Bottom** (SIDE-10/11/12): Settings link (route), report-a-bug
   (`ReportProblemPopover`), and the `VersionDisplay`.
6. **Resize + collapse** (SIDE-13/14): a drag handle on the right border writing
   `sidebarWidthAtom`, clamped to a minimum width; collapse toggle writing
   `sidebarCollapsedAtom` (collapsed shows only `CollapsedSidebarToggle`). Apply
   `body.sculptor-resizing` during drag (token from Task 2.1) to suppress
   webview pointer events.
7. **ElementIDs** to add (`harness_migration.md` §2 + `sidebar_nav.md` §5):
   `WORKSPACE_SIDEBAR`, `SIDEBAR_HOME_LINK`, `SIDEBAR_CMDK_LINK`,
   `SIDEBAR_NEW_WORKSPACE_BUTTON`, `SIDEBAR_REPO_GROUP`, `SIDEBAR_REPO_ADD_WORKSPACE`,
   `SIDEBAR_REPO_SETTINGS`, `SIDEBAR_WORKSPACE_ROW`, `SIDEBAR_WORKSPACE_ROW_DELETE`,
   `SIDEBAR_WORKSPACE_ROW_MENU`, `SIDEBAR_SETTINGS_LINK`, `SIDEBAR_REPORT_BUG`,
   `SIDEBAR_VERSION`, `SIDEBAR_COLLAPSE_TOGGLE`, `SIDEBAR_RESIZE_HANDLE`,
   `SIDEBAR_EXPAND_ICON`. Reuse existing `WORKSPACE_ROW`/`WORKSPACE_ROW_BRANCH`/
   `WORKSPACE_ROW_CONTEXT_MENU_DELETE`/`VERSION`/report-popover ids where the row
   matches the home-page row. Set them as `data-testid`s, then run
   `just generate-api`.
8. The sidebar is rendered globally in Task 2.6's shell wiring; this task builds the
   component + atoms + testids.

## Testing suggestions

- E2e coverage for SIDE-* is consolidated in Task 8.1 (`test_workspace_sidebar.py`,
  `test_sidebar_collapse_resize.py`, etc.). A smoke assertion (sidebar renders with
  home/Cmd+K/new-workspace links and at least one workspace row) lands in Task 2.7.
- Resize/collapse min-width is behavioral (drag → width clamps) — testable; the
  pure visual treatment is screenshot-verified.

## Gotchas

- `IconButton`s inside a `Flex` need `gap="2"` (Radix hover negative margins) —
  `CLAUDE.md` frontend guideline.
- Keep `getTitleBarLeftPadding()` as a helper; collapsed-on-home must not overlap OS
  controls (SIDE-13).
- Width/collapsed persist **globally** (one global snapshot) — use the global slices,
  not per-workspace state.
- Relocating `VersionDisplay`/`ReportProblemPopover` means *moving* them into the
  sidebar bottom; don't duplicate — the old footer placement is removed when the old
  shell is deleted (Phase 7).

## Verification checklist

- [ ] `WorkspaceSidebar` renders top links, repo groups (collapse/add/settings),
  workspace rows (click/hover/right-click/unread), and bottom (Settings/report-bug/
  version).
- [ ] Resize handle clamps to a minimum width; collapse shows only the expand icon
  and avoids OS controls on home.
- [ ] Width/collapsed read/write the global sidebar atoms (persist globally).
- [ ] New sidebar `ElementIDs` added and `just generate-api` run.
- [ ] `just check` passes.
