# New Workspace Modal — Cruft Cleanup

## Overview

The `bryden/scu-1494-rewrite-new-workspace-modal` branch replaced the
legacy `/ws/new` page with a New Workspace modal (plus an inline form on
an empty Home). The migration works, but it landed a layer of cruft —
much of it carried over from an extremely stale branch — that describes
or defends behavior the new design no longer has. The result is
debt-on-debt: workarounds, dead helpers, redundant runtime guards, and
tests that exercise pure logic through the browser.

This spec plans a focused cleanup that fixes each issue **at its source**
and is **net-negative on lines of code**. We are not adding features; we
are removing accumulated debt and, in one case, fixing a product
limitation at its root rather than papering over it in tests.

The seven issues identified:

1. **Stale `firstLoad=true` comments** in `sculptor/sculptor/testing`
   (`playwright_utils.full_spa_reload`, `server_utils.spawn_instance`)
   justify navigation choices by a modal auto-open-on-first-load that
   does not exist on this branch (zero `firstLoad` references; Home
   renders an inline form, not an auto-opened modal).

2. **`navigate_to_home_page` full SPA reload** — when already on `/home`
   the helper tears down and rebuilds the whole SPA, purely because
   `RecentWorkspaces` fetches once on mount and never refreshes. Fix at
   the source by making the recent-workspaces list live-update.

3. **Dead helper `read_branch_name_field`** in `playwright_utils.py` —
   never called; the page object's `read_branch_name()` is the real
   path.

4. **Duplicated app-ready beacon** — `ADD_WORKSPACE_BUTTON.or_(START_TASK_BUTTON)`
   plus a multi-line cautionary comment is copy-pasted across
   `resources.py`, `sculptor_instance.py`, and `server_utils.py`.
   Consolidate into one helper.

5. **`test_home_toggle_safety.py` weirdness** — integration tests that
   inject stale tab-order via a bespoke `set_local_storage_item_with_storage_event`
   helper and synthetic `storage` events, re-testing pure hook logic
   already covered by `useHomeToggle.test.tsx`.

6. **Legacy `__new_workspace_<draftId>__` pseudo-tab defense** — the
   runtime filter in `isVisibleTabId` is redundant (the single chokepoint
   `effectiveOpenTabIdsAtom` already excludes these ids), while the
   migration boundary `createMigratingTabsStorage` launders the dead ids
   into the new storage shape unfiltered. Scrub at the boundary; simplify
   the runtime; delete the now-dead symbols.

7. **Misplaced test** — `test_deleting_project_also_deletes_its_workspaces`
   lives in `test_new_workspace_modal.py` but tests project-deletion
   cascade. Move it to its own file.

**This is NOT:** a redesign of the modal, the Home page, or the tab
system; nor a change to what the user sees (except issue 2's live Home
list, which is a fix, not a redesign).

**Decisions (from Q&A):** Issue 2 is **in scope at full effort** via
**Option C** — push the data the recent list needs over the existing
websocket and derive the list from a live atom, rather than fetching it
once over REST. All seven issues land as **one cleanup PR** on this
branch.

## User Scenarios

### Live Home list — workspace created elsewhere appears (REQ-HOME-1, REQ-HOME-3)
The user is sitting on the Home page. In another window — or via the
`sculpt` CLI, or another agent — a new workspace is created. Without the
user touching anything, the new workspace appears in the Home
recent-workspaces list, sorted by recency. Today it would not appear
until the page was reloaded.

### Live Home list — deletion disappears everywhere (REQ-HOME-2, REQ-HOME-4)
The user deletes a workspace from the Home list. The row disappears
immediately (optimistically), and the same workspace also disappears
from the "closed workspaces" pill in the top bar — both surfaces are
fed by one source, so they cannot disagree. If the delete fails, the row
returns.

### Live Home list — activity reorders the list (REQ-HOME-3)
An agent in a closed-but-not-deleted workspace produces new activity
(its `last_activity_at` advances). The Home list re-sorts to bring that
workspace up, live, without a reload. The "N agents" count on a row
reflects task additions/removals for that workspace.

### First paint and closed workspaces (REQ-HOME-5, REQ-HOME-6)
On first load of Home, the list shows a brief loading state, then
renders **all** recent workspaces — including closed-but-not-deleted
ones, which is current behavior. Zero workspaces still renders the
inline new-workspace form (`HOME_NEW_WORKSPACE_FORM`), unchanged.

### `navigate_to_home_page` becomes a plain navigation (REQ-NAV-1)
Because the Home list now updates live, the integration-test helper
`navigate_to_home_page` no longer needs to force a full SPA reload when
already on `/home`. A test that creates a workspace via the CLI and then
"goes Home" sees it appear through the live update; the helper is a
simple navigate-or-no-op.

