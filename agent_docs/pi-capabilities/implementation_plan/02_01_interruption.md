# Task 2.1: Interruption — Stop works for pi (`supports_interruption`)

## Goal

The Stop affordance halts an in-flight pi turn promptly, the agent stays
responsive, no pi work is orphaned — and `supports_interruption` flips
`True`. Feasibility verdict **(i) Sculptor-side only** (`feasibility.md`
§1): pi's `abort` command works, leaves the session usable, and ends the
run in ~11 ms with `stopReason:"aborted"` and partial content retained.

## Requirements addressed

REQ-CAP-INTERRUPTION; REQ-CAP-ALL-1..7; REQ-TEST-1/2/4.

## Background

Sculptor's pi harness (`sculptor/sculptor/agents/pi_agent/`) wraps the
pinned `pi --mode rpc` CLI (0.78.0). The base tranche (PR #54) landed the
substrate this task builds on:

- **Typed protocol**: `output_processor.py` models the full wire union;
  `parse_rpc_message(dict) -> ParsedRpcMessage`; the dispatcher is one
  exhaustive `match` in `PiAgent._dispatch_event` (`agent_wrapper.py`).
- **Dead-letter**: `PiAgent._push_message` currently error-logs and drops
  `InterruptProcessUserMessage` (listed in `_DEAD_LETTER_MESSAGE_TYPES`,
  `agent_wrapper.py` ~line 106). This task replaces that drop with real
  handling.
- **Frontend gates**: the Stop button renders via
  `useCapabilityGate(canBeInterrupted, ElementIds.CAPABILITY_DISABLED_STOP)`
  (`StatusPill.tsx:116`), the queued-message interrupt via `CapabilityGate`
  (`QueuedMessageBar.tsx:132`, `CAPABILITY_DISABLED_QUEUED_INTERRUPT`),
  and the Ctrl+C keybinding via `useTaskSupportsInterruption`
  (`ChatInput.tsx`). All read `supportsInterruption` through narrow hooks
  (`useTaskHelpers.ts`); the ratchet `no-direct-harness-capability-read`
  forbids direct `.harnessCapabilities.` reads.
- **Request lifecycle**: `DefaultAgentWrapper._handle_user_message`
  (`agents/default/agent_wrapper.py:137-196`) wraps every pi turn
  (`PiAgent._process_message_queue`) and emits
  `RequestSuccessAgentMessage(interrupted=self._was_interrupted.is_set())`
  — the base class already owns `_was_interrupted: threading.Event`
  (line 62). The frontend resolves the in-flight chat message on that
  terminal Request message.

Probe facts that bound the design (`feasibility.md` §1): after `abort`,
the interrupted assistant message carries `stopReason:"aborted"` with
partial content blocks; `agent_end` fires `willRetry:false`; the same
process accepts the next `prompt` normally; abort→`agent_end` ≈ 11 ms.
Claude-parity semantics (REQ-CAP-INTERRUPTION): qualitative bar — Stop
ends the turn with latency comparable to Claude's observable behavior;
queued-message behavior matches Claude's (Sculptor-owned queue; pi's
native `steer`/`follow_up` are deliberately NOT adopted).

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — accept
  `InterruptProcessUserMessage` in `_push_message` (remove it from
  `_DEAD_LETTER_MESSAGE_TYPES` and its comment row): send
  `{"type":"abort"}` via `_send_rpc` (id-correlated), set the base
  `_was_interrupted` event, and mark interrupt-pending state the
  dispatcher can read. In the abort-pending state, `stopReason:"aborted"`
  on `message_end`/`agent_end` messages MUST finalize partial text
  normally instead of raising `PiCrashError` (today
  `_handle_message_end`/`_handle_agent_end` raise on `"aborted"` — that
  stays the behavior ONLY when no interrupt is pending). Add an
  escalation ladder: if `agent_end` doesn't arrive within a grace window
  after abort, SIGTERM the process (pi exits 143, RPC §3) and rely on the
  existing process-exit fallback in `_consume_until_turn_end`.
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_interruption=True`; update the stance comment (it currently
  explains the drop).
- `sculptor/sculptor/agents/pi_agent/harness_test.py` and
  `.../claude_code_sdk/harness_test.py` (if stance-asserting) — update
  expected stances.
- `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py` — unit
  coverage (see Testing).
- `sculptor/sculptor/testing/fake_pi.py` — today the `abort` branch in
  `_run_rpc_loop` (lines 287-289) acks and **exits**; real pi stays
  alive. Change it to: ack the abort, emit an `agent_end` for any
  in-flight turn (assistant message with `stopReason:"aborted"` +
  whatever partial text directives produced), and keep looping. Abort
  arriving while a directive like `fake_pi:sleep`/`wait_for_file` blocks
  needs the loop reorganized so abort can preempt a running turn (e.g.
  read stdin on a thread or check between directive steps) — keep it
  deterministic (sentinel-file pauses, no wall-clock racing).
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  flip the pi-side branches of `test_stop_button_gated_on_interruption`
  (line ~157) and `test_queued_interrupt_gated_on_interruption` (~182):
  pi now shows the REAL Stop affordance (the `CAPABILITY_DISABLED_*`
  placeholders are absent for BOTH harnesses), and pressing Stop ends the
  turn.
- **Create** `sculptor/tests/integration/real_pi/test_interrupts.py` —
  mirror `sculptor/tests/integration/real_claude/test_interrupts.py`'s
  applicable cases (see Testing).

## Implementation details

1. Interrupt flow: `_push_message` recognizes
   `InterruptProcessUserMessage` → record the interrupt (set
   `_was_interrupted` + an interrupt-pending flag/event the dispatcher
   checks) → `_send_rpc({"type":"abort", "id": <generated>})` → return
   `True` (handled). The in-flight turn keeps running inside
   `_handle_user_message`; when the abort-induced `agent_end` arrives,
   `_consume_until_turn_end` returns and the wrapper emits
   `RequestSuccess(interrupted=True)` because `_was_interrupted` is set —
   no new message types needed.
2. The interrupt may arrive when NO turn is in flight (race): the flag
   must not poison the NEXT turn — clear interrupt-pending when a new
   prompt is sent (mirror the comment in Claude's
   `_process_single_message`, `process_manager.py:575-583`, which handles
   the same race).
3. Grace-window escalation: implement with the existing concurrency
   primitives (`self.concurrency_group`/`ObservableThread` patterns in
   this file); on expiry, `self._process.terminate()` — the dispatcher's
   `process.is_finished()` exit path already resolves the turn.
4. The abort `response` envelope (`command:"abort"`) is already absorbed
   by `_handle_response_event` (logged, ignored) — no change needed
   there.
5. Keep the Sculptor-owned message queue untouched: queued messages send
   after the interrupted turn resolves, exactly as today.

## Testing suggestions

- Unit (`agent_wrapper_test.py`): interrupt mid-turn → abort written to
  stdin, turn resolves with `interrupted=True`, no `PiCrashError` on the
  aborted `stopReason`; interrupt with no turn in flight → next turn
  unaffected; `stopReason:"aborted"` WITHOUT interrupt-pending still
  raises `PiCrashError`; escalation fires `terminate()` when no
  `agent_end` arrives.
- Integration (fake_pi): a long streaming turn (`fake_pi:stream_text`
  with a sentinel-file pause) + Stop button → chat resolves as
  interrupted, agent accepts a follow-up; the two flipped gating tests.
- Real (`real_pi/test_interrupts.py`): graceful stop of a long
  generation + a follow-up turn on the same agent (mirrors
  `real_claude/test_interrupts.py`'s stop case; the force-kill ladder
  case is unit/integration-covered — note any divergence in the MR per
  REQ-TEST-1). Full suite: `just test-real-pi` green at merge
  (REQ-TEST-2).

## Gotchas

- Do NOT clear `_was_interrupted` yourself on success — the base wrapper
  reads-and-clears it (`agent_wrapper.py:186-188` base class).
- `stopReason:"aborted"` is ambiguous: interrupt-pending → expected
  finalization; otherwise → error path. Get this branch right or
  real aborts will render as crashes (or crashes as clean stops).
- fake_pi's old exit-on-abort behavior is load-bearing for some existing
  shutdown tests — check `agent_wrapper_test.py` / integration shutdown
  paths that relied on it (`PiAgent.wait` also sends `abort` at shutdown:
  `agent_wrapper.py` `wait()`); keep shutdown semantics working (abort at
  shutdown is followed by stdin close — fake_pi exits on stdin EOF).
- The Ctrl+C keybinding gate in `ChatInput.tsx` reads
  `useTaskSupportsInterruption(...) ?? true` — no code change needed
  there; it activates with the flag. Verify, don't re-wire.
- Tranche conventions: own workspace on `danver/pi-capabilities-interruption`
  rooted at current `origin/main` (≥ merge `99cbc0d`), MR → `main`;
  `just rebuild` first (fresh worktree); commit rules (`just format` /
  `check` / `test-unit`, trailer `Co-authored-by: Sculptor <sculptor@imbue.com>`);
  integration tests via the repo's integration-test skill (background +
  watchdog); evidence bundle in the MR (deterministic gates single-run,
  FULL `just test-real-pi`, real-claude rerun — ask Danver if the
  environment lacks prerequisites; ticked checklist); PR world-readable
  ending `(Sent by Claude)`; announce per post-mr-to-slack; pause and ask
  Danver before converting anything to a deferral (REQ-INV-6).

## Verification checklist

- [ ] Stop ends an in-flight pi turn; the chat message resolves
      interrupted; a follow-up turn works on the same process.
- [ ] `supports_interruption=True` for pi; stance tests updated; the
      flipped gating tests assert the REAL Stop affordance under pi.
- [ ] Aborted-vs-crash disambiguation unit-covered both ways.
- [ ] Escalation ladder covered (no `agent_end` → terminate → turn
      resolves).
- [ ] fake_pi stays alive after abort and existing shutdown tests pass.
- [ ] No remaining `CAPABILITY-GAP` markers for interruption
      (`grep -rn "supports_interruption" + "CAPABILITY-GAP"`).
- [ ] Integration tests: `test_pi_capability_gating.py` (flipped),
      `test_pi_basic.py`, `test_minimum_interface_conformance.py`; new
      `real_pi/test_interrupts.py`; full `real_pi/` suite green at merge.
