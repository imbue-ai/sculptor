# Task 9.1: Perf tooling — switch profiler + measure-react-renders scenarios

## Goal

Stand up the non-functional verification: carry the workspace-switch profiler forward
and define the `measure-react-renders` scenarios that verify the `[perf]` stories
(zero layout-shift on switch, ≤1 mount per panel per switch, memoized re-renders
during drag/resize, global sizes in the first frame). These are a perf **checklist**,
not Playwright tests.

## Stories addressed

SWITCH-01 (`[perf]` zero layout-shift on switch), SWITCH-02 (`[perf]` ≤1 mount per
panel per switch), SWITCH-05 (`[unit]`/`[perf]` memoized re-renders during drag/
resize), SEC-18 (`[perf]` global sizes in the first frame), PERSIST-02 (`[perf]`
global sizes present + shared).

## Background

**Project:** Sculptor frontend (TS + React). We rewrote the workspace shell from
`agent_docs/ui_refresh/goals.md`. The non-functional acceptance bars are **not**
Playwright tests — they are verified with profiling/render-count tooling
(`user_stories.md` legend; `e2e_test_plan.md` "Perf coverage";
`harness_migration.md` §5).

**The tooling** (`harness_migration.md` §5; `design_extraction.md`):
- **Workspace-switch profiler** — `sculptor/frontend/src/common/perf/workspaceSwitchProfiler.ts`
  (`ws-switch.*` perf marks). It already exists on the `scu-1474` prototype and is
  **carried forward** into the rewrite (not net-new). It backs SWITCH-01 (zero
  layout-shift) and SEC-18/PERSIST-02 (global sizes in the first committed frame).
- **`measure-react-renders` skill** — compares render counts between `origin/main` and
  the branch for a user-defined scenario. It backs SWITCH-02 (≤1 mount per panel per
  switch) and SWITCH-05 (memoized re-renders during drag/resize).

**Scenarios to define** (`harness_migration.md` §5): "switch between two workspaces",
"drag a panel between sections", "resize the left section".

This is the final feature verification; it depends on **all prior phases** (the
interactions it measures must exist).

## Files to modify/create

- `sculptor/frontend/src/common/perf/workspaceSwitchProfiler.ts` — carry forward from
  `bryden/scu-1474-compact-workspace-layout` (`git show
  bryden/scu-1474-compact-workspace-layout:sculptor/frontend/src/common/perf/workspaceSwitchProfiler.ts`),
  renamed to `goals.md` vocabulary. Wire its `ws-switch.*` marks into the switch
  sequence (Task 6.2).
- `agent_docs/ui_refresh/plan/PERF_CHECKLIST.md` — new: the perf checklist (scenarios,
  how to run, the bars to confirm) so the human-run verification is repeatable.

## Implementation details

1. Carry forward `workspaceSwitchProfiler.ts`; instrument the Task 6.2 switch sequence
   so a switch emits the `ws-switch.*` marks. Confirm the marks show the
   sidebar/header/section-headers/frames present in the first committed frame with no
   second-pass resize (SWITCH-01) and global sizes already applied (SEC-18/PERSIST-02).
2. Define the three `measure-react-renders` scenarios (per the skill): switch between
   two workspaces (assert ≤1 mount per panel — SWITCH-02), drag a panel between
   sections (assert memoized boundaries hold — SWITCH-05), resize the left section
   (assert resize doesn't cascade into panel content — SWITCH-05).
3. Run the `measure-react-renders` skill for each scenario comparing `origin/main` vs.
   the branch; record the results in `PERF_CHECKLIST.md`. (Note: `origin/main` is the
   old shell, so the comparison is informational for the rewrite — the absolute bar is
   "≤1 mount per panel per switch" and "no re-render cascade," which the memo
   boundaries from Phase 2/Task 2.4 guarantee.)
4. Document the bars + how to re-run so this is a repeatable checklist, not a one-off.

## Testing suggestions

- This is **not** a pytest/Playwright task. Use the `measure-react-renders` skill +
  the profiler marks (e.g. via the Performance panel / the profiler's logging). Keep it
  as a perf checklist run at integration time (`harness_migration.md` §5
  recommendation).

## Gotchas

- These bars are **tooling, not e2e** — do not add `test_*.py` for them
  (`e2e_test_plan.md`: `[perf]` rows never get a `test_*.py`).
- The profiler is **carried forward**, not net-new — rename to `goals.md` vocab.
- The ≤1-mount and no-cascade bars depend on the memo boundaries (Task 2.4) + the
  identity cache (Task 1.6) — if a scenario fails, the fix is a missing memo/identity-
  cache boundary, not the profiler.

## Verification checklist

- [ ] `workspaceSwitchProfiler.ts` carried forward + wired into the switch sequence
  (`ws-switch.*` marks emit on switch).
- [ ] The three `measure-react-renders` scenarios defined and run; results recorded in
  `PERF_CHECKLIST.md`.
- [ ] SWITCH-01 (zero layout-shift), SWITCH-02 (≤1 mount/panel), SWITCH-05 (memoized
  drag/resize), SEC-18/PERSIST-02 (global sizes in the first frame) confirmed.
- [ ] No `test_*.py` added for the `[perf]` bars.
