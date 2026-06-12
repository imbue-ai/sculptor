# Task 0.1: Feasibility investigation — verdicts for every target capability

## Goal

Empirically classify each of the 11 target capabilities as (i) achievable
Sculptor-side only, (ii) achievable via an added pi extension, (iii)
achievable only via a pinned-version bump (permission-gated), or (iv)
blocked on pi-core → defer — and record verdicts, evidence, and chosen
mechanism sketches in `agent_docs/pi-capabilities/feasibility.md`.
This document gates every capability tranche and feeds the pass-2
planning session that writes their task files.

## Requirements addressed

REQ-INV-1, REQ-INV-2, REQ-INV-3, REQ-INV-4, REQ-INV-5 (establishes the
gate), REQ-PROC-2, REQ-PROC-6 (adapted), REQ-PROC-7.

## Background

Sculptor (this repo) runs coding agents in workspaces; the **pi harness**
(`sculptor/sculptor/agents/pi_agent/`) wraps the third-party `pi` CLI
(`@earendil-works/pi-coding-agent`, pinned at **0.78.0** — see
`PI_VERSION_RANGE` in
`sculptor/sculptor/services/dependency_management_service.py:64-68`) as an
alternative to Claude Code. pi shipped "degraded": 11 of its capability
flags are `False` (see `PiHarness.capabilities()` in
`sculptor/sculptor/agents/pi_agent/harness.py:54-72`), each disabling a
real Sculptor affordance. This cycle (`pi-capabilities`) turns flags
`True` where genuine support can land. **pi-core is immutable — not ours
to change.** The only pi-side levers are: configuration/flags pi already
supports, adding extensions to Sculptor's pinned set, or (permission-
gated, opportunistic) a pinned-version bump.

The cycle's documents, all under `agent_docs/pi-capabilities/`:
`goals.md` (intent), `requirements.md` (REQ-* identifiers; the verdict
taxonomy is REQ-INV-2), `architecture.md` (Sculptor-side designs; §4.3–
§4.11 end with the **probe checklists** reproduced below). The wire
protocol is already authoritatively characterized in
`agent_docs/pi-basic/pi-0.78.0-rpc.md` ("RPC §n" below) — built
from the shipped tarball's `docs/rpc.md`, `rpc-types.d.ts`, and live
probes. Trust it for protocol *shapes*; this task's job is the behaviors
it could not verify (most need a real API key, which it lacked).

Key protocol facts to build on (RPC §3–§9): commands are JSONL on stdin
(`prompt{message, images?, streamingBehavior?}`, `abort`, `new_session`,
`compact`, `set_auto_compaction`, `switch_session`, `fork`, `get_state`,
`get_commands`, `bash`, model/thinking setters); stdout multiplexes
`response` envelopes (correlate by `id`, NOT order), `AgentSessionEvent`s
(`agent_start/end`, `turn_start/end`, `message_start/update/end`,
`tool_execution_start/update/end`, `compaction_start/end{reason}`,
`queue_update`, `auto_retry_*`, `extension_error`), and
`extension_ui_request` dialogs (`select`/`confirm`/`input`/`editor`,
answered via `extension_ui_response`; plus fire-and-forget methods).
`agent_end` is the turn boundary; preflight failure = `response
success:false` with NO session events. Startup flags include
`--no-session`, `--session-dir`, `--no-skills`, `--no-extensions`,
`--no-tools`, `--offline`, `--provider/--model`.

What pi-basic does today (for contrast): launches `pi --mode rpc
--no-session --append-system-prompt <prompt>`
(`agent_wrapper.py:140`), consumes only text deltas and message/agent
ends, discards tool/compaction/extension events, and drops
interrupt/resume/clear/answer control messages
(`agent_wrapper.py:150-161`).

## Files to modify/create

- `agent_docs/pi-capabilities/feasibility.md` — **the only file
  that merges.** Spike code, probe scripts, and transcripts stay on this
  task's branch, unmerged (REQ-INV-4).

## Implementation details

1. **Workspace/branch:** own workspace on
   `danver/pi-capabilities-feasibility`, rooted on `main`, MR → `main`
   (REQ-PROC-2). Prerequisites: a real pi binary at the pinned version
   (`just install-pi` exists for the managed GitHub-release install — see
   RPC §2.2; or npm `@earendil-works/pi-coding-agent@0.78.0`) and a real
   API key in the environment (pi reads names listed in
   `PiConfig.api_key_env_var_names`; `ANTHROPIC_API_KEY` is the default —
   see `tests/integration/real_pi/conftest.py`). The version guard in
   `PiAgent._check_pi_version` (`agent_wrapper.py:217-235`) rejects
   off-pin binaries — probe with the pinned one only.