### Upgrading from a pre-modal session — stale draft tabs are scrubbed (REQ-TABS-1, REQ-TABS-2)
A user upgrades from a pre-modal build whose `localStorage` still holds
a `__new_workspace_<draftId>__` entry in the persisted tab order. On
load, the migration boundary strips that dead id. The Home toggle behaves
correctly (no defunct navigation), and no runtime per-consumer guard is
needed because the persisted order is clean.

### Test suite carries no phantom-modal lore (REQ-TESTINFRA-1..4)
A developer reading the `sculptor/sculptor/testing` helpers finds
comments that match the code's real reasons. There is no reference to a
`firstLoad=true` modal auto-open (which does not exist), no dead
`read_branch_name_field`, and one shared app-ready beacon helper instead
of three copy-pasted unions.

## Requirements

### Live recent-workspaces list (issue 2 — Option C)

- **REQ-HOME-1** — The Home recent-workspaces list MUST update live as
  workspaces are created, without a manual page reload, including
  workspaces created outside the current window (CLI, other windows,
  other agents).
- **REQ-HOME-2** — Workspace deletion MUST be reflected live in the Home
  list and MUST remain optimistic (row hides before the server ack, and
  is restored on failure).
- **REQ-HOME-3** — The list MUST stay correctly sorted by
  `last_activity_at`, and each row's agent count MUST reflect the
  workspace's current task set, updating live for **all** workspaces in
  the list — including closed-but-not-deleted ones, not just those open
  as tabs.
- **REQ-HOME-9** — To satisfy REQ-HOME-3, the backend MUST re-emit a
  workspace's derived fields (`agent_count`, `last_activity_at`) over the
  stream whenever one of that workspace's tasks is created or deleted (or
  the workspace itself is created). It MUST NOT re-emit the workspace on
  per-message / per-chunk task stream events — those cannot change the
  aggregates and would be a needless hot-path cost.
- **REQ-HOME-4** — The Home list and the top-bar "closed workspaces"
  pill (`ClosedWorkspacesPill`) MUST be fed from one shared source of
  truth so they cannot show divergent data.
- **REQ-HOME-5** — Initial render MUST show all recent workspaces,
  including closed-but-not-deleted ones, matching today's behavior.
- **REQ-HOME-6** — The empty state (zero non-deleted workspaces) MUST
  continue to render the inline new-workspace form
  (`HOME_NEW_WORKSPACE_FORM`); the top-bar "+" stays hidden there.
- **REQ-HOME-7** — The data needed to render and sort the list
  (`description`, `source_branch`, `project_name`, `agent_count`,
  `last_activity_at`, `created_at`, `is_open`, `is_deleted`, `harness`)
  MUST be available to the frontend live, without the one-shot
  `listRecentWorkspaces` REST fetch as the source of truth.
- **REQ-HOME-8** — The `listRecentWorkspaces` REST fetch MUST be removed
  from both consumers and the endpoint deleted. To make first paint need
  no REST call, the **initial** stream snapshot MUST carry the
  denormalized fields (REQ-HOME-7) for all non-deleted workspaces,
  including closed ones.

### Test helper simplification (issue 2 consequence)

- **REQ-NAV-1** — `navigate_to_home_page` MUST drop its full-SPA-reload
  branch and become a plain navigate-or-no-op; the staleness workaround
  it existed for is gone once the list is live.
