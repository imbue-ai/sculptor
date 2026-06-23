# Task 8.3: Terminology rename pass (files / functions / @user_story / POM methods)

## Goal

Realign the suite's vocabulary to `goals.md` terms even where behavior is unchanged —
the mechanical rename of file names, test-function names, `@user_story` strings, and
POM method names — as **its own commit**, separate from behavioral changes, so review
can verify "rename only."

## Stories addressed

Vocabulary alignment only (`harness_migration.md` §4; `supplemental/naming_map.md`).
No behavior change.

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`. Run
via **`/run-integration-test`**.

**Project decision** (`harness_migration.md` §4; `e2e_test_plan.md` §5): every test
carrying old vocabulary is renamed to the new terms even when nothing else changes.
The canonical map is `supplemental/naming_map.md`; the test-facing rename rules:

| Old vocab | New vocab |
|---|---|
| zone / docking / top-right / bottom-right | section / sub-section |
| zen mode / focus mode | (removed) |
| `/btw` | (removed) |
| side toggle / bottom bar toggle | section collapse / expand |
| agent tab / file-browser tab / diff tab | panel / panel tab |
| add workspace page / `/ws/new` | new workspace dialog |
| top bar | sidebar / workspace header |
| focus (the active surface) | active section |

The per-diff "expand"/fullscreen toggle is **deprecated, not renamed** — there is no
diff-specific fullscreen; do **not** add an `expand → maximize` alias.

**Scope:** the subset of files already handled by Phases 7–8 (DELETE/REWRITE/UPDATE)
inherited their rename there; this task is the **RENAME-only remainder** — files whose
name or `@user_story` text still carry old vocab but whose behavior/assertions are
unchanged. The starting worklist (grep-derived, `harness_migration.md` §4): the old-
vocab files not already renamed, plus the `@user_story` strings in the FCC/agent tests
that say "tab" meaning a panel tab.

This task depends on **Phases 2–8** (so the rename targets the final surfaces).

## Files to modify/create

- Rename test files (`git mv`), test functions, `@user_story` strings, and POM method
  names across the suite per the map. No assertion or reach changes.

## Implementation details

1. **Re-grep before editing** (other in-flight branches move these files —
   `harness_migration.md` §4): build the current old-vocab worklist with a grep for
   `zone`, `docking`, `zen`, `focus`, `btw`, `side_toggle`, `top.?bar`, `add_workspace`,
   and `tab` (meaning a panel/agent/file tab) across `sculptor/tests/integration/` and
   `sculptor/sculptor/testing/`.
2. Apply the rename rules mechanically: `git mv` files; rename test functions; update
   `@user_story` strings to new vocab; rename POM methods (and their call sites).
   Where `naming_map.md` and the table disagree, **`naming_map.md` wins**.
3. Do **not** change behavior, assertions, or reach — this is rename-only.
4. Do **not** add an `expand → maximize` POM alias (the toggle is deprecated, Phase 7).
5. Run `just generate-api` only if a renamed POM touches an `ElementID` (most don't).

## Testing suggestions

- After the rename, run the full suite via `/run-integration-test` — it should be green
  with no behavior change (the rename is structural). A green run before and after
  (same set of passing tests) is the proof it was rename-only.
- Keep this as a **single commit** titled as a rename so review can verify the diff is
  mechanical.

## Gotchas

- **Re-grep first** — the worklist drifts as other branches move files.
- Rename-**only**: no assertion/reach/behavior changes in this commit.
- `naming_map.md` is the source of truth where the table is ambiguous.
- No `expand → maximize` alias.
- Update POM **call sites** when renaming POM methods, or imports break.

## Verification checklist

- [ ] All old-vocab file names / test functions / `@user_story` strings / POM methods
  renamed per `naming_map.md`.
- [ ] No behavior/assertion/reach changes; suite green before and after via
  `/run-integration-test`.
- [ ] Committed as a single "rename only" commit.
- [ ] `just check` passes.