2. **Probe method:** drive `pi --mode rpc` directly over stdin/stdout
   (the protocol doc's live-probe style, RPC §2). Where useful, also
   extract the npm tarball and read `docs/`, `dist/modes/rpc/*`, and
   extension-related sources — reading pi source is allowed; *modifying*
   pi is not. Use `--offline` where network startup noise is unwanted.
   Keep every probe transcript; evidence is mandatory per verdict
   (REQ-INV-3).
3. **Answer the probe checklists** (from `architecture.md` §4.3–§4.11):
   - **Interruption (§4.3):** does `abort` mid-stream leave the session
     usable for the next `prompt`? abort during tool execution — does the
     tool die? what does `agent_end` carry after abort (partial messages?
     `stopReason:"aborted"`)? abort→`agent_end` latency on a long
     generation?
   - **Tool rendering (§4.4):** exact arg schemas of `read`/`edit`/
     `write`/`bash`; `partialResult` size/truncation on long outputs;
     ordering between `message_update`(toolcall_*) and
     `tool_execution_*`; any sub-agent-like tools in the default set?
   - **Context reset (§4.5):** does `new_session` genuinely clear context
     (ask a prior-content question after it)? does it reset model/
     thinking selections or only history? behavior while streaming?
   - **Compaction (§4.6):** does threshold auto-compaction fire under
     0.78.0 defaults (`autoCompactionEnabled` default?)? any numeric
     threshold exposed for UI? compaction mid-turn vs between turns?
   - **Session resume (§4.7):** with `--session-dir`, does
     `switch_session` (or relaunch pointing at the same session file)
     restore context such that the next prompt sees prior content?
     crash-mid-write resilience? file growth over long conversations?
     interaction between `--session-dir` and `new_session`?
   - **Backchannel (§4.8):** how is an extension authored and loaded for
     `--mode rpc` (the tarball's extension docs/examples)? what do
     `ctx.ui.select/confirm/input/editor` offer; `timeout` semantics vs
     Sculptor's unbounded-wait AUQ? does pi support MCP servers natively?
     can plan-then-confirm be expressed?
   - **Skills (§4.9):** pi's skill discovery rules (directories, file
     format — does it read `.claude/skills`-style SKILL.md?); how a skill
     is invoked over RPC; does `get_commands` enumerate them; can
     discovery dirs be injected per launch?
   - **Sub-agents / background tasks (§4.10):** can an extension spawn
     nested work and surface lifecycle events? anything backgroundable in
     pi's toolset? (No protocol surface exists — deferral is the expected
     outcome unless extensions can express these.)
   - **Image input / attachments (§4.11):** does a text-only model
     **error** on `prompt.images[]` or silently ignore it? what does
     `get_available_models` expose about multimodality? practical size
     limits for base64 images over stdin JSONL? do attachments-by-path
     satisfy "usable that turn" for large files?
4. **Write `feasibility.md`** with: a header naming the verdict taxonomy
   (REQ-INV-2); a **verdict table** (one row per target flag: verdict,
   one-line mechanism, evidence link); a **per-capability section** with
   probe answers, the chosen mechanism sketch (this is the *permanent
   record* — architecture.md deliberately contains no pi-side design),
   free-form notes where findings exceed the taxonomy, and — for verdict
   (ii) capabilities — the extension-runtime-failure posture
   recommendation (leaning: fail loud first); and a **"Graduation"
   placeholder section** at the end (filled at cycle close per
   REQ-PROC-9). For any immediate verdict-(iv) deferral, include a
   ready-to-curate "Proposed FOLLOWUPS entry" block (problem + evidence +
   direction) in the MR description (REQ-PROC-7).
5. **Signal the pass-2 handoff:** the MR description states that verdicts
   are ready for the capability-planning session (which writes
   `02_*`–`11_*` task files in `implementation_plan/`).

## Testing suggestions

- Not a code change — "testing" = evidence quality. Each verdict must be
  reproducible from its transcript/citation alone (REQ-INV-3).
- Sanity-run the existing suites to prove the branch is docs-only: the
  deterministic gates pass untouched.
- Existing integration tests that document current pi behavior (useful
  baselines while probing): `tests/integration/frontend/test_pi_basic.py`,
  `tests/integration/frontend/test_minimum_interface_conformance.py`,
  `tests/integration/real_pi/test_basic_message_flow.py`,
  `tests/integration/real_pi/test_file_edit.py`.

## Gotchas

- **Nothing but the document merges** — no probe scripts, no extension
  spikes, no `~/.pi` config (REQ-INV-4). Keep the workspace + branch on
  disk for reference until cycle close; Danver deletes them.
- Do NOT add anything to the pinned plugin set here — extension spikes
  are throwaway evidence, not shipped code (REQ-EXT lands later).
- A pinned-version bump may look tempting if 0.79+ adds surface; it
  requires Danver's explicit permission BEFORE bumping (REQ-PROC-5) —
  record the opportunity as a verdict-(iii) note instead.
- `pi --version` writes to **stderr** (RPC §2.2); response ordering is
  not FIFO — correlate by `id` (RPC §5.1).
- Probes that need money: anything past preflight needs a real key —
  budget prompts small; the test-prefix convention in
  `tests/integration/real_pi/helpers.py` (`[SCULPTOR-UI-TEST] ...`) is a
  good prompt-hygiene model.

## Verification checklist

- [ ] `feasibility.md` exists with a verdict row for ALL 11 targets, each
      classified per the four-way taxonomy (REQ-INV-2).
- [ ] Every verdict cites evidence sufficient to re-check it (transcript
      excerpt, tarball file:line, or probe output) (REQ-INV-3).
- [ ] Verdict-(ii) sections include the mechanism sketch + failure-posture
      recommendation; verdict-(iv) entries have a Proposed FOLLOWUPS block
      in the MR description (REQ-PROC-7).
- [ ] The "Graduation" placeholder section exists at the end.
- [ ] The merged diff contains ONLY `feasibility.md` (REQ-INV-4).
- [ ] MR description signals pass-2 readiness and lists environment
      details (pi version probed, models used).
- [ ] Integration tests: none required (docs-only MR) — baseline suites
      named in Testing suggestions remain green.
