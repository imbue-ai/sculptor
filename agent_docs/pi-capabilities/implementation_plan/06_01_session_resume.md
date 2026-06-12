# Task 6.1: Session resume — pi conversations survive restarts (`supports_session_resume`)

## Goal

A pi workspace's conversation survives an agent-process restart (Sculptor
restart / workspace reopen / stop-then-message): the resumed agent
answers follow-ups that depend on pre-restart content — and
`supports_session_resume` flips `True`. Feasibility verdict **(i)
Sculptor-side only** (`feasibility.md` §3): running with `--session-dir`
persists a JSONL session; relaunching against the same dir/id restored
full context in the probe (same `sessionId`, secret recalled verbatim).

## Requirements addressed

REQ-CAP-SESSION-RESUME; REQ-CAP-ALL-1..7; REQ-TEST-1/2/4.

## Background

This tranche owns a launch-behavior change every pi run will carry
(locked in the architecture Q&A): `PiAgent.start` currently spawns
`pi --mode rpc --no-session --append-system-prompt <prompt>`
(`agent_wrapper.py`, the `command = [...]` line in `start()`); this task
flips `--no-session` to a managed `--session-dir` and adds resume.

Claude's resume pattern (the contract to mirror): a persisted session-id
file under the environment state path
(`claude_code_sdk/process_manager.py:810-811`), validated and passed as
resume flags on relaunch (`process_manager.py:633-656`);
`ResumeAgentResponseRunnerMessage` is the runner-level message that
reaches the agent around resume — pi currently dead-letters it
(`_DEAD_LETTER_MESSAGE_TYPES`, `agent_wrapper.py` ~106). Study how the
Claude side consumes it (grep `ResumeAgentResponseRunnerMessage` across
`sculptor/sculptor/agents/default/` and the agent runner) before wiring
pi's handling — the load-bearing outcome is that a turn interrupted by a
process death resolves in the UI instead of sticking "thinking", and the
next turn has full context.

