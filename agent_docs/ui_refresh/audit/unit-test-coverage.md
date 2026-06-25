# Side quest 1 — additional unit-test coverage

Goal: find non-e2e (vitest/pytest unit) coverage we can add cheaply for new
section-shell code, and implement the free wins.

## Method
Listed branch-added frontend modules (`git diff --diff-filter=A main...HEAD`)
with no `.test.ts(x)` sibling, then filtered to PURE logic / atoms (good unit
targets; React components are better left to the integration suite).

## Added this session (12 tests, all green)

| File | Covers | Why it's a win |
|---|---|---|
| `common/state/agentPanelPlacement.test.ts` | `ensureAgentPanelsPlacedAtom` | The new agent-auto-open atom (this session). Tests: places a new agent in center; appends only missing; no-op when all present (no persist churn); never moves an agent already in another section; **purely additive — keeps active panel/sub-section (no focus steal)**. Locks the "don't steal focus" invariant the code comment promises. |
| `components/sections/splitDirection.test.ts` | `splitDirectionLabel`, `splitDirectionOptionsForSection` | Pure split-direction rules (left/right→bottom, bottom→right, center→both). Cheap, exhaustive. |
| `components/newWorkspace/homePromptPrefill.test.ts` | `HOME_PROMPT_PREFILL` | Guards FIRST-04: the first-run prompt stays sourced from the built-in `/help` action so the two can't drift. |

Run: `pnpm exec vitest run src/common/state/agentPanelPlacement.test.ts src/components/sections/splitDirection.test.ts src/components/newWorkspace/homePromptPrefill.test.ts` → 12 passed.

## Further candidates (not yet done — judged lower value / higher effort)

Good next targets if you want more pure-logic coverage (no DOM needed):
- `components/sections/panelDndKeyboard.ts` — keyboard drag-and-drop move math; pure, worth testing reorder/cross-section logic.
- `components/sections/persistence/defaultLayout.ts` — the seeded default layout (files/changes/commits in left, terminal in bottom). A snapshot/shape test would lock SEC-02.
- `components/sections/addPanelCore.ts` — add-panel target resolution (agents → center; PANEL-06).
- `components/newWorkspace/newWorkspaceAtoms.ts` + `homePromptPrefill` siblings — new-workspace form state derivations.
- `common/perf/workspaceSwitchProfiler.ts` — milestone recording (opt-in guard, mark/measure bookkeeping) is pure enough to test with a fake `performance`.
- `components/sections/sectionActions.ts` already has a strong suite; the recently-added single-instance `withOpenPanel` expand-on-reveal branch could get one explicit case ("re-opening a placed panel in a collapsed section expands it").

Pure components (DiffViewer, SectionHeader, etc.) are exercised by the
integration suite; unit-testing them would mostly re-test React and isn't a
"free" win.

## Note
These additions are NOT a substitute for the integration coverage; they lock
specific invariants in new pure logic that's otherwise only covered end-to-end.
