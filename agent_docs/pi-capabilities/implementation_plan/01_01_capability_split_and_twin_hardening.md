# Task 1.1: Capability split + twin hardening (typo ⇒ compile error)

## Goal

Split `supports_compaction` into `supports_context_reset` (the `/clear`
reset path) + `supports_compaction` (auto-compaction chrome) across the
backend model, every constructor site, and the generated TypeScript twin —
and make a mistyped capability field read a **compile-time error**
(verified with a type-level negative test; ratchet fallback if
verification fails).

## Requirements addressed

REQ-BASE-2, REQ-BASE-3, REQ-BASE-7 (no Claude-visible change).

## Background

Sculptor gates per-harness affordances on a typed capability object.
`HarnessCapabilities` (`sculptor/sculptor/interfaces/agents/harness.py:51-81`)
is a pydantic `SerializableModel` of 12 bools with **no field defaults** —
deliberately, so every constructor must take an explicit stance per flag
and `grep <field>` finds every harness's stance. It reaches the frontend
via a computed field on the task view
(`sculptor/sculptor/web/derived.py:378-381`) and a **generated** TS twin
(`sculptor/frontend/src/api` is gitignored; regenerate with
`just generate-api`). Frontend reads go through narrow Jotai atom families
(`sculptor/frontend/src/common/state/atoms/tasks.ts:107-137`) and hook
wrappers (`sculptor/frontend/src/common/state/hooks/useTaskHelpers.ts:33-62`).

Why the split: pi-basic filed BOTH the `/clear` pseudo-skill and the
auto-compaction chrome under `supports_compaction`, but they are different
mechanisms — `/clear` discards the session (Claude path:
`process_clear_context_message`,
`sculptor/sculptor/agents/default/claude_code_sdk/process_manager.py:244`),
while compaction summarizes in place at a threshold
(`AutoCompactingAgentMessage` → `is_auto_compacting`,
`sculptor/sculptor/web/derived.py:278`). They also have different pi
feasibility (pi exposes `new_session` vs compaction events — see
`agent_docs/pi-basic/pi-0.78.0-rpc.md` §4/§5). The strict
flip rule (REQ-CAP-ALL-1) punishes the conflation.

Why the hardening: FOLLOWUPS-9 — a typo'd capability read once
type-checked and the consumer's `?? true` default made the gate fail
OPEN (an affordance showed for pi that should have been hidden). The
`?? true` load-race default is **deliberately retained** (decided in the
requirements Q&A); the fix is to make typos impossible at compile time.

Capability stances live at: base all-False body
(`interfaces/agents/harness.py:116-129`), Claude all-True
(`sculptor/sculptor/agents/default/claude_code_sdk/harness.py`,
`capabilities()` override), pi
(`sculptor/sculptor/agents/pi_agent/harness.py:54-72`, only
`supports_file_references=True`).

## Files to modify/create

- `sculptor/sculptor/interfaces/agents/harness.py` — add
  `supports_context_reset: bool` to the model (place beside
  `supports_compaction`); add the explicit `False` to the base
  `capabilities()` body; update the class docstring's conflation-relevant
  wording.
- `sculptor/sculptor/agents/default/claude_code_sdk/harness.py` — Claude
  advertises `supports_context_reset=True` (and keeps
  `supports_compaction=True`).
- `sculptor/sculptor/agents/pi_agent/harness.py` — pi advertises both
  `False`; extend the inline comments to note `/clear` now gates on
  context_reset.
- Python fixture/test constructor sites (every one must add the new
  field — pydantic forces this):
  `sculptor/sculptor/agents/default/claude_code_sdk/harness_test.py`,
  `sculptor/sculptor/agents/pi_agent/harness_test.py`,
  `sculptor/sculptor/web/derived_task_status_test.py`.
- TS fixture sites (after regeneration the twin gains the field; fixtures
  hand-build the object):
  `sculptor/frontend/src/common/state/atoms/tasks.test.ts` (objects at
  lines 29, 130, 154, 179, 211, 235),
  `sculptor/frontend/src/stories/custom/WorkspacePeekPopover.stories.tsx:74`.
- Comment-only retargeting: `sculptor/frontend/src/pages/workspace/components/ChatInput.tsx:186`
  (the `/clear` CAPABILITY-GAP marker names `supportsCompaction`; retarget
  to `supportsContextReset`); `sculptor/sculptor/agents/pi_agent/agent_wrapper.py:154-158`
  (the drop-list comment: `ClearContextUserMessage` moves under
  `supports_context_reset`); `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py:500`
  (same retarget). `StatusPill.tsx:34` and `TokenPopoverContent.tsx:30`
  markers stay `supportsCompaction` (genuinely compaction chrome).
