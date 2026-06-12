# Task 10.1: Sub-agents — nested, attributed rendering for pi (`supports_sub_agents`)

## Goal

pi sub-agent activity renders grouped and attributed like Claude's — a
parent entry with each child's activity nested and distinctly attributed
— and `supports_sub_agents` flips `True`. Feasibility verdict **(ii) via
added pi extension** (`feasibility.md` §8), with an explicit warning:
this is the **heaviest, lowest-confidence** item in the cycle.
**Schedule it late**, and treat the REQ-INV-6 pause-and-ask path as a
live contingency, pre-staged in the task-0 record.

## Requirements addressed

REQ-CAP-SUB-AGENTS; REQ-EXT-1..5; REQ-CAP-ALL-1..7 (esp. ALL-6 striving
bar + the deferral contingency); REQ-TEST-1/2/4.

## Background

Claude's sub-agents render through the harness-agnostic ChatMessage
contract: nested messages carry `parent_tool_use_id`
(`imbue_core/imbue_core/sculptor/state/chat_state.py:178-204`), and
`web/message_conversion.py` (~316-340) switches parent context on
`parent_tool_use_id` so children group under the spawning tool call;
`AlphaToolGroup` renders the grouping (gated at `AlphaToolGroup.tsx:69`
via `useTaskSupportsSubAgents` — base tranche kept the render path
suppressed for pi, pinned by `test_sub_agent_pill_render_path_gated`,
`test_pi_capability_gating.py:121`).

What pi offers (`feasibility.md` §8): NO sub-agent protocol surface in
pi-core (default toolset is read/bash/edit/write). The shipped
`subagent` example extension (`<pi-pkg>/examples/extensions/subagent/`)
spawns each subagent as a separate `pi` process (single / parallel ≤8,
4 concurrent / chained), streaming child progress through the parent
tool's `onUpdate` → surfacing over RPC as the parent's
`tool_execution_update.partialResult` **as aggregated formatted text** —
NOT structured per-child lifecycle events. Closing the parity gap
(nested + attributed) therefore needs a **bespoke Sculptor extension**
that emits structured per-child data the adapter can parse into
nested blocks — e.g. structured JSON in `partialResult` (child id,
child tool events) or piping each child's own RPC event stream upward.

Hard dependency: **phase 03 (tool rendering) must be merged** — the
nested rendering rides the ToolUseBlock pipeline 03 builds (the parent
subagent tool call is itself a rendered tool block; children attach via
`parent_tool_use_id`). Phase 07 (backchannel) establishes the extension
home (`sculptor/sculptor/agents/pi_agent/extensions/`), `-e` launch
wiring, and the fail-loud posture — land after it or replicate its
packaging exactly.

## Files to modify/create

- **Create** `sculptor/sculptor/agents/pi_agent/extensions/<subagent ext>.ts`
  — a Sculptor-pinned extension (REQ-EXT rules: in-repo, reviewed,
  pinned with the binary, user-invisible, no secrets, no telemetry)
  registering a subagent tool that spawns child `pi` processes (start
  from the shipped example's process management — including its
  abort-propagation/child-kill handling) but emits **structured**
  per-child progress: a stable child id, child lifecycle (started /
  tool-call / text / done), serialized into the parent tool's streaming
  result in a shape the adapter parses (define the schema in one place;
  version it in the payload).
- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — adapter:
  parse the structured `tool_execution_update.partialResult` of the
  subagent tool into nested content — child activity emitted as
  messages/blocks carrying `parent_tool_use_id` = the parent tool block
  id (the exact emission shape must match what
  `message_conversion.py:316-340` consumes; study how Claude's nested
  messages arrive before writing this).
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_sub_agents=True` (ONLY if the parity bar is met); stance
  comment.
- `sculptor/sculptor/agents/pi_agent/harness_test.py`,
  `agent_wrapper_test.py` — stances + parser units.
- `sculptor/sculptor/testing/fake_pi.py` — directive emitting a
  scripted subagent lifecycle (parent tool events whose partialResult
  carries the structured child payload) for deterministic UI tests.
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  flip `test_sub_agent_pill_render_path_gated`: pi now renders the
  nested group.
- **Create** `sculptor/tests/integration/real_pi/test_sub_agents.py` —
  a real nested run (parent spawns one child doing a trivial tool task);
  assert grouped rendering and clean completion.

## Implementation details

1. **Timebox the spike first** (inside this tranche): prove the
   structured-progress extension can carry child tool events with
   ordering and ids intact over `partialResult` BEFORE building the full
   adapter. If the lane can't carry it faithfully (interleaving loss,
   size limits, update coalescing), STOP — that's the REQ-INV-6
   trigger: pause, present findings to Danver, and convert to a deferral
   if he agrees (fail-closed gate stays exactly as the base tranche
   left it; ship the Proposed FOLLOWUPS entry block from the task-0
   record in the MR).
2. Abort composition: parent abort (phase 02's interrupt) must kill
   children — the example's Ctrl+C propagation is the starting point;
   verify no orphan `pi` processes after Stop (extend the phase-02
   no-zombie assertion to the nested case).
3. Concurrency: cap children conservatively (the example's limits are
   fine); the adapter must tolerate out-of-order child updates.
4. Fail-loud applies (the 07 posture): a thrown subagent extension fails
   the turn visibly.

## Testing suggestions

- Unit: payload parser (well-formed, out-of-order, truncated, versioned);
  nested-emission shape against message_conversion expectations.
- Integration (fake_pi): scripted parent+child renders as a nested
  group; abort kills the scripted child state; flipped gating test.
- Real (`real_pi/test_sub_agents.py`): one parent, one child, real
  nested render, no orphans (process-table check in the test teardown).
  Full `just test-real-pi` green at merge. Mirror
  `real_claude`'s sub-agent coverage where shapes correspond
  (REQ-TEST-1; divergences noted).

## Gotchas

- The flip is all-or-nothing under the strict rule: aggregated-text
  rendering (the example's native surface) does NOT meet the parity bar
  — don't flip for it. The override valve (REQ-CAP-ALL-2,
  maintainer-judged + `CAPABILITY-GAP` marker) exists but is Danver's
  call, not yours — ask.
- `partialResult` is ACCUMULATED, not a delta — the structured payload
  must be re-parseable from the full accumulated value each update
  (design for idempotent re-parse, not append).
- Child processes inherit the parent's API-key env — no new secret
  plumbing, and none may be embedded in the extension (REQ-EXT-4).
- Don't let child session files (if children run with sessions) pollute
  phase 06's managed session dir — children should run `--no-session`.
- Tranche conventions: own workspace on
  `danver/pi-capabilities-sub-agents` rooted at current `origin/main`
  (must include phases 03 and 07 merges — verify before starting), MR →
  `main`; `just rebuild` first; commit rules (`just format`/`check`/
  `test-unit`, trailer `Co-authored-by: Sculptor <sculptor@imbue.com>`);
  integration tests via the repo's integration-test skill; evidence
  bundle in the MR (deterministic gates, FULL `just test-real-pi`,
  real-claude rerun — ask Danver if prerequisites are missing; ticked
  checklist); PR world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack.

## Verification checklist

- [ ] Spike verdict recorded FIRST (structured progress viable / not) —
      and on "not", the REQ-INV-6 pause happened before any deferral.
- [ ] If delivered: nested + attributed rendering under pi matches
      Claude's grouping; abort leaves no orphan processes; flipped
      gating test; `supports_sub_agents=True` + stances.
- [ ] If deferred (with Danver's go-ahead): flag stays False, gates
      stay closed, `feasibility.md` §8 amended to the reversal, MR ships
      the Proposed FOLLOWUPS entry block.
- [ ] REQ-EXT checklist for the new extension (in-repo, pinned set,
      user-invisible, no secrets/telemetry).
- [ ] Integration tests: flipped (or intact, on deferral)
      `test_sub_agent_pill_render_path_gated`, `test_pi_basic.py`,
      `test_minimum_interface_conformance.py`; new
      `real_pi/test_sub_agents.py` (if delivered); full `real_pi/`
      green at merge.
