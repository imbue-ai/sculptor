# Task 3.1: Tool-use rendering — pi tool calls render richly (`supports_tool_use_rendering`)

## Goal

pi's tool calls render as rich tool blocks (name, input, in-progress
state, result) equivalent to Claude's, instead of being discarded — and
`supports_tool_use_rendering` flips `True`. Feasibility verdict **(i)
Sculptor-side only** (`feasibility.md` §2): the tool-execution event lane
carries everything needed; the four core tools have stable arg schemas.

## Requirements addressed

REQ-CAP-TOOL-RENDERING; REQ-CAP-ALL-1..7; REQ-TEST-1/2/4.

## Background

Sculptor renders agent tool calls from harness-agnostic `ToolUseBlock`s
(`imbue_core/imbue_core/sculptor/state/chat_state.py:51-56` — fields
`id: ToolUseID`, `name: str`, `input`), carried in
`PartialResponseBlockAgentMessage` / `ResponseBlockAgentMessage` content
and assembled into ChatMessages by `web/message_conversion.py` (tool
results replace their tool-use via `_replace_tool_use_with_result`,
~line 368).

The base tranche (PR #54) landed the substrate:

- `output_processor.py` models the tool lane: `ParsedToolExecutionStart`
  (`tool_call_id`, `tool_name`, `args`), `ParsedToolExecutionUpdate`
  (`partial_result` — **accumulated** output, not deltas; consumers
  replace their display), `ParsedToolExecutionEnd` (`result`, `is_error`),
  plus `extract_tool_call_blocks(message)` for the `toolCall` content
  blocks inside assistant messages.
- `PiAgent._dispatch_event` (`agent_wrapper.py`) currently routes
  `ParsedToolExecutionStart/Update` to the enumerated discard arm and
  `ParsedToolExecutionEnd` to `_refresh_diff_if_file_change` only. The
  text accumulator (`_TurnState`, `_handle_message_update/_end`) emits
  partials/finals reusing stable `assistant_message_id` /
  `first_message_id` so the UI collapses streaming into final blocks.

Wire facts (`feasibility.md` §2): arg schemas — `bash {command}`,
`read {path}`, `write {path, content}`,
`edit {path, edits: [{oldText, newText}]}` (an ARRAY — pi's edit is
multi-edit-shaped, unlike Claude's single `old_string`/`new_string`);
the assistant message's `toolcall_start/delta/end` streaming sub-events
arrive BEFORE the matching `tool_execution_start`; `tool_execution_end`
carries rich details for file tools (`edit` → `{diff, patch,
firstChangedLine}`); `partialResult` is
`{content:[{type:"text",text}], details:{truncation, fullOutputPath}}`.
The default RPC toolset is exactly read/bash/edit/write.

Locked design (architecture §4.4): the **tool-execution lane is
authoritative** for rendering; the in-message `toolCall` blocks are
reconciled away (never rendered separately). Mapping policy: the core
four map onto Claude's renderers **with arg-shape adaptation in the
backend adapter**; any other tool renders generically (name + raw args +
result). Divergence note for the MR (REQ-CAP-ALL-3): Claude streams tool
*input* deltas; pi shows complete input at `tool_execution_start` —
equivalent fidelity, different rhythm.

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — replace the
  discard arms: `ParsedToolExecutionStart` → append a `ToolUseBlock`
  (id=`tool_call_id`, mapped name, adapted input) to the in-progress
  assistant content and emit a partial; `ParsedToolExecutionUpdate` →
  update that block's in-progress result display (replace, don't append);
  `ParsedToolExecutionEnd` → emit the tool-result content (mapping
  `result`/`is_error` onto the same shape Claude's tool results take in
  `ResponseBlockAgentMessage` content — study how
  `claude_code_sdk/output_processor.py` emits tool results and what
  `message_conversion._replace_tool_use_with_result` consumes), and keep
  the existing `_refresh_diff_if_file_change` call. `_TurnState` likely
  grows per-turn tool-block bookkeeping (blocks interleave with text in
  one assistant message).
- **Create** the name/arg mapping (a small module or functions beside the
  adapter): `read→Read {file_path}`, `write→Write {file_path, content}`,
  `bash→Bash {command}`, `edit` → single-element `edits` to Claude's
  `Edit {file_path, old_string, new_string}`, multi-element to
  `MultiEdit`-shaped input (verify the exact Claude MultiEdit input keys
  against `claude_code_sdk` usage before committing to them); unknown
  tools pass through unmapped (rendered generically by the frontend).
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_tool_use_rendering=True`; update stance comment.
- `sculptor/sculptor/agents/pi_agent/harness_test.py` — stances.
- `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py` — adapter
  unit coverage with wire-shape fixtures (the protocol doc's §9 shapes).
- `sculptor/sculptor/testing/fake_pi.py` — add a directive family, e.g.
  `fake_pi:tool_call` with args `{tool, args, result, is_error,
  updates?}`, emitting `tool_execution_start` → optional `_update`(s) →
  `_end` interleaved with the turn's text (and optionally the in-message
  `toolcall_*` sub-events to prove reconciliation).
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  update `test_sub_agent_pill_render_path_gated` if it asserted on tool
  rendering absence; add a pi-side test asserting a scripted tool call
  renders (name + result visible).
- **Create** `sculptor/tests/integration/real_pi/test_tool_calls.py` —
  mirror `real_claude/test_tool_calls.py`: a prompt forcing
  read/write/bash/edit usage; assert rendered tool blocks appear and the
  turn succeeds.

## Implementation details

1. Keep the message-ID streaming contract intact: tool blocks join the
   SAME in-progress assistant message the text accumulator advertises
   (`assistant_message_id`/`first_message_id`) so partial/final collapse
   keeps working. `message_end`'s authoritative text-finalization must
   not drop already-appended tool blocks — extend `_handle_message_end`
   to rebuild final content as interleaved text + tool blocks (the
   `toolCall` blocks on the final message, via
   `extract_tool_call_blocks`, are the reconciliation source for
   ordering).
2. Reconciliation rule: a `toolCall` content block with the same id as a
   rendered tool-execution block is the SAME call — never render both.
   The streaming `toolcall_*` sub-events stay ignored (the lane is
   authoritative).
3. `partial_result` text lives at
   `partial_result["content"][0]["text"]`-ish — parse defensively
   (permissive `Any` in the model); truncation metadata
   (`details.truncation`, `fullOutputPath`) may be surfaced in the
   result block's text if cheap, else ignored.
4. `is_error=True` results render as error results (match Claude's
   error-result shape so the frontend styles them identically).
5. Do not touch interruption/abort behavior (phase 02 owns it) — but the
   aborted-turn path must tolerate a tool block left in-progress (no
   crash; block resolves with the turn).

## Testing suggestions

- Unit: adapter mapping table (all four tools + unknown tool + multi-edit
  array); interleaving (text → tool → text in one message); error result;
  reconciliation (in-message toolCall + lane events → one block).
- Integration (fake_pi): scripted `fake_pi:tool_call` renders name/args/
  result in the chat under pi; Claude side unaffected
  (`test_pi_capability_gating.py` extension); `test_pi_basic.py`,
  `test_minimum_interface_conformance.py` stay green.
- Real: new `real_pi/test_tool_calls.py`; full `just test-real-pi` at
  merge (REQ-TEST-2). Divergence note (input-at-start vs streamed input)
  recorded in the MR (REQ-TEST-1 / REQ-CAP-ALL-3).

## Gotchas

- `ToolUseID` and block identity: reuse pi's `tool_call_id` verbatim as
  the block id — `_replace_tool_use_with_result` correlates by id.
- Don't let `extract_assistant_text` start including toolCall text — text
  extraction and tool blocks are separate content entries.
- pi `edit`'s `edits[]` arg adaptation: verify Claude's `MultiEdit` input
  key names from the Claude-side code before mapping; a wrong key renders
  as a broken-looking edit rather than erroring.
- Diff refresh must keep firing ONLY for non-error `edit`/`write`/`bash`
  ends (`FILE_CHANGE_TOOL_NAMES`, `agent_wrapper.py:74`) — the rendering
  arm replaces the discard arm but must preserve that call.
- The gate substrate for this flag has no disabled-affordance surface
  (rendering simply starts working) — REQ-TEST-4 is satisfied by the
  two-sided rendering test, not a tooltip assertion.
- Tranche conventions: own workspace on
  `danver/pi-capabilities-tool-rendering` rooted at current `origin/main`
  (≥ `99cbc0d`), MR → `main`; `just rebuild` first; commit rules
  (`just format`/`check`/`test-unit`, trailer
  `Co-authored-by: Sculptor <sculptor@imbue.com>`); integration tests via
  the repo's integration-test skill; evidence bundle in the MR
  (deterministic gates, FULL `just test-real-pi`, real-claude rerun — ask
  Danver if prerequisites are missing; ticked checklist); PR
  world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack; pause for Danver before any deferral (REQ-INV-6).

## Verification checklist

- [ ] A pi tool call shows name + input while running and the result when
      done; errors style as errors; unknown tools render generically.
- [ ] No double-render from in-message `toolCall` blocks (reconciliation
      unit-tested).
- [ ] Text/tool interleaving collapses correctly from partials to finals.
- [ ] Diff refresh still fires only for non-error edit/write/bash.
- [ ] `supports_tool_use_rendering=True`; stance tests updated; no stale
      CAPABILITY-GAP markers for tool rendering.
- [ ] Integration tests: extended `test_pi_capability_gating.py`,
      `test_pi_basic.py`, `test_minimum_interface_conformance.py`; new
      `real_pi/test_tool_calls.py`; full `real_pi/` green at merge.
