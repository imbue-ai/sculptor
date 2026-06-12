# Task 1.4: Typed pi protocol module + behavior-preserving dispatcher rewire

## Goal

Extend pi's event models to the **full documented wire union** (session
events, response envelopes, extension-UI requests, streaming sub-events)
and rewire the PiAgent dispatcher to parse-once typed dispatch — with
**zero behavior change** (events pi-basic discards are still discarded,
just typedly). Capability tranches then consume typed events instead of
raw dicts.

## Requirements addressed

REQ-BASE substrate (architecture §4.2), REQ-BASE-7 (no behavior change).

## Background

The pi harness (`sculptor/sculptor/agents/pi_agent/`) wraps the pinned
`pi --mode rpc` CLI (0.78.0). Its stdout multiplexes three lanes
distinguished by top-level `type`: `response` command-acks (correlate by
`id`, NOT arrival order), `extension_ui_request` dialogs, and the
`AgentSessionEvent` union. The wire protocol is authoritatively
characterized in `agent_docs/pi-basic/pi-0.78.0-rpc.md` (RPC §4
commands, §5 outbound vocabulary, §6 turn-boundary semantics, §7
streaming sub-events, §8 error channels, §9 tool events) — written
explicitly as ground truth for this typed rewrite.

Current state: `sculptor/sculptor/agents/pi_agent/output_processor.py`
already models the consumed subset as pydantic `SerializableModel`s —
`RpcResponse`, `ExtensionUiRequest` (type+id+method only),
`ParsedTextDelta`, `ParsedAssistantMessageError`, `ParsedAgentStart`,
`ParsedAgentEnd`, `ParsedMessageUpdate` (with `assistant_message_event`
kept as a raw dict), `ParsedMessageEnd`, `ParsedAutoRetryEnd`,
`ParsedExtensionError`, plus `AgentMessage` (content as raw dicts) and
`extract_assistant_text`. The dispatcher
(`sculptor/sculptor/agents/pi_agent/agent_wrapper.py`):
`_consume_until_turn_end` (258-302) splits the three lanes on raw
`event.get("type")`; `_handle_session_event` (324-363) chains
`if event_type == ...` branches, validating per-branch; tool events are
discarded except `tool_execution_end`, which triggers a workspace-diff
refresh for `FILE_CHANGE_TOOL_NAMES = {edit, write, bash}`
(`agent_wrapper.py:74, 357-381`).

