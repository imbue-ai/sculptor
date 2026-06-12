# Task 11.1: Background tasks — execute the deferral (`supports_background_tasks` stays False)

## Goal

Resolve REQ-CAP-BACKGROUND-TASKS **by deferral**, per the feasibility
verdict **(iv) blocked on pi-core** (`feasibility.md` §11): pi 0.78.0
deliberately has no background-execution primitive and no lifecycle
event vocabulary; the only extension path is a bespoke simulation with
no native signal, against a Sculptor affordance that is itself thin.
This task verifies the deferral invariants and closes the loop — it is
expected to require **no code change and no MR**.

## Requirements addressed

REQ-CAP-BACKGROUND-TASKS (resolved-by-deferral); REQ-CAP-ALL-4 (no
fail-open, no dead affordance); REQ-CAP-ALL-6 (deferral via verdict
(iv)); REQ-PROC-7 (FOLLOWUPS handoff).

## Background

Claude's background tasks surface via
`BackgroundTaskStartedAgentMessage` / `BackgroundTaskNotificationAgentMessage`
and the task view's `pending_background_task_ids`
(`sculptor/sculptor/web/derived.py` ~745). pi emits nothing comparable
(`<pi-pkg>/docs/usage.md:286`: "intentionally does not include …
background bash"; the RPC §5 event union has no background vocabulary).

The base tranche (PR #54) already left this capability in the correct
deferred state: `supports_background_tasks=False` on `PiHarness`
(`agents/pi_agent/harness.py`); a narrow atom/hook exists
(`taskSupportsBackgroundTasksAtomFamily`, `tasks.ts:147`;
`useTaskSupportsBackgroundTasks`) for any future gate; there is **no
frontend affordance to suppress** (no background chrome renders for a
harness that never emits the messages — nothing fails open, nothing
renders dead). The FOLLOWUPS handoff already happened: task 0's MR
(PR #53) description carries the ready-to-curate **"Proposed FOLLOWUPS
entry"** for this deferral (problem statement + evidence + revisit
condition: "revisit only if pi-core adds a background-execution
primitive" — explicitly NOT expected from a version bump).

## Files to modify/create

None expected. This phase exists so the cycle's bookkeeping is honest:
every REQ-CAP must be **resolved** (flipped or deferred-with-record)
before cycle close (REQ-PROC-9), and this file is the record that the
deferral was deliberate, verified, and architect-visible — not an
oversight.

## Implementation details (verification, not construction)

1. Confirm the flag stance: `supports_background_tasks=False` in
   `PiHarness.capabilities()` with a comment pointing at
   `feasibility.md` §11 (add the pointer comment if absent — that would
   be the one permissible one-line diff, rolled into any open
   capability tranche rather than its own MR).
2. Confirm no-dead-affordance: in a pi workspace, no background-task
   chrome renders and nothing background-related is clickable
   (covered today by the absence of the emitting messages; spot-check
   via the existing fake_pi integration suite rather than new tests).
3. Confirm the FOLLOWUPS handoff: the Proposed-FOLLOWUPS block exists in
   PR #53's description; the architect (curator of FOLLOWUPS.md on
   `danver/pi-spec`) has it available. If the architect has not yet
   curated it, surface a reminder — do not write to `danver/pi-spec`
   yourself.
4. Record resolution at cycle close: when the cycle agent assembles the
   final state (REQ-PROC-9), REQ-CAP-BACKGROUND-TASKS is marked
   **resolved by deferral**, citing `feasibility.md` §11 — which already
   reflects final reality (no amendment needed unless something above
   surprised you; a surprise here is a REQ-INV-6 pause-and-ask).

## Testing suggestions

- No new tests. The existing suites already pin the deferred state
  (nothing renders; the harness stance tests assert `False`).

## Gotchas

- Do NOT build the bespoke simulation "while we're here" — the verdict
  explicitly judged it not worth a tranche this cycle; resurrecting it
  is a goals-level decision for a future cycle via the FOLLOWUPS entry.
- Do NOT remove the substrate atom/hook — unused-but-present is the
  intended state (the gate exists for the day the verdict changes).
- If any future tranche accidentally flips this flag (e.g. a careless
  all-True fixture copied into `PiHarness`), the stance tests catch it —
  keep them asserting `False`.

## Verification checklist

- [ ] `supports_background_tasks=False` stance confirmed (with the
      feasibility pointer comment present or added via an open tranche).
- [ ] No background-task affordance renders in a pi workspace (existing
      suites green — no fail-open, no dead affordance).
- [ ] Proposed-FOLLOWUPS block confirmed in PR #53's description and
      visible to the architect.
- [ ] Cycle-close bookkeeping (REQ-PROC-9) lists this REQ-CAP as
      resolved-by-deferral citing `feasibility.md` §11.
