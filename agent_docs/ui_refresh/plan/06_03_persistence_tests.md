# Task 6.3: Persistence/switch tests — adapter unit tests + PERSIST + SWITCH e2e

## Goal

Cover persistence and seamless switching: adapter-level tests for the per-workspace-
vs-global split and the no-migration rule, and the PERSIST/SWITCH end-to-end tests
(the e2e-observable parts; the `[perf]` bars are Task 9.1).

## Stories addressed

PERSIST-01 (per-workspace arrangement stored + isolated), PERSIST-03 (persists across
restart), PERSIST-04 (round-trip stability regression), PERSIST-05 (cross-workspace
isolation), SWITCH-03 (no spinner), SWITCH-04 (last view preserved). (PERSIST-02,
SWITCH-01/02/05, SEC-18 are `[perf]` → Task 9.1.)

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`. Run
via **`/run-integration-test`**; `just generate-api` after `ElementIDs` changes.
Frontend unit tests (Vitest) live next to source.

**The plan** (`e2e_test_plan.md` §1; `harness_migration.md` §3): persistence tests use
the existing `sculptor_instance_factory_` multi-instance (restart) fixture. The
**persistence adapter is a cheaper test surface** than full e2e for the
per-workspace-vs-global split (PERSIST-01/02) and the "old keys ignored, no migration"
rule — exercise the adapter directly where a full restart isn't needed.

**Test files** (`e2e_test_plan.md` §1):
- `test_layout_persistence.py` (PERSIST-01/03/05) — per-workspace independence of
  visibility/open/active; restart persistence; cross-workspace isolation. Uses the
  restart fixture.
- `test_layout_persistence_regression.py` (PERSIST-04) — **regression**: expand right
  section + add a terminal panel → navigate Home → back; the agent panel survives.
- `test_seamless_switch.py` (SWITCH-03/04) — no spinner (skeleton/stale-then-update);
  last-view preserved.

This task depends on **Tasks 6.1 (wiring + default), 6.2 (switch sequence)** and the
Phase-2..5 surfaces + POMs.

## Files to modify/create

- `sculptor/frontend/src/components/sections/persistence/LocalStorageLayoutAdapter.test.ts`
  — extend (from Task 1.2) with the per-workspace-vs-global split + no-migration
  (legacy keys ignored) cases.
- `sculptor/tests/integration/frontend/test_layout_persistence.py` — new.
- `sculptor/tests/integration/frontend/test_layout_persistence_regression.py` — new.
- `sculptor/tests/integration/frontend/test_seamless_switch.py` — new.

## Implementation details

1. **Adapter unit tests (Vitest):** writing a workspace snapshot does not affect the
   global snapshot or another workspace's snapshot; reading a legacy/old key returns
   nothing (no migration); `remove` clears only the targeted scope.
2. `test_layout_persistence.py` (PERSIST-01/03/05): arrange a workspace (collapse/
   expand sections, open/close panels, set active panel, reorder), restart via
   `sculptor_instance_factory_`, assert the same arrangement; assert a second
   workspace is unaffected by the first's changes.
3. `test_layout_persistence_regression.py` (PERSIST-04): expand the right section + add
   a terminal panel, navigate Home and back, assert the agent panel (and the added
   terminal) survive — no panel/agent disappears.
4. `test_seamless_switch.py` (SWITCH-03/04): switching workspaces shows **no spinner**
   (assert the skeleton/stale-then-update path, not a spinner element); re-entering a
   workspace preserves the last-active sub-section + active panels.
5. Skip **layout-property-only** assertions (`.sculptor/testing.md`); the zero-reflow
   / mount-count guarantees are `[perf]` (Task 9.1), not asserted here.

## Testing suggestions

- Run e2e via `/run-integration-test` (background + Monitor); unit via
  `just test-unit-frontend`.
- Use controlled FakeClaude where a streaming/agent state must be stable across the
  switch.

## Gotchas

- Use the restart fixture (`sculptor_instance_factory_`) for PERSIST-03/04.
- Don't assert reflow/mount counts here — those are `[perf]` (Task 9.1).
- The adapter-level tests are the right place for the split/no-migration rules
  (cheaper than full restart e2e).
- No spinner assertion = assert the skeleton/stale path is used, not a spinner widget.

## Verification checklist

- [ ] Adapter unit tests cover the per-workspace-vs-global split + no-migration.
- [ ] `test_layout_persistence.py` / `test_layout_persistence_regression.py` /
  `test_seamless_switch.py` pass via `/run-integration-test`.
- [ ] PERSIST-01/03/04/05 + SWITCH-03/04 covered; `[perf]` bars deferred to Task 9.1.
- [ ] `just test-unit-frontend` passes.