The base tranche (PR #54) landed: the narrow atom/hook
(`taskSupportsSessionResumeAtomFamily`, `tasks.ts:151`); the typed
protocol (incl. `ParsedSessionInfoChanged`); the dead-letter row this
task deletes. There is no frontend affordance surface for this flag —
REQ-TEST-4 is satisfied by behavior tests, not tooltip assertions.

Wire facts (`feasibility.md` §3): sessions are single JSONL files
(`<timestamp>_<uuid>.jsonl`) under the session dir, auto-saved, organized
by working directory; resume levers: `--continue` (most recent in dir),
`--session <path|id>` (exact), in-band `switch_session`; `get_state`
exposes `sessionId` and `sessionFile`. `new_session` (phase 04's clear)
starts a fresh id IN the same dir — resume must track the current id.
Crash-mid-write resilience and file growth were NOT stress-tested —
this tranche's tests bound them (partial-tail truncation is the expected
failure mode).

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` —
  1. `start()`: replace `--no-session` with `--session-dir <dir>` where
     `<dir>` lives under the environment state path (follow the
     state-file pattern already used in this class hierarchy:
     `get_state_file_contents` / `environment.get_state_path()` — see
     `REMOVED_MESSAGE_IDS_STATE_FILE` usage in
     `agents/default/agent_wrapper.py:74-76,104-107`).
  2. Persist the current session id: after the first successful prompt
     (and after any `new_session`), obtain `sessionId` (a `get_state`
     round-trip on the typed `RpcResponse.data`, or
     `ParsedSessionInfoChanged` if it proves sufficient) and write it to
     a state file.
  3. On `start()` with a persisted id: launch with `--session-dir` plus
     the exact-session lever (`--session <id>`; fall back to
     `--continue` only if exact-id resolution proves unreliable —
     record which lever shipped in the MR).
  4. Handle `ResumeAgentResponseRunnerMessage` (remove from
     `_DEAD_LETTER_MESSAGE_TYPES`): per the Claude-side contract you
     studied — at minimum, resolve any in-flight request the dead process
     left behind so the frontend unsticks.
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_session_resume=True`; update stance comment. Optionally
  override the polymorphic session-path helper(s) on `PiHarness`
  (`Harness.get_jsonl_path_for_working_directory`, `interfaces/agents/harness.py:146`)
  for diagnostics parity — optional, not load-bearing.
- `sculptor/sculptor/agents/pi_agent/harness_test.py` — stances.
- `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py` — unit
  coverage (see Testing).
- `sculptor/sculptor/testing/fake_pi.py` — emulate sessions: accept
  `--session-dir`/`--session`; persist enough state (e.g. a transcript
  file in the dir) that a relaunched fake_pi can answer a scripted
  recall; expose `sessionId` via a `get_state` response handler (add the
  command if fake_pi lacks it).
- `sculptor/tests/integration/frontend/` — an integration test for the
  stop-then-message resume flow under fake_pi (extend an existing pi
  file or add `test_pi_session_resume.py` beside the gating tests).
- **Create** `sculptor/tests/integration/real_pi/test_session_resume.py`
  — plant a sentinel, force an agent-process restart through a real user
  flow (Stop the agent, then send the recall prompt — the next message
  spawns a fresh process; if the harness offers a cleaner restart lever,
  use it), assert recall succeeds.

## Implementation details

1. The session dir must be per-task (the environment state path already
   is) so parallel pi workspaces never share sessions.
2. Order of operations on resume: persisted id exists → launch with the
   resume lever → verify via `get_state` that the reported `sessionId`
   matches → if mismatch/missing (corrupt/absent file), fall back to a
   fresh session and log at error (a silent context loss is the failure
   mode to avoid; a loud fresh start is acceptable degraded behavior).
3. Coordinate with phase 04 (context reset): `new_session` changes the
   id — if 04 is already merged, update the persisted id in its handler
   path too (or subscribe `session_info_changed` and centralize id
   tracking in one place); if 04 lands later, leave the pointer comment
   where the id is persisted.
4. Crash-mid-write: a truncated JSONL tail must not brick resume — the
   fallback in (2) covers it; add a unit fixture with a truncated file.

## Testing suggestions

- Unit: id persisted after first turn; relaunch arglist carries the
  resume lever; mismatch/corrupt-file falls back loud; resume message
  resolves a stuck in-flight request.
- Integration (fake_pi): full stop-then-message flow recalls a scripted
  sentinel; fresh workspace (no persisted id) starts clean.
- Real (`real_pi/test_session_resume.py`): sentinel recall across a real
  process restart; session-file growth eyeballed (log its size in the
  test output — the bound is informational, not an assertion).
- Full `just test-real-pi` green at merge (REQ-TEST-2). real_claude has
  no direct resume mirror — note the divergence rationale in the MR
  (REQ-TEST-1): the contract mirrored is Claude's resume *behavior*, not
  a specific test file.

## Gotchas

- This flips run behavior for EVERY pi turn (sessions now persist on
  disk). The growth concern is real: note in the MR what a long
  conversation's file looks like; do NOT add cleanup machinery this
  cycle without a demonstrated need (YAGNI — record as a FOLLOWUPS
  candidate if growth looks alarming).
- `--continue` resumes the MOST RECENT session in the dir — wrong session
  risk if anything else writes the dir; prefer exact `--session <id>`.
- Don't break phase 02's interrupt semantics: an aborted-then-resumed
  session must replay cleanly (the aborted partial is part of pi's
  session record; verify resume after an interrupt in integration).
- `pi --version`/startup is unchanged — only the session flags move.
- Tranche conventions: own workspace on
  `danver/pi-capabilities-session-resume` rooted at current `origin/main`
  (≥ `99cbc0d`), MR → `main`; `just rebuild` first; commit rules
  (`just format`/`check`/`test-unit`, trailer
  `Co-authored-by: Sculptor <sculptor@imbue.com>`); integration tests via
  the repo's integration-test skill; evidence bundle in the MR
  (deterministic gates, FULL `just test-real-pi`, real-claude rerun — ask
  Danver if prerequisites are missing; ticked checklist); PR
  world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack; pause for Danver before any deferral (REQ-INV-6).

## Verification checklist

- [ ] Stop-then-message (and real restart) recalls pre-restart content.
- [ ] Corrupt/missing session file falls back to a loud fresh start —
      never a silent context loss, never a crash loop.
- [ ] `new_session` interaction: post-clear, resume targets the NEW id.
- [ ] Resume after an interrupted turn works (composition with phase 02).
- [ ] `supports_session_resume=True`; stance tests updated; the
      dead-letter row for resume removed.
- [ ] Integration tests: the new fake_pi resume test,
      `test_pi_basic.py`, `test_minimum_interface_conformance.py`,
      `test_pi_capability_gating.py`; new
      `real_pi/test_session_resume.py`; full `real_pi/` green at merge.
