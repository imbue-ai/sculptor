# Task 7.1: Interactive backchannel — AUQ + plan mode for pi (`supports_interactive_backchannel`)

## Goal

Both interactions the flag gates work end-to-end on pi: (a)
ask-user-question — the agent poses a structured question, the user
answers in Sculptor's UI, the answer reaches the agent mid-turn; (b) plan
mode — entry, plan presentation, and exit behave as on Claude — and
`supports_interactive_backchannel` flips `True`. Feasibility verdict
**(ii) via added pi extension** (`feasibility.md` §6): a ~25-line spike
extension proved the full AUQ round-trip over pi's extension-UI dialog
lane; pi ships a `plan-mode` example extension; pi has NO native MCP.

This is the first tranche that ships an extension — it also establishes
the REQ-EXT packaging home and the fail-loud runtime-failure posture.

## Requirements addressed

REQ-CAP-BACKCHANNEL; REQ-EXT-1..5; REQ-CAP-ALL-1..7; REQ-TEST-1/2/4.

## Background

Claude's backchannel: its MCP server delivers
`mcp__sculptor__ask_user_question` / `mcp__sculptor__exit_plan_mode`
tool calls; the output processor emits `AskUserQuestionAgentMessage`
(`sculptor/sculptor/interfaces/agents/agent.py:397`) carrying
`AskUserQuestionData` (`imbue_core/imbue_core/sculptor/state/chat_state.py:224`);
the frontend blocks input while a question is pending
(`app.py` send endpoint 409s, ~2086); the user's answer arrives as
`UserQuestionAnswerMessage` via the `answer_question` endpoint
(`app.py` ~2114) and is delivered back into the in-flight turn. Plan
mode: the send endpoint gates `enter_plan_mode` on this capability
(`app.py:2078` — flips automatically with the flag); plan state rides
`ChatInputUserMessage.enter_plan_mode`/`exit_plan_mode`, plan-approval
questions are synthesized via `make_plan_approval_question`
(`chat_state.py`; see Claude's
`output_processor.py:1169-1215` `_maybe_handle_exit_plan_mode`), and the
harness's gated methods classify the tool blocks
(`is_ask_user_question_tool`, `is_exit_plan_mode_tool`,
`is_valid_ask_user_question_input`, plan-file extraction —
`interfaces/agents/harness.py:131-144`; consumed in
`web/message_conversion.py:508-524,913,946` and `web/derived.py:509-637`).

