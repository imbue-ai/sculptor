# Task 3.6e: test_commits_panel.py — Commits panel (migrate history)

## Goal

Build `test_commits_panel.py` — the Commits panel's commit history list (graph dots,
rows, popover, metadata) + commit-scoped diffs in its own embedded viewer —
migrating the proven history assertions **unchanged** via the 3.6a POMs + seed
fixture. Delete this slice's migrated sources after it runs green.

## Stories addressed

FCC-01 (Commits is a separate panel), FCC-03 (its sidebar is the commit history),
FCC-02 (commit-scoped viewer).

## Background

**Project:** Sculptor integration tests; run via `/run-integration-test`. Content is
**migrated, not rewritten** (`e2e_test_plan.md` §1/§4e). Open the Commits panel via
the 3.6a open-a-panel helper (clicks the add-panel dropdown); drive the `ExplorerLayout`
+ `DiffViewer` POMs.

Depends on **Task 3.6a** (POMs + open-a-panel helper). Not on 6.1.

## Migration sources (delete after green)

`test_history_panel.py`, `test_history_panel_diffs.py`.

## Files to modify/create

- `sculptor/tests/integration/frontend/test_commits_panel.py` — new (migrated content).
- Remove the migration sources listed above once their assertions land.

## Implementation details

1. Open Commits via the 3.6a helper (add-panel dropdown); assert the commit graph (dots: gray /
   green = HEAD / amber-ring = uncommitted), rows, popover, metadata.
2. Commit-scoped diffs render in the panel's own `DiffViewer`.
3. Move assertions across **unchanged**; skip purely-visual assertions.

## Gotchas

- **Per-slice deletion:** remove **only** this slice's sources, after green — this is
  the last FCC slice, so confirm no FCC source `test_*` remains anywhere.
- Commit graph visuals are screenshot-verified, not asserted as layout properties.

## Verification checklist

- [ ] `test_commits_panel.py` passes via `/run-integration-test`.
- [ ] Both listed sources removed; no FCC migration source left in the suite.
- [ ] Commit list + popover + commit-scoped diffs covered; no layout-only visual
  assertions.
