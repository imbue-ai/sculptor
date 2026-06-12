# Task 1.2: Gate substrate — the five missing narrow atoms + hooks

## Goal

Give every target capability flag a single, narrow frontend read path:
add the five missing Jotai atom families and hook wrappers —
ContextReset, Compaction, BackgroundTasks, SessionResume,
ToolUseRendering — in the established `taskSupports<X>` pattern.

## Requirements addressed

REQ-BASE-4.

## Background

Sculptor's frontend gates per-harness affordances on
`task.harnessCapabilities`, a generated twin of the backend
`HarnessCapabilities` model
(`sculptor/sculptor/interfaces/agents/harness.py:51-81`, computed onto
the task view at `sculptor/sculptor/web/derived.py:378-381`). The
FOLLOWUPS-9 discipline: components never read
`.harnessCapabilities.<field>` directly — each flag has exactly one
narrow atom family in
`sculptor/frontend/src/common/state/atoms/tasks.ts:107-137` and one hook
in `sculptor/frontend/src/common/state/hooks/useTaskHelpers.ts:33-62`;
consumers apply `?? true` (load-race optimism, retained deliberately).

Existing pattern to copy exactly — atom
(`tasks.ts:131-133`): `taskSupportsInterruptionAtomFamily` =
`atomFamily<string, Atom<boolean | undefined>>` reading
`get(taskAtomFamily(taskId))?.harnessCapabilities.supportsInterruption`;
hook (`useTaskHelpers.ts:57-58`): `useTaskSupportsInterruption(taskId)`
returning the atom's value.

Task 1.1 (same phase, lands first) split the capability model: the twin
now carries `supportsContextReset` alongside `supportsCompaction` (both
False for pi, True for Claude). Flags currently lacking any atom/hook:
`supportsContextReset` (new), `supportsCompaction`,
`supportsBackgroundTasks`, `supportsSessionResume`,
`supportsToolUseRendering`. Without these, later capability tranches have
no gate to wire (the `/clear` entry, compaction chrome, etc. are
currently ungated chrome or backend-only drops).

## Files to modify/create

- `sculptor/frontend/src/common/state/atoms/tasks.ts` — five new atom
  families appended to the existing `taskSupports*` block (107-137),
  same shape and naming: `taskSupportsContextResetAtomFamily`,
  `taskSupportsCompactionAtomFamily`,
  `taskSupportsBackgroundTasksAtomFamily`,
  `taskSupportsSessionResumeAtomFamily`,
  `taskSupportsToolUseRenderingAtomFamily`.
- `sculptor/frontend/src/common/state/hooks/useTaskHelpers.ts` — five
  matching `useTaskSupports<X>` hooks beside the existing eight (33-62).
- `sculptor/frontend/src/common/state/atoms/tasks.test.ts` — unit
  coverage for the new atoms following the existing capability-atom test
  pattern (see the `supportsInteractiveBackchannel` flip test around
  line 235: build a task fixture, override one capability, assert the
  atom's value).

## Implementation details

1. Append the five atom families to `tasks.ts`, exactly mirroring
   `taskSupportsInterruptionAtomFamily` (131-133): keyed by `taskId`,
   `Atom<boolean | undefined>`, optional-chained read of the precise twin
   field name. The twin field names are camelCase mirrors of the model:
   `supportsContextReset`, `supportsCompaction`,
   `supportsBackgroundTasks`, `supportsSessionResume`,
   `supportsToolUseRendering` (typo ⇒ compile error, thanks to Task 1.1).
2. Add the five hooks to `useTaskHelpers.ts`, one-liners mirroring
   `useTaskSupportsInterruption` (57-58).
3. No consumer changes in this task: Task 1.3 migrates surfaces onto
   these gates; capability tranches wire behavior later. (Dead code is
   acceptable for one task's lifetime within the same phase/MR.)
4. Extend `tasks.test.ts`: for each new atom, a fixture-driven test
   asserting the value tracks the capability field (both True and False)
   and is `undefined` when the task is absent.

## Testing suggestions

- `tasks.test.ts` is the unit surface (vitest; run the frontend unit
  suite per the justfile).
- Integration tests exercising the atom plumbing indirectly (must stay
  green): `tests/integration/frontend/test_pi_capability_gating.py`
  (existing five tests), `tests/integration/frontend/test_pi_basic.py`.
  New gate-state coverage for the five flags arrives in Task 1.6 after
  Task 1.3 gives them surfaces/ElementIDs.

## Gotchas

- Match naming EXACTLY (`taskSupports<X>AtomFamily` / `useTaskSupports<X>`)
  — Task 1.6's tests and pass-2 task files reference these names sight
  unseen.
- Return `boolean | undefined` (not defaulted) from atoms/hooks — the
  `?? true` belongs to consumers (existing convention; see
  `ChatInput.tsx:149-156` comments explaining the load-race rationale).
- Don't be tempted to add a `supportsFastMode`-style consumer cleanup
  here; this task is append-only substrate.

## Verification checklist

- [ ] All five atoms + hooks exist, named per the pattern, reading the
      exact twin fields.
- [ ] `tasks.test.ts` covers each new atom (true/false/undefined task).
- [ ] No component/consumer diffs in this task (atoms/hooks + tests only).
- [ ] Integration tests:
      `tests/integration/frontend/test_pi_capability_gating.py`,
      `tests/integration/frontend/test_pi_basic.py` pass unchanged.
