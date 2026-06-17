# New Workspace Modal — Cruft Cleanup

## Overview

The `bryden/scu-1494-rewrite-new-workspace-modal` branch replaced the
legacy `/ws/new` page with a New Workspace modal (plus an inline form on
an empty Home). The migration works, but it landed a layer of cruft —
much of it carried over from an extremely stale branch — that describes
or defends behavior the new design no longer has. The result is
debt-on-debt: workarounds, dead helpers, redundant runtime guards, and
tests that exercise pure logic through the browser. The same work also
surfaced two real bugs worth fixing in the same pass.

This spec plans a focused cleanup that fixes each issue **at its source**
and is **net-negative on lines of code**. We are not adding features; we
are removing accumulated debt and fixing two narrow bugs.

> **Scope note (revised):** An earlier draft of this spec also proposed
> making the Home recent-workspaces list update live by pushing its data
> over the existing websocket and deleting the `listRecentWorkspaces`
> REST endpoint ("issue 2 / Option C"). **That work is now out of
> scope.** The Home page is **not** changed to receive workspace data
> over the websocket, and the `/api/v1/workspaces/recent`
> (`list_recent_workspaces`) REST endpoint is **retained**. See
> [Removed from scope](#removed-from-scope-formerly-issue-2). The
> source-level cleanups and the two bug fixes below are all that remain.

The in-scope issues:

1. **Stale `firstLoad=true` comments** in `sculptor/sculptor/testing`
   (`playwright_utils.full_spa_reload`, `server_utils.spawn_instance`)
   justify navigation choices by a modal auto-open-on-first-load that
   does not exist on this branch (zero `firstLoad` references; Home
   renders an inline form, not an auto-opened modal). The comments must
   be rewritten to state the real reason for the navigation. The actions
   themselves — including `navigate_to_home_page`'s full SPA reload —
   **stay**, because the Home list is still fetched once on mount and the
   reload remains the correct way to refresh it.

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

8. **Target-branch flicker on `useRepoInfo` partial write (bug fix)** —
   when the new-workspace modal refreshes the current branch for a
   project, `useRepoInfo` rebuilds the shared, project-keyed `RepoInfo`
   atom by listing fields by hand, silently dropping the origin flags
   (`isGitlabOrigin` / `isGithubOrigin`) and `remoteBranches`. The open
   workspace's `WorkspaceBanner` derives "show the target branch" from
   those flags, so the target branch flickers out and back as the partial
   write lands ahead of the next full `fetchRepoInfo`. Fix at the source
   by spreading the existing `RepoInfo` and overriding only
   `currentBranch`.

9. **Reopen-from-empty-Home reverts to closed (bug fix)** — clicking a
   recent-workspace row on a freshly-reloaded, all-closed Home routes
   through `useWorkspaceNavigation.handleWorkspaceClick`, which calls
   `convertHomeTabToWorkspaceAtom`. That atom skips recording the
   open-intent when the workspace model has not loaded yet (the common
   case right after a reload), so the workspace re-closes instead of
   reopening. Fix at the source: `handleWorkspaceClick` must use
   `openWorkspaceTabAtom` (which always issues the open PATCH and marks
   the pending-open intent regardless of model-load state) — the same
   path the closed-workspaces pill already uses. Home is no longer a tab,
   so there is no home slot to convert; once unused,
   `convertHomeTabToWorkspaceAtom` is deleted.

**This is NOT:** a redesign of the modal, the Home page, or the tab
system; nor a change to what the user sees. The Home recent-workspaces
list keeps its current behavior and data source.

**Decision (from Q&A):** All in-scope issues land as **one cleanup PR**
on this branch.

### Removed from scope (formerly "issue 2")

The following were proposed in an earlier draft and are **explicitly out
of scope**. They MUST NOT be implemented in this cleanup:

- **No live Home list.** The Home recent-workspaces list is **not**
  re-fed from a live atom and is **not** changed to receive workspace
  data over the websocket. It continues to fetch once on mount via the
  REST endpoint, exactly as today.
- **The REST endpoint stays.** `list_recent_workspaces` /
  `/api/v1/workspaces/recent` is **retained**. No consumer (the Home
  list, `ClosedWorkspacesPill`, or the `sculpt` CLI) is migrated off it
  to the stream. The `get_all_workspaces` data-model path it relies on
  stays.
- **No websocket payload changes.** The streamed `Workspace` payload and
  the initial dump are **not** extended with denormalized fields
  (`agent_count`, `last_activity_at`, `project_name`, etc.), and the
  backend does **not** re-emit a workspace on task create/delete.
  `data_types.py`, `sql_implementation.py`, `web/data_types.py`, and
  `web/app.py` are untouched by this cleanup.
- **`navigate_to_home_page` keeps its full SPA reload.** Because the list
  is still fetched once on mount, the reload remains the correct refresh
  mechanism. Only its stale rationale comment (issue 1) is corrected; the
  action does not change.
- **`deletedWorkspaceIdsAtom` and `RecentWorkspaceResponse` stay.** The
  bridge atom and the existing REST response shape remain in use; no new
  `recentWorkspacesAtom` / `RecentWorkspace` type is introduced.

## User Scenarios

### Test suite carries no phantom-modal lore (issues 1, 3, 4)
A developer reading the `sculptor/sculptor/testing` helpers finds
comments that match the code's real reasons. There is no reference to a
`firstLoad=true` modal auto-open (which does not exist), no dead
`read_branch_name_field`, and one shared app-ready beacon helper instead
of three copy-pasted unions. `navigate_to_home_page` still performs its
full SPA reload — now correctly explained as refreshing the once-on-mount
recent-workspaces fetch.

### Home-toggle logic is unit-tested, not browser-tested (issue 5)
The pure-logic no-op toggle cases move out of the integration suite,
which no longer injects synthetic `storage` events; `useHomeToggle.test.tsx`
covers them. The genuine browser-level workspace ↔ Home round-trip stays.

### Upgrading from a pre-modal session — stale draft tabs are scrubbed (issue 6)
A user upgrades from a pre-modal build whose `localStorage` still holds
a `__new_workspace_<draftId>__` entry in the persisted tab order. On
load, the migration boundary strips that dead id. The Home toggle behaves
correctly (no defunct navigation), and no runtime per-consumer guard is
needed because the persisted order is clean.

### Project-deletion test lives where it belongs (issue 7)
`test_deleting_project_also_deletes_its_workspaces` is found in
`test_project_deletion.py`, not buried in the new-workspace-modal suite.

### Target branch no longer flickers (issue 8)
With an open workspace, the user opens the new-workspace modal (which
refreshes the current branch for the same project). The open workspace's
target-branch indicator stays put — the origin flags survive the
current-branch refresh, so there is no flicker-out-and-back.

### Reopening a closed workspace from a reloaded Home works (issue 9)
The user reloads the app on an all-closed Home, then clicks a recent
workspace. It reopens and navigates, instead of momentarily opening and
re-closing because the open-intent was dropped before the model loaded.

## Requirements

### Test-infra cruft (issues 1, 3, 4)

- **REQ-TESTINFRA-1** — All comments in `sculptor/sculptor/testing`
  referencing a `firstLoad=true` modal auto-open or its pointer-event
  overlay MUST be removed or rewritten to state the real reason for the
  navigation. The helpers' **actions do not change** — in particular
  `navigate_to_home_page` keeps its full SPA reload, now explained by the
  once-on-mount recent-workspaces fetch rather than a phantom modal.
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

### Target-branch flicker fix (issue 8)

- **REQ-BRANCH-1** — `useRepoInfo`'s current-branch refresh MUST preserve
  every other field on the shared `RepoInfo` atom. It MUST rebuild the
  atom by spreading the existing `RepoInfo` and overriding only
  `currentBranch`, rather than enumerating fields by hand, so the origin
  flags (`isGitlabOrigin` / `isGithubOrigin`) and `remoteBranches` are
  never dropped by the partial write.
- **REQ-BRANCH-2** — A unit test MUST cover that a current-branch refresh
  leaves the origin flags (and other non-branch fields) intact on the
  atom.

### Reopen-from-empty-Home fix (issue 9)

- **REQ-REOPEN-1** — `useWorkspaceNavigation.handleWorkspaceClick` MUST
  open a clicked recent-workspace via `openWorkspaceTabAtom` (which
  issues the open PATCH and records the pending-open intent even before
  the workspace model has loaded), so reopening a closed workspace from a
  freshly-reloaded all-closed Home succeeds instead of reverting to
  closed.
- **REQ-REOPEN-2** — `convertHomeTabToWorkspaceAtom` MUST be deleted once
  it has no remaining readers (Home is no longer a tab, so there is no
  home slot to convert). Confirm no other reader before removing.
- **REQ-REOPEN-3** — `handleWorkspaceClick` and `handleOpenInNewTab` MUST
  keep accepting the existing `RecentWorkspaceResponse` REST shape (no new
  `RecentWorkspace` atom type is introduced, since the live-list work is
  out of scope).

### Cross-cutting

- **REQ-CLEAN-1** — The net change across the in-scope issues MUST be
  net-negative on lines of code (excluding the spec and any new focused
  unit tests).
- **REQ-CLEAN-2** — No issue may be "fixed" by adding a new downstream
  workaround; each MUST be addressed at its source.
- **REQ-CLEAN-3** — `just format`, `just check`, and `just test-unit`
  MUST pass; affected integration tests MUST pass.

## Non-Goals

- Redesigning the New Workspace modal, the inline Home form, the Home
  page layout, or the tab system.
- Making the Home recent-workspaces list update live, changing how it
  fetches its data, or pushing that data over the websocket (see
  [Removed from scope](#removed-from-scope-formerly-issue-2)).
- Removing or altering the `list_recent_workspaces` /
  `/api/v1/workspaces/recent` REST endpoint or its `get_all_workspaces`
  data-model path; migrating any consumer (Home list,
  `ClosedWorkspacesPill`, `sculpt` CLI) off it.
- Changing the websocket/streaming payloads or transport.
- Changing what the user sees, except removing the two bugs in issues 8
  and 9 (a flicker fix and a reopen fix, not a redesign).
- Touching the `firstLoad`-style direct-to-`/home` navigation choices in
  the test harness beyond fixing their comments (the actions stay; only
  stale rationale is removed). Issue 1 is comment-only.
- Backfilling or migrating historical persisted state beyond stripping
  the known-dead `__new_workspace_*__` ids.
