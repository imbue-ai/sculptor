# Task 5.1: Compaction — auto-compact chrome is truthful for pi (`supports_compaction`)

## Goal

pi's compaction events light Sculptor's existing compaction chrome (the
StatusPill "Compacting" state) truthfully — and `supports_compaction`
(post-split: auto-compaction only) flips `True`. Feasibility verdict
**(i) Sculptor-side only** (`feasibility.md` §5): `compaction_start/end`
events exist and fire; `autoCompactionEnabled` defaults `true`; the same
events carry `reason: manual|threshold|overflow`.

## Requirements addressed

REQ-CAP-COMPACTION; REQ-CAP-ALL-1..7; REQ-TEST-1/2/4.

## Background

Claude's compaction surfaces in Sculptor via two ephemeral agent
messages — `AutoCompactingAgentMessage` / `AutoCompactingDoneAgentMessage`
(`sculptor/sculptor/interfaces/agents/agent.py:381,391`) — which drive
the derived `is_auto_compacting` task property
(`sculptor/sculptor/web/derived.py:278`: latest AutoCompacting wins until
a Done arrives) and from there the StatusPill "Compacting" state. The
TokenPopover "Context" row displays Claude's auto-compact threshold; pi
exposes **no numeric threshold** on the wire — `feasibility.md` §5 rules
leaving that sub-element empty a valid divergence note (REQ-CAP-ALL-3).

The base tranche (PR #54) landed: the post-split flag (this flag now
means auto-compaction chrome ONLY — `/clear` is `supports_context_reset`,
phase 04); the narrow atom/hook (`taskSupportsCompactionAtomFamily`,
`tasks.ts:143`); typed events `ParsedCompactionStart{reason}` /
`ParsedCompactionEnd{reason, result, aborted, will_retry, error_message}`
(`output_processor.py:162-174`) currently routed to the dispatcher's
enumerated discard arm; and the gating test
`test_compaction_chrome_absent_under_pi`
(`test_pi_capability_gating.py:240`) pinning the chrome absent for pi.

Wire facts (`feasibility.md` §5): manual `compact` produced
`compaction_start{reason:"manual"}` →
`compaction_end{reason:"manual", aborted:false, willRetry:false,
result:{summary, firstKeptEntryId, tokensBefore, details}}`; threshold
and overflow reuse the same events with their `reason`;
`compaction_end{willRetry:true}` (overflow) means pi re-runs the prompt —
the turn EXTENDS (the dispatcher already only ends turns on `agent_end`,
so no state change is needed; just don't treat compaction events as
terminal). Conversation memory survives compaction. No manual `/compact`
surface is added (Claude has none in Sculptor — parity bar).

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — move
  `ParsedCompactionStart`/`ParsedCompactionEnd` out of the discard arm:
  start → emit `AutoCompactingAgentMessage`; end → emit
  `AutoCompactingDoneAgentMessage` (check the two messages' exact fields
  at `interfaces/agents/agent.py:381-396` and mirror how Claude's side
  constructs them — find its emit sites with
  `grep -rn AutoCompactingAgentMessage sculptor/sculptor/agents/default`).
  `compaction_end{aborted:true}` or `error_message` set → still emit
  Done (the pill must not stick "Compacting"), and surface the error via
  the standard failed-turn path ONLY if pi itself ends the run in error
  (don't invent a failure pi didn't report).
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_compaction=True`; update the stance comment (and the
  `StatusPill.tsx:35` / `TokenPopoverContent.tsx:30` CAPABILITY-GAP
  markers: the pill's marker is resolved by this tranche; the
  TokenPopover threshold-row marker converts to a recorded divergence
  note, not a gap).
- `sculptor/sculptor/agents/pi_agent/harness_test.py` — stances.
- `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py` — unit
  coverage (see Testing).
- `sculptor/sculptor/testing/fake_pi.py` — add a directive, e.g.
  `fake_pi:compaction` with args `{reason, will_retry?, aborted?}`,
  emitting the start/end pair mid-turn (between text directives) so
  integration tests can script the pill state deterministically.
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  flip `test_compaction_chrome_absent_under_pi`: under pi, a scripted
  compaction now SHOWS the Compacting state while active and clears it
  after; Claude side unchanged.
- **Create** `sculptor/tests/integration/real_pi/test_compaction.py` —
  see Testing for the honest scoping.

## Implementation details

1. The mapping is two `match` arms and two message constructions — the
   weight of this tranche is in tests and truthfulness edges:
   - start without end (process dies mid-compaction): the pill clears via
     the turn's failure path — verify `is_auto_compacting` doesn't stick
     (derived.py:278 scans messages; a Done or terminal turn message must
     unstick it — if nothing does, emit Done on the process-exit path).
   - end-without-start (resumed mid-stream): emit Done idempotently.
2. `will_retry:true`: emit Done for the compaction itself; the turn
   continues (a new agent run follows). No turn-boundary change.
3. Nothing reads pi's `result.summary` this cycle — don't render it
   (Claude shows no equivalent).

## Testing suggestions

- Unit: each arm (start → AutoCompacting message; end → Done; aborted/
  error end still Done; will_retry extends), plus the stick-prevention
  edge (start then process exit).
- Integration (fake_pi): scripted compaction mid-turn shows then clears
  the pill under pi (flipped gating test); Claude side untouched.
- Real (`real_pi/test_compaction.py`): triggering REAL threshold
  compaction cheaply is not reliable, and Sculptor has no manual compact
  surface. Honest scoping per REQ-TEST-1's divergence clause: mirror the
  *chrome truthfulness* contract — a long-ish conversation that may
  compact opportunistically (assert no error and, when compaction events
  occur, that the pill cycles) — or document in the MR why the real-pi
  mirror is a justified divergence with deterministic coverage carrying
  the weight. State the choice explicitly in the MR.
- Full `just test-real-pi` green at merge (REQ-TEST-2).

## Gotchas

- The split matters: do NOT touch `/clear` paths here (phase 04 owns
  `supports_context_reset`); this flag is chrome-only.
- The TokenPopover threshold row stays empty for pi (no wire threshold) —
  that's the recorded divergence, not a bug to fake with a made-up
  number.
- `is_auto_compacting` derivation scans message history in reverse
  (derived.py:278-285) — emitting Done twice is safe; never emitting it
  is the dangerous direction.
- Tranche conventions: own workspace on
  `danver/pi-capabilities-compaction` rooted at current `origin/main`
  (≥ `99cbc0d`), MR → `main`; `just rebuild` first; commit rules
  (`just format`/`check`/`test-unit`, trailer
  `Co-authored-by: Sculptor <sculptor@imbue.com>`); integration tests via
  the repo's integration-test skill; evidence bundle in the MR
  (deterministic gates, FULL `just test-real-pi`, real-claude rerun — ask
  Danver if prerequisites are missing; ticked checklist); PR
  world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack; pause for Danver before any deferral (REQ-INV-6).

## Verification checklist

- [ ] A scripted pi compaction shows the Compacting pill state while
      active and clears it after — both reasons (manual via fake_pi
      args, threshold shape identical) covered at unit level.
- [ ] No stuck-pill path survives (start-without-end covered).
- [ ] `supports_compaction=True`; stance tests updated; pill marker
      resolved; TokenPopover divergence recorded in the MR.
- [ ] Integration tests: flipped `test_compaction_chrome_absent_under_pi`
      (now asserting truthful chrome), `test_pi_basic.py`,
      `test_minimum_interface_conformance.py`; `real_pi/test_compaction.py`
      per the honest scoping above; full `real_pi/` green at merge.
