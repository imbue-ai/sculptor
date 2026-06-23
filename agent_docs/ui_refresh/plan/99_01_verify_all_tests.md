# Task 99.1: Run all tests added in this plan and iterate to green

## Goal

Run every test introduced or modified by this plan and iterate until they all pass.
This is a safety check after all the per-task work — even though each task verified
its own scope, this task verifies them as a whole.

## Background

This is the second-to-last task in the plan. By now every feature task has been
completed and committed: the new section/panel shell, the panels, the interactions,
workspace creation, persistence/switching, the deprecated-feature removals, the legacy
test migration, the rename pass, and the perf tooling. Per-task verification has
already passed, but cross-task interactions may have introduced regressions.

The plan touched a very large surface (the whole workspace frontend + ~207 integration
files), so this whole-suite pass matters more than usual.

## Files to modify/create

None expected. If you find a failure, fix it in the source file the failure
originates from.

## Implementation details

1. Determine which tests were added/modified in this plan. Either:
   - Read each task file's *Testing suggestions* / *Verification checklist* and gather
     the test names; or
   - Run `git diff --stat origin/main...HEAD` filtered to test paths
     (`sculptor/tests/integration/frontend/` for integration; `*.test.ts` /
     `*_test.py` next to source for unit, per `.sculptor/testing.md`).
2. Run the unit tests with `just test-unit` (or `just test-unit-frontend` /
   `just test-unit-backend` to scope). Fix failures; iterate until green.
3. Run the integration tests via the **`/run-integration-test`** skill (NOT `pytest`
   directly), as background processes with a Monitor watchdog. Iterate until green. Use
   `/debug-integration-test` for diagnosis. Behaviors that depend on **real Claude**
   are verified against real Claude (`/auto-qa-changes`), not `fake_claude`
   (`.sculptor/testing.md`).
4. Run the full pre-commit verification one final time per `.sculptor/code.md`:
   `just format`, then `just check` (lint + types + ratchets), then `just test-unit`.
   Also confirm `just generate-api` has been run if any `ElementIDs` changed and the
   generated TS is committed.
5. **No pre-existing failures:** if any check or test fails, fix it before committing —
   even if you believe it predates your changes. All failures are your responsibility
   (`implement_task.md` → "No pre-existing failures").

## Verification checklist

- [ ] Every unit test added in this plan passes (`just test-unit`).
- [ ] Every integration test added/migrated in this plan passes via
  `/run-integration-test`.
- [ ] The full pre-commit verification passes (`just format`, `just check`,
  `just test-unit`); `just ratchets` is clean; generated API types are up to date.

## Commit policy

**Do NOT make an empty commit.** If you didn't have to change anything (everything
passed first try), report success without a commit. If you fixed regressions, commit
those fixes with a descriptive message ending with the trailer:

```
Co-authored-by: Sculptor <sculptor@imbue.com>
```