The base tranche (PR #54) landed: the typed `ExtensionUiRequest` model
(`output_processor.py:71-83` — `id`, `method`, optional `timeout`,
method-specific payload via `extra="allow"`); the dispatcher arm that
currently discards it (`_dispatch_event`); the dead-letter row for
`UserQuestionAnswerMessage`; the plan-mode toggle rendered via
`CapabilityGate` with `ElementIds.CAPABILITY_DISABLED_PLAN_MODE`
(`ChatInput.tsx:623`); and the gating test
`test_plan_mode_toggle_gated_on_interactive_backchannel`
(`test_pi_capability_gating.py:88`).

Wire facts (`feasibility.md` §6): an extension is a `.ts` module
exporting `default (pi: ExtensionAPI) => { pi.registerTool(...) }`,
loaded with `-e <path>` (repeatable). `--no-extensions` disables
*discovery* but explicit `-e` still loads — the lever for an immutable,
Sculptor-curated set (REQ-EXT-3). Imports
(`@earendil-works/pi-coding-agent`, `@earendil-works/pi-ai`) resolve
against the bundled binary. `ctx.ui.select/confirm/input/editor` are all
functional in RPC mode (`ctx.hasUI === true`), surfacing as
`extension_ui_request` ⇄ `extension_ui_response`; with NO `timeout`
field pi blocks indefinitely — exactly Sculptor's unbounded-wait AUQ
model. The shipped `plan-mode` example
(`<pi-pkg>/examples/extensions/plan-mode/`) provides `/plan`, read-only
tool restriction, `Plan:` extraction, an "Execute the plan?" confirm,
and session-persistent state. A thrown extension surfaces as a
non-terminal `extension_error` event — the locked posture for this
tranche is **fail loud** (a mid-turn `extension_error` from OUR
extension fails the turn visibly).

## Files to modify/create

- **Create** `sculptor/sculptor/agents/pi_agent/extensions/` — the
  REQ-EXT home (in-repo, code-reviewed, pinned with the binary as one
  unit, never user-visible, no secrets, no telemetry). First extension:
  the Sculptor backchannel extension (suggested
  `sculptor_backchannel.ts`): registers an `ask_user_question` tool
  (schema: question text, options list, optional multi-select/freeform
  notes — mirror `AskUserQuestionData`'s needs) whose `execute` calls
  `ctx.ui.select`/`ctx.ui.input` with NO timeout and returns the answer
  as the tool result; plus the plan-mode lever adapted from the shipped
  `plan-mode` example (a `/plan`-style mode with read-only tools and an
  exit/confirm signal Sculptor can drive). Document at the top of the
  file that the set is pinned with `PI_VERSION_RANGE` and re-validated on
  any bump (REQ-PROC-5).
- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` —
  1. `start()`: append `--no-extensions` plus `-e <abs path>` for each
     pinned extension (paths supplied by the harness/agent code, not
     globals — resolve the in-repo extension source's runtime location
     the same way other packaged resources are resolved in this repo;
     verify it works from an installed build, not just the repo
     checkout).
  2. Dispatcher: replace the `ExtensionUiRequest` discard arm — for the
     backchannel tool's dialog methods, emit
     `AskUserQuestionAgentMessage` (map request id → `tool_use_id`) and
     hold the turn open; on `UserQuestionAnswerMessage` (remove from
     `_DEAD_LETTER_MESSAGE_TYPES`), send
     `{"type":"extension_ui_response","id":...,"value":...}` and emit the
     `RequestStartedAgentMessage`/deferred-success flow the Claude path
     uses (`process_manager.py:214-242` is the reference for the
     answer-delivery lifecycle).
  3. Plan-mode wiring: translate `ChatInputUserMessage.enter_plan_mode` /
     `exit_plan_mode` into the extension's lever (e.g. the `/plan`
     command in the prompt or the extension's own control), track
     `_is_in_plan_mode` analogously to Claude
     (`process_manager.py:588-599`), and emit the same plan-mode
     messages.
  4. Fail-loud posture: a mid-turn `extension_error` whose
     `extension_path` is ours → fail the turn visibly (raise through the
     existing error path), replacing the info-log-only handling for our
     extension; foreign/none stay log-only.
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_interactive_backchannel=True`; override the gated methods
  truthfully for pi's tool names (`is_ask_user_question_tool` matching
  the extension's tool name; `is_valid_ask_user_question_input`
  validating its schema; plan-mode methods per the chosen lever) — these
  make `message_conversion`/`derived` classify pi's AUQ/plan blocks
  exactly as Claude's.
- `sculptor/sculptor/agents/pi_agent/harness_test.py`,
  `agent_wrapper_test.py` — stances + flow units.
- `sculptor/sculptor/testing/fake_pi.py` — directives to script the
  lane: e.g. `fake_pi:ui_request` `{method, title, options}` (emit the
  request, then block the turn until an `extension_ui_response` arrives
  on stdin, echo the answer into the turn's text) — deterministic,
  sentinel-file-free.
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  flip the plan-mode toggle test's pi branch (real toggle visible;
  `CAPABILITY_DISABLED_PLAN_MODE` absent for both).
- **Create** `sculptor/tests/integration/real_pi/test_ask_user_question.py`
  and `real_pi/test_plan_mode.py` — mirror the corresponding
  `real_claude/` tests' core flows.

## Implementation details

1. Sequencing within the tranche: AUQ first (the spike-proven path), plan
   mode second (the larger adaptation). Both must land for the flag to
   flip (one flag gates both — REQ-CAP-ALL-1; partial = no flip).
2. The send endpoint's pending-question 409 and the `app.py:2078` plan
   gate need NO changes — they read the flag/state that this tranche
   makes truthful.
3. AUQ data mapping: `select` → multiple-choice question; `input` →
   freeform; build `AskUserQuestionData` so the existing frontend
   question UI renders it unmodified (no new frontend work expected —
   the affordance is Sculptor-owned chrome gated on the flag).
4. The extension is TypeScript loaded by pi's jiti — there is no build
   step; treat it as source shipped with Sculptor. Keep it minimal and
   dependency-free beyond pi's own API surface.
5. If tool-rendering (phase 03) has landed, the AUQ tool call also
   renders as a tool block and the gated methods make
   `message_conversion` swap it for the question UI — verify the
   interplay; if 03 has NOT landed, AUQ must still work via the
   dispatcher-emitted messages alone (soft dependency only — verify both
   orders or note which landed first).

## Testing suggestions

- Unit: dialog-request → AskUserQuestion message mapping (select/input);
  answer → `extension_ui_response` write + request lifecycle; fail-loud
  on own `extension_error`; plan-mode state transitions; gated-method
  truth tables.
- Integration (fake_pi): full AUQ round-trip in the UI (question blocks
  input, answer resumes turn); plan-mode enter → plan → exit; flipped
  plan-toggle gating test.
- Real: `real_pi/test_ask_user_question.py` (agent asks, test answers,
  agent uses the answer), `real_pi/test_plan_mode.py` (enter, get a plan,
  approve/exit) — with the REAL extension loaded; these also prove
  REQ-EXT packaging works outside the repo checkout. Full
  `just test-real-pi` green at merge.

## Gotchas

- Never set a `timeout` on dialog calls — pi would auto-resolve with a
  default and the user's answer would race it.
- `--no-extensions` + `-e` ordering/behavior is the immutability
  guarantee — without `--no-extensions`, user-discovered extensions
  would load (violates REQ-EXT-3 and PHASE_6 §5).
- The extension's tool name is now API: the gated methods, the
  dispatcher, and tests all reference it — define it once (a constant
  shared by harness + wrapper) and never rename casually.
- Extension source path resolution must survive packaging (installed
  Sculptor builds run from an app bundle — find how other bundled
  resources resolve paths and follow that pattern; a repo-relative path
  is the trap).
- Coordinate launch-args with phases 06/08 (session-dir, skills flags) —
  each tranche appends its own flags; rebase carefully around the
  `command = [...]` line.
- Tranche conventions: own workspace on
  `danver/pi-capabilities-backchannel` rooted at current `origin/main`
  (≥ `99cbc0d`), MR → `main`; `just rebuild` first; commit rules
  (`just format`/`check`/`test-unit`, trailer
  `Co-authored-by: Sculptor <sculptor@imbue.com>`); integration tests via
  the repo's integration-test skill; evidence bundle in the MR
  (deterministic gates, FULL `just test-real-pi`, real-claude rerun — ask
  Danver if prerequisites are missing; ticked checklist); PR
  world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack; pause for Danver before any deferral (REQ-INV-6).

## Verification checklist

- [ ] AUQ round-trip works end-to-end in a pi workspace (question UI,
      answer reaches the mid-turn agent, turn completes using it).
- [ ] Plan mode: entry gated→allowed, plan presented, exit/approval flows
      match Claude's state machine; `app.py:2078` passes for pi.
- [ ] Gated methods truthful (message classification + waiting-state
      derivation behave as Claude's for pi blocks).
- [ ] Fail-loud: a thrown extension fails the turn visibly (unit + an
      integration fixture).
- [ ] REQ-EXT checklist: in-repo, `--no-extensions` + pinned `-e` set,
      no secrets/telemetry, path resolution works installed.
- [ ] `supports_interactive_backchannel=True`; stance tests updated;
      plan-toggle gating test flipped; backchannel CAPABILITY-GAP markers
      (`ChatInput.tsx:309` region, dead-letter row) resolved.
- [ ] Integration tests: flipped gating test, AUQ/plan fake_pi tests,
      `test_pi_basic.py`, `test_minimum_interface_conformance.py`; new
      `real_pi/test_ask_user_question.py` + `real_pi/test_plan_mode.py`;
      full `real_pi/` green at merge.