- **REQ-NAV-2** — Existing integration tests that relied on
  `navigate_to_home_page` refreshing the list MUST still pass (they now
  observe the live update via Playwright's auto-waiting assertions).

### Test-infra cruft (issues 1, 3, 4)

- **REQ-TESTINFRA-1** — All comments in `sculptor/sculptor/testing`
  referencing a `firstLoad=true` modal auto-open or its pointer-event
  overlay MUST be removed or rewritten to state the real reason for the
  navigation (no behavior change to the helpers' actions).
- **REQ-TESTINFRA-2** — The dead `read_branch_name_field` helper in
  `playwright_utils.py` MUST be deleted.
- **REQ-TESTINFRA-3** — The `ADD_WORKSPACE_BUTTON.or_(START_TASK_BUTTON)`
  app-ready beacon MUST be defined once as a shared helper and reused by
  `resources.py`, `sculptor_instance.py`, and `server_utils.py`; the
  copy-pasted cautionary comment collapses to one place.
- **REQ-TESTINFRA-4** — The consolidation MUST preserve the existing
  `.first` / `expect_app_not_onboarding` composition behavior the
  current call sites rely on.

### Home-toggle test weirdness (issue 5)

- **REQ-TOGGLE-1** — The pure-logic no-op cases in
  `test_home_toggle_safety.py` (the `__home__` and
  `__new_workspace_*__` pseudo-tab cases) MUST be removed as integration
  tests, since `useHomeToggle.test.tsx` already covers them at the unit
  level.
- **REQ-TOGGLE-2** — The genuinely browser-level golden-path toggle test
  (workspace ↔ Home round-trip, `aria-pressed`) MUST be kept.
- **REQ-TOGGLE-3** — Once unused, the
  `set_local_storage_item_with_storage_event` helper MUST be deleted.
- **REQ-TOGGLE-4** — Unit coverage for the pseudo-tab safety guard MUST
  remain intact (see REQ-TABS-4) so removing the integration tests loses
  no coverage.

### Legacy pseudo-tab cleanup (issue 6)

- **REQ-TABS-1** — `createMigratingTabsStorage` MUST drop dead
  `__new_workspace_<draftId>__` ids from the persisted tab order, applied
  to both the legacy-key migration path and reads of the current
  `sculptor-tabs` key, so the persisted order can never contain them in
  this version.
- **REQ-TABS-2** — `isVisibleTabId` (in `useHomeToggle.ts`) MUST be
  simplified to exclude only `HOME_TAB_ID`; the redundant
  `NEW_WORKSPACE_TAB_PREFIX` clause MUST be removed.
- **REQ-TABS-3** — The now-dead symbols `newWorkspaceTabId`,
  `NEW_WORKSPACE_TAB_PREFIX` (unless retained module-private to the
  storage scrub), and `parseDraftIdFromTabId` MUST be deleted.
- **REQ-TABS-4** — A unit test MUST cover the migration scrub (stale
  `__new_workspace_*__` ids are stripped on load). The `useHomeToggle`
  unit tests SHOULD be updated to drop the now-unreachable draft-tab
  cases while keeping the `__home__` no-op case.
- **REQ-TABS-5** — Existing tab behavior for real workspace ids and the
  current pseudo-tabs (`__home__`, `__settings__`, `__component_gallery__`)
  MUST remain unchanged.

### Test relocation (issue 7)

- **REQ-MOVE-1** — `test_deleting_project_also_deletes_its_workspaces`
  MUST move out of `test_new_workspace_modal.py` into a new
  `test_project_deletion.py`, taking the `_extract_workspace_id` helper
  with it.
- **REQ-MOVE-2** — No assertion logic changes; the test MUST still pass
  unchanged after the move.

### Cross-cutting

- **REQ-CLEAN-1** — The net change across the seven issues MUST be
  net-negative on lines of code (excluding the spec and any new focused
  unit tests).
- **REQ-CLEAN-2** — No issue may be "fixed" by adding a new downstream
  workaround; each MUST be addressed at its source.
- **REQ-CLEAN-3** — `just format`, `just check`, and `just test-unit`
  MUST pass; affected integration tests MUST pass.

## Non-Goals

- Redesigning the New Workspace modal, the inline Home form, the Home
  page layout, or the tab system.
- Changing what the user sees, except the Home list now updating live
  (issue 2) — which is a fix, not a redesign.
- Reworking the websocket/streaming transport itself; Option C adds
  fields to the existing stream, it does not change how streaming works.
- Touching the `firstLoad`-style direct-to-`/home` navigation choices in
  the test harness beyond fixing their comments (the actions stay; only
  stale rationale is removed). Issue 1 is comment-only.
- Backfilling or migrating historical persisted state beyond stripping
  the known-dead `__new_workspace_*__` ids.

## Open Questions

- **Task-derived freshness — RESOLVED (see REQ-HOME-3, REQ-HOME-9).**
  Decision: fully live for all workspaces. Cost is acceptable because,
  per `sql_implementation.py:329-342`, `agent_count = COUNT(tasks)` and
  `last_activity_at = MAX(task.created_at)` change **only** on task
  create/delete (and workspace create) — never on messages/chunks/state.
  The re-emit trigger MUST be scoped to task membership changes.
  Remaining for the architect: the exact emission seam where a task
  create/delete also refreshes and emits its parent workspace, and
  whether the derived fields ride on the existing `Workspace` payload or
  a parallel structure. `created_at` and `project_name` are non-aggregate
  (project_name changes only on project rename).
- **Initial snapshot completeness (now a hard requirement):** the
  endpoint is being deleted (REQ-HOME-8), so the initial stream dump MUST
  carry the denormalized fields for all non-deleted workspaces. The
  architect must confirm the initial dump's workspace set and extend its
  payload accordingly.
- **`deletedWorkspaceIdsAtom` fate:** if both list surfaces derive from
  the live `workspacesArrayAtom` (which already filters `isDeleted`),
  this bridge atom's only reader disappears and it can likely be deleted
  along with its stream-propagation block. Confirm no other reader before
  removing.
- **`project_name` source:** add it to the streamed workspace payload, or
  derive it frontend-side from an existing projects atom (if one exists)?