Missing from the models (the events capability tranches will consume):
`turn_start`, `turn_end{message, toolResults}`, `message_start`,
`tool_execution_start{toolCallId, toolName, args}`,
`tool_execution_update{..., partialResult}` (accumulated, not delta),
`tool_execution_end{toolCallId, toolName, result, isError}`,
`queue_update{steering, followUp}`, `compaction_start{reason}`,
`compaction_end{reason, aborted, willRetry, errorMessage?}`,
`auto_retry_start`, `session_info_changed`, `thinking_level_changed`;
the full `extension_ui_request` shape (dialog methods
`select`/`confirm`/`input`/`editor` + fire-and-forget methods + optional
`timeout`); and typed streaming sub-event variants beyond
`text_delta`/`error` (`text_start/end`, `thinking_*`, `toolcall_*`,
`start`, `done`) per RPC §7.

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/output_processor.py` — extend to the
  full union: one model per documented event with exact wire field names
  (camelCase aliases — follow the existing models' alias handling via
  `SerializableModel`); a discriminated parse entry point (e.g. a
  function mapping a raw dict to the union or an "unknown event"
  wrapper); keep `AgentMessage.content` as raw dicts EXCEPT add a typed
  accessor for `toolCall` blocks alongside `extract_assistant_text`
  (tool-rendering tranche consumes it). Update the module docstring (it
  currently says "richer events are not surfaced").
- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — rewire
  `_consume_until_turn_end` + `_handle_session_event` to parse-once typed
  dispatch (match on the union) while preserving every current behavior:
  text accumulation (`_handle_message_update`, 383-418), non-assistant
  `message_end` drop (444-446), error paths raising `PiCrashError`
  (407-415, 447-449, 485-488, 506-508), `agent_end` turn boundary
  (464-498), `auto_retry_end` continue-on-success, `extension_error`
  info-log (511-524), tool-event discard + diff refresh on
  `tool_execution_end` (351-381), unknown-event debug-log-and-ignore
  (forward compat, RPC §5.3).
- `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py` — extend
  existing unit tests (this file already exercises the dispatcher; see
  the CAPABILITY-GAP marker near line 500) with parse/dispatch coverage
  for the newly-typed events using wire-shape fixtures lifted from the
  protocol doc's examples.

## Implementation details

1. Model the events exactly as documented — field names, optionality,
   and enum-ish literals (`compaction_start.reason ∈
   manual|threshold|overflow`; `done.reason ∈ stop|length|toolUse`;
   `error.reason ∈ aborted|error`). Where the doc marks something
   uncharacterized, leave the field permissive (`dict`/`str`) with a
   comment pointing at the RPC section.
2. The parse entry point must (a) route the three lanes, (b) tolerate
   unknown `type`s by returning an explicit Unknown variant that the
   dispatcher debug-logs (never raises), and (c) leave `response`
   correlation by `id` where it is today
   (`_handle_response_event`, 304-322).
3. Rewire dispatch to a single `match` over the typed union. Every arm's
   behavior must be byte-for-byte what the string-keyed chain does today
   — this task is substrate, not features. Newly-typed events that
   pi-basic never consumed (`turn_start`, `queue_update`,
   `compaction_*`, ...) land in the discard arm (debug log), explicitly
   enumerated so capability tranches replace exactly one arm each.
4. Keep `_TurnState` (85-103) and the message-ID streaming contract
   untouched: partials and finals must keep reusing
   `assistant_message_id`/`first_message_id` so the UI collapses
   in-progress text into the stable final block.

## Testing suggestions

- Unit: `agent_wrapper_test.py` — existing tests must pass unchanged
  (they pin today's behavior); add fixtures for each new event type
  asserting (a) it parses, (b) the dispatcher's observable behavior is
  unchanged (nothing emitted for discard-arm events; diff refresh still
  fires for file-change `tool_execution_end`; `PiCrashError` paths
  intact).
- Integration (deterministic, fake_pi-driven — fake_pi emits the same
  wire shapes): `tests/integration/frontend/test_pi_basic.py`,
  `tests/integration/frontend/test_minimum_interface_conformance.py`,
  `tests/integration/frontend/test_pi_capability_gating.py`.
- Real (manual, evidence bundle): `just test-real-pi` — both existing
  tests (`tests/integration/real_pi/test_basic_message_flow.py`,
  `tests/integration/real_pi/test_file_edit.py`) green against the real
  binary.

## Gotchas

- **Do not change `wait()`/abort plumbing** (176-194) or
  `_push_message` (150-161) here — interruption and dead-letter logging
  are other tasks (1.5 / phase 02).
- `ParsedMessageUpdate.assistant_message_event` is a raw dict today
  *deliberately*; if you type the sub-event union, the `text_delta` and
  `error` consumption paths must behave identically (including the
  empty-delta early return at 396-397).
- pi sends `tool_execution_update.partialResult` as ACCUMULATED output,
  not a delta (RPC §9) — encode that in the model's docstring; the
  rendering tranche depends on it.
- Response ordering is not FIFO (RPC §5.1) — nothing in the rewire may
  assume arrival order.
- Forward compat is load-bearing: an unrecognized event type must never
  crash the dispatcher (RPC §5.3 guidance; pi-basic's behavior today).

## Verification checklist

- [ ] Every event/command shape named in RPC §4/§5/§7/§9 has a model (or
      an explicit permissive field with a doc pointer).
- [ ] Dispatcher behavior is provably unchanged: existing
      `agent_wrapper_test.py` tests pass without modification.
- [ ] Unknown-type events: dispatcher debug-logs and continues (unit
      test with a fabricated `{"type":"from_the_future"}`).
- [ ] Diff refresh still fires only for non-error
      `edit`/`write`/`bash` `tool_execution_end` (unit-tested).
- [ ] Integration tests: `test_pi_basic.py`,
      `test_minimum_interface_conformance.py`,
      `test_pi_capability_gating.py`; manual `just test-real-pi` run
      recorded in the MR (evidence bundle).
