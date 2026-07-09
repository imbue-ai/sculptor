# Workspace Grouping — Review

Reviewed at the head of `bryden/scu-1804-workspace-groups` (diff range
`origin/main...HEAD`, ~9k lines over 70 files) against [spec.md](./spec.md)
and [architecture.md](./architecture.md). The configured `/code-review-checklist`
skill ran over the full diff with the repo review docs applied; its findings
and their resolutions are recorded below.

## Summary

- The implementation delivers the spec across all five layers: backend entity
  + flag-gated API + streaming with same-transaction auto-dissolve, the
  `sculpt group` CLI family with auto-grouping, the stream-fed data layer with
  guarded optimistic mutations, the Dia-style sidebar UI, and the flat-lane
  projection drag-and-drop.
- All review findings were addressed in-branch except two acknowledged gaps,
  which are ticketed: SCU-1805 (dialog-fallback path of *New workspace in
  group* loses the group, REQ-MENU-3 partial) and SCU-1806 (no integration
  round-trip test for REQ-FLAG-3).
- Nothing blocking. Full gate (`just format` / `check` / `test-unit`) and the
  8 sidebar integration tests pass on the reviewed head.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-GROUP-1..9 | Covered | `sculptor/database/models.py`, `web/app.py` (flag-gated endpoints, auto-dissolve in-transaction), `common/state/mutations/workspaceGroups.ts` |
| REQ-UI-1..5 | Covered | `nav/WorkspaceGroupCard.tsx` + `.module.scss` (always-visible box, inset pills, app-accent selected row), `SidebarWorkspaceRow.tsx` |
| REQ-MENU-1..2, 4 | Covered | `WorkspaceGroupCard.tsx` (menu order, danger Ungroup, unlabeled circular swatches last), `contextActions/WorkspaceGroupingMenuItems.tsx` |
| REQ-MENU-3 | Partial | Direct-create path covered; dialog fallback loses the group → SCU-1805 |
| REQ-DND-1..7 | Covered | `nav/sidebarDropProjection.ts` (+450-line test), `SidebarRepoGroup.tsx` (re-render-only previews, geometric depth intent, optimistic commits with lane snapshot/restore) |
| REQ-CLI-1..4 | Covered | `tools/sculpt/sculpt/commands/group.py`, `_group_helpers.py`, `run.py`/`workspace.py` (grouping degrades instead of stranding, added this review) |
| REQ-FLAG-1..2, 4 | Covered | `config/user_config.py`, `SettingsPage.tsx`, flag-off menu gating integration test |
| REQ-FLAG-3 | Partial | Unit-level lane degradation covered; no disable→re-enable e2e test → SCU-1806 |

## User Scenarios

Every spec scenario has a working code path: create/add via row menu (integration-
tested), drag into/out of/within/between groups (integration-tested on the
keyboard path; pointer paths hand-verified in the QA harness with screenshots),
group menu management (integration-tested), collapse persistence
(`atomWithStorage`, not asserted across reload — noted under SCU-1806's
scope), CLI-born groups (respx-tested), deletion auto-dissolve
(integration-tested), and flag-off rendering (integration-tested).

## Test Coverage

- Added: `sidebarDropProjection.test.ts` (37 cases), `sidebarWorkspaceOrder.test.ts`
  (drop-commit/restore), `workspaceGroupComposition.test.ts`,
  `workspaceGroups.test.ts` (atoms + mutations incl. rollback version guards),
  migration version test, backend API tests, `sculpt` respx tests
  (`test_group.py`, `test_run.py`, `test_workspace.py`),
  `test_sidebar_groups.py` (4 integration tests).
- Suite status: `just test-unit` green; sidebar integration suite (8 tests) green.
- Nothing skipped/xfail.
- Known coverage gaps (accepted): the pointer-geometry depth intent
  (`BOX_EDGE_INSET_PX`, the fast-drag ejector) is exercised by hand via the QA
  harness rather than Playwright — scripted pointer drags can't reproduce
  tracked hand motion; the keyboard path covers the shared projection logic.

## Code Review Findings

Findings from `/code-review-checklist`, with resolutions:

1. **LOW / correctness** — group create stored whitespace-only names that
   rename rejects. **Resolved:** create now strips and falls back to the
   server-assigned default (`web/app.py`).
2. **MEDIUM / goal** — REQ-DND-1 spec text still demanded "no axis lock" after
   hand-testing reinstated the vertical lock. **Resolved:** spec text updated
   to the landed behavior.
3. **MEDIUM / goal** — REQ-MENU-3 dialog-fallback gap. **Ticketed:** SCU-1805.
4. **MEDIUM / tests** — REQ-FLAG-3 round trip untested. **Ticketed:** SCU-1806.
5. **MEDIUM / dead code** — `toggleBoundaryDepth`'s `pending` parameter became
   unreachable once every projection applied to the display. **Resolved:**
   parameter, dead branches, and the two tests asserting them removed.
6. **LOW / comments** — stale module header describing the retired
   transform-preview regime. **Resolved.**
7. **LOW / comments** — a real username in `mocks.html` example branch names.
   **Resolved:** replaced with `dev/…`.
8. **MEDIUM / error handling** — a grouping failure between workspace and
   agent creation aborted `sculpt run`, stranding an agent-less workspace
   whose id was never printed. **Resolved:** grouping now degrades to a loose
   workspace with a stderr warning (`_group_helpers.py::group_new_workspace_or_warn`),
   with regression tests for the create-failure and join-failure paths.
9. **MEDIUM / frontend** — the membership flip's rollback lacked a stream
   sync-version guard, so a lost response racing a WS frame could clobber
   server truth. **Resolved:** per-workspace stream write counters
   (`atoms/workspaces.ts::getWorkspaceSyncVersion`) now guard the rollback,
   mirroring the group mutations; covered by a mid-request-frame test.
10. **LOW / frontend** — the Add-to-group submenu dot used `--radius-full`,
    which renders square under non-"full" theme radius. **Resolved:** `50%`.
11. **MEDIUM / integration helpers** — `drag_workspace_into_group_via_keyboard`
    pressed on a lowered 2s timeout without confirming the previous press
    applied. **Resolved:** per-press confirmation via the shared drag
    snapshot. The snapshot itself was then narrowed to the dragged row's
    geometry only — the lit drop-target slot can flash before the lane
    re-render lands, and counting it confirmed presses early enough to
    overshoot (caught by the integration suite during this review).
12. **LOW / integration helpers** — the press-confirmation poll is a bounded
    manual loop rather than an `expect`-style wait. **Accepted:** the
    condition compares Playwright `bounding_box()` reads across presses,
    which has no locator predicate to `expect` on; the loop is bounded and
    fails loudly downstream.
13. **LOW / comments** — `REQ-*` ids referenced in code comments. **Accepted:**
    the ids resolve against the committed spec in this directory and the repo
    has standing precedent; the comments read standalone.

## Overall Assessment

Ready for PR. The riskiest surface — the drag grammar — is backed by a pure,
heavily-tested projection module, integration coverage of the keyboard path,
and hand verification of the pointer paths; the optimistic write paths now
carry version-guarded rollbacks on both the group and workspace stores.
Follow-ups are ticketed (SCU-1805, SCU-1806) rather than left implicit.
