# Task 3.6d: test_changes_panel.py — Changes panel (migrate changes/scope/discard)

## Goal

Build `test_changes_panel.py` — the Changes panel's changes browser + scope picker
(All/Uncommitted), discard, and commit-from-changes, each with its own embedded
viewer — migrating the proven assertions **unchanged** via the 3.6a POMs + seed
fixture. Delete this slice's migrated sources after it runs green.

## Stories addressed

FCC-01 (Changes is a separate panel), FCC-03 (its sidebar is the changes browser),
FCC-02 (its own viewer); changes-specific behavior (scope picker, discard,
commit-from-changes, target branch).

## Background

**Project:** Sculptor integration tests; run via `/run-integration-test`. Content is
**migrated, not rewritten** (`e2e_test_plan.md` §1/§4e). Open the Changes panel via
the 3.6a open-a-panel helper (clicks the add-panel dropdown); drive the `ExplorerLayout`
+ `DiffViewer` POMs. FakeClaude drives the file writes / commits these tests need.

Depends on **Task 3.6a** (POMs + open-a-panel helper). Not on 6.1.

## Migration sources (delete after green)

`test_file_browser_uncommitted.py`, `test_diff_scope_switching.py`,
`test_commit_from_changes_tab.py`, `test_discard_file.py`,
`test_discard_preserves_all_tab.py`, `test_target_branch.py`.

## Files to modify/create

- `sculptor/tests/integration/frontend/test_changes_panel.py` — new (migrated content).
- Remove the migration sources listed above once their assertions land.

## Implementation details

1. Open Changes via the 3.6a helper (add-panel dropdown); assert the changes list + scope picker
   (All / Uncommitted), discard-file, and commit-from-changes (clears after commit).
2. Preserve target-branch behavior.
3. Move assertions across **unchanged**; skip purely-visual assertions.

## Gotchas

- Each panel embeds **its own** viewer instance — no shared global active-diff.
- **Per-slice deletion:** remove **only** this slice's sources, after green.
- `test_diff_scope_switching.py` belongs here (the scope picker is a Changes feature),
  not in 3.6b's diff-viewer slice.

## Verification checklist

- [ ] `test_changes_panel.py` passes via `/run-integration-test`.
- [ ] All listed sources removed; nothing else.
- [ ] Scope picker / discard / commit-from-changes / target branch covered; no
  layout-only visual assertions.
