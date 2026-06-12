# Task 4.1: Context reset — `/clear` works for pi (`supports_context_reset`)

## Goal

`/clear` genuinely resets a pi conversation (the next turn demonstrably
lacks prior content), acknowledged in the UI the way Claude's clear is —
and `supports_context_reset` flips `True`. Feasibility verdict **(i)
Sculptor-side only** (`feasibility.md` §4): `new_session` clears history
in-process (`messageCount` 2→0, recall provably gone), preserving model
and thinking-level selections; no process restart needed.

## Requirements addressed

REQ-CAP-CONTEXT-RESET; REQ-CAP-ALL-1..7; REQ-TEST-1/2/4.

## Background

`/clear` is a frontend pseudo-skill (`pseudoSkills.ts`) executed in
`ChatInput.executePseudoSkill` → `clearWorkspaceAgentContext` → the
backend endpoint `clear_workspace_agent_context`
(`sculptor/sculptor/web/app.py`, the `/clear_context` route ~line 2145):
it persists a `ClearContextUserMessage` under
`await_message_response(message_id, ...)` — the HTTP response resolves
when the agent emits the terminal Request message for that
`message_id`. Claude's handler restarts its CLI session
(`process_clear_context_message`,
`claude_code_sdk/process_manager.py:244`).

The base tranche (PR #54) landed:

- `supports_context_reset` as a separate flag (split from
  `supports_compaction`), `False` for pi; narrow atom/hook
  (`taskSupportsContextResetAtomFamily`, `tasks.ts:139`;
  `useTaskSupportsContextReset`, `useTaskHelpers.ts`).
- Client-side refusal: under a non-supporting harness, typing `/clear`
  shows a toast with `CAPABILITY_UNSUPPORTED_COPY`
  (`ChatInput.tsx:209`) and never calls the endpoint; the gating test
  `test_clear_pseudo_skill_gated_on_context_reset`
  (`test_pi_capability_gating.py:219`) pins both sides.
- Dead-letter: `ClearContextUserMessage` is in
  `_DEAD_LETTER_MESSAGE_TYPES` (`agent_wrapper.py` ~106) — error-logged
  and dropped. This task replaces the drop.
- Typed protocol: `parse_rpc_message`; `RpcResponse` envelopes correlate
  by `id` (`_handle_response_event`).

Wire facts (`feasibility.md` §4): `{"type":"new_session"}` →
`{"command":"new_session","success":true,"data":{"cancelled":false}}`;
`sessionId` changes; history empties; `thinkingLevel`/model preserved.
Sculptor issues it between turns (its `/clear` is a between-turns
action). An extension's `session_before_switch` may cancel
(`cancelled:true`) — no extensions are loaded yet this cycle unless the
backchannel tranche has landed; handle `cancelled` defensively as a
failed clear.

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — remove
  `ClearContextUserMessage` from `_DEAD_LETTER_MESSAGE_TYPES` (and its
  comment row); handle it: enqueue/dispatch so it runs between turns
  through `_handle_user_message(message)` (emitting
  RequestStarted/Success for the message id — that resolves the
  endpoint's `await_message_response`), send `new_session`
  (id-correlated), wait for its `response`, treat `success:false` or
  `data.cancelled:true` as a failed request (the wrapper's error path
  produces the failure message). Simplest shape: route it through the
  existing `_input_agent_messages` queue so ordering with chat turns is
  free, branching on message type in `_process_message_queue`.
- `sculptor/sculptor/web/app.py` — add the capability guard to the
  clear-context endpoint mirroring the plan-mode precedent at ~2078:
  resolve the harness via `get_harness_for_config(task.input_data.agent_config)`
  and 400 when `not harness.capabilities().supports_context_reset`
  (defense-in-depth for future harnesses; passes for both Claude and pi
  once flipped).
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_context_reset=True`; update the stance comment.
- `sculptor/sculptor/agents/pi_agent/harness_test.py` — stances.
- `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py` — unit
  coverage (see Testing).
- `sculptor/sculptor/testing/fake_pi.py` — handle `new_session`:
  respond `{"command":"new_session","success":true,"data":{"cancelled":false}}`
  and reset any session-ish internal state (so a directive-driven recall
  test can prove the reset).
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  flip the pi branch of `test_clear_pseudo_skill_gated_on_context_reset`:
  `/clear` under pi now CALLS the endpoint and succeeds (no refusal
  toast).
- **Create** `sculptor/tests/integration/real_pi/test_clear_context.py` —
  mirror `real_claude/test_clear_context.py`: plant a sentinel in turn 1,
  `/clear`, then ask for it — assert the agent does NOT recall it.

## Implementation details

1. Ordering: a clear arriving mid-turn must not race the in-flight
   stream. Queue-based handling gives between-turns semantics for free;
   document the choice in the handler docstring.
2. The endpoint's waiter resolves on the terminal Request message — make
   sure the success path emits it exactly once (the
   `_handle_user_message` context manager already does, on clean exit).
3. UX parity: check what Claude's clear shows in the chat (the frontend
   handles the endpoint response; Claude's agent messages around clear
   are minimal). Match whatever the frontend renders for Claude today —
   no bespoke pi chrome.
4. Keep the client-side gate logic untouched — flipping the flag
   activates the live path; the refusal branch remains for genuinely
   unsupporting harnesses.

## Testing suggestions

- Unit (`agent_wrapper_test.py`): ClearContext → `new_session` written to
  stdin; success resolves the request; `success:false` and
  `cancelled:true` produce the failure path; clear queued behind an
  in-flight turn executes after it.
- Integration (fake_pi): `/clear` in a pi workspace round-trips (toast-
  free), and a scripted recall before/after proves the conversation
  restarts; the flipped gating test; Claude-side clear unaffected.
- Real: new `real_pi/test_clear_context.py`; full `just test-real-pi`
  green at merge.

## Gotchas

- `await_message_response` has a timeout (the frontend passes
  `wsTimeout: 30000` — `ChatInput.tsx` clear call); the handler must
  resolve promptly even when a long turn is in flight, or the UI shows a
  spurious failure. If a turn is streaming, the honest options are
  reject-fast or queue-and-resolve-after — pick one deliberately,
  match the frontend timeout budget, and unit-test it.
- `new_session` preserves model/thinking — do NOT re-send model setup
  after a clear.
- The session-resume tranche (phase 06) persists pi's `sessionId`;
  `new_session` CHANGES the id. If 06 has landed first, update the
  persisted id after a successful clear (and if this lands first, leave a
  pointer comment for 06). The two compose (`feasibility.md` §3) but the
  id handoff is where they touch.
- Tranche conventions: own workspace on
  `danver/pi-capabilities-context-reset` rooted at current `origin/main`
  (≥ `99cbc0d`), MR → `main`; `just rebuild` first; commit rules
  (`just format`/`check`/`test-unit`, trailer
  `Co-authored-by: Sculptor <sculptor@imbue.com>`); integration tests via
  the repo's integration-test skill; evidence bundle in the MR
  (deterministic gates, FULL `just test-real-pi`, real-claude rerun — ask
  Danver if prerequisites are missing; ticked checklist); PR
  world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack; pause for Danver before any deferral (REQ-INV-6).

## Verification checklist

- [ ] `/clear` in a pi workspace resets context (sentinel unrecallable)
      and resolves in the UI like Claude's clear.
- [ ] Endpoint guard 400s for a non-supporting harness; passes for
      Claude and pi.
- [ ] Failure paths (success:false / cancelled:true / timeout budget)
      unit-covered.
- [ ] `supports_context_reset=True`; stance tests updated; the gating
      test's pi branch flipped; stale CAPABILITY-GAP markers for the
      clear path removed.
- [ ] Integration tests: flipped `test_pi_capability_gating.py`,
      `test_pi_basic.py`, `test_minimum_interface_conformance.py`; new
      `real_pi/test_clear_context.py`; full `real_pi/` green at merge.