- **Create** a type-level negative test in the frontend (e.g. a small
  `*.test-d.ts`-style or vitest-compiled file under
  `sculptor/frontend/src/common/state/` near `tasks.test.ts`): an access
  to a nonexistent capability key (e.g. the historical `canRenderSkills`)
  annotated so compilation FAILS if the access type-checks (use the
  established `@ts-expect-error` idiom: the directive errors when the
  marked line stops erroring).
- **Fallback only:** if the twin proves to have an index signature (or
  regeneration reintroduces one) so the negative test cannot work, add a
  ratchet rule instead forbidding `.harnessCapabilities.<field>` member
  access outside `sculptor/frontend/src/common/state/atoms/tasks.ts` —
  follow the `writing-ratchet-tests` skill and the existing rules under
  `ratchets/`. Record which path was taken in the MR description.

## Implementation details

1. Add the field to the pydantic model; update the base, Claude, and pi
   `capabilities()` bodies. Keep field ordering tidy (beside
   `supports_compaction`) — the twin's field order follows the model.
2. Fix every Python constructor site the validation error surfaces
   (`grep -rn "supports_file_references" --include='*.py' sculptor/` is
   the complete site list).
3. Run `just generate-api` to regenerate the twin and any ElementID/type
   artifacts; fix the TS fixture sites the compiler surfaces.
4. Inspect the regenerated twin type for `HarnessCapabilities` in
   `sculptor/frontend/src/api/` (gitignored — inspect locally): confirm
   no index signature swallows unknown keys.
5. Write the type-level negative test against the `~/api` import path the
   atoms use (`tasks.ts:107-137` imports the task type whose
   `harnessCapabilities` field carries the twin).
6. If (4) fails: implement the ratchet fallback as described above.
7. Update the comment-only sites listed above.

## Testing suggestions

- Backend: extend `sculptor/sculptor/agents/pi_agent/harness_test.py` and
  `.../claude_code_sdk/harness_test.py` stance assertions to cover both
  split flags (pi False/False; Claude True/True).
- Frontend: `tasks.test.ts` keeps passing after fixture updates; the new
  negative test fails compilation when its `@ts-expect-error` line stops
  erroring.
- Integration tests exercising the touched paths (must stay green,
  Claude-side unchanged):
  `tests/integration/frontend/test_pi_capability_gating.py` (all),
  `tests/integration/frontend/test_minimum_interface_conformance.py`,
  `tests/integration/frontend/test_pi_basic.py`.

## Gotchas

- **No behavioral gating changes in this task** — `/clear` is NOT yet
  gated for pi here (that's the phase-04 capability tranche; the flag is
  False either way). This task only reshapes the model + hardens reads.
- The no-defaults policy is the feature, not a bug: do NOT add a default
  for the new field to "reduce churn" — the forced edits are the
  grep-complete guarantee.
- `sculptor/frontend/src/api` is **gitignored**: never commit generated
  files; CI regenerates. The negative test must live OUTSIDE the
  generated tree.
- Wire compat: the new field is additive; old clients ignore it. Note in
  the MR that the forward-compat question from requirements Open Q4 was
  checked (this is the verification REQ-BASE-2 asks for).
- The frontend worktree needs `node_modules` (`just rebuild` on a fresh
  worktree) before `just generate-api`/`just check` run.

## Verification checklist

- [ ] `grep -rn supports_context_reset` shows: model field, base False,
      Claude True, pi False, and every fixture site updated — no site
      missing.
- [ ] Deliberately typo a capability read locally (e.g.
      `.harnessCapabilities.supportsSkillz`) → `just check` FAILS;
      revert. The committed negative test encodes this permanently.
- [ ] If the ratchet fallback was taken: the ratchet fires on a direct
      read outside `tasks.ts` and `just ratchets` is green on the real
      tree; MR records the fallback decision.
- [ ] Claude UX unchanged: no Claude-side capability value changed except
      gaining `supports_context_reset=True` (which gates nothing for
      Claude — all its surfaces already render).
- [ ] Integration tests:
      `tests/integration/frontend/test_pi_capability_gating.py`,
      `test_minimum_interface_conformance.py`, `test_pi_basic.py` pass.
