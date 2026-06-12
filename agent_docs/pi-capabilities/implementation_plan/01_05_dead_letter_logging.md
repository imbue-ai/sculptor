# Task 1.5: Dead-letter logging for unsupported control messages

## Goal

Make the pi agent's silent drops visible: every control message rejected
because its capability is unsupported logs a warning naming the message
type. No user-facing change.

## Requirements addressed

REQ-BASE-6.

## Background

Sculptor delivers user/runner control messages to agents through
`Agent.push_message`. The base class
(`sculptor/sculptor/agents/default/agent_wrapper.py:93-117`,
`DefaultAgentWrapper.push_message`) first offers the message to the
agent-specific `_push_message`; if that returns `False`, generic handling
covers `RemoveQueuedMessageUserMessage` and `StopAgentUserMessage`
(terminate) — anything else falls through unhandled.

The pi agent's `_push_message`
(`sculptor/sculptor/agents/pi_agent/agent_wrapper.py:150-161`) accepts
only `ChatInputUserMessage` (queued for the RPC pump) and returns `False`
for everything else. The CAPABILITY-GAP comment there (154-158)
enumerates the capability-correlated drops:
`ResumeAgentResponseRunnerMessage` (session resume),
`UserQuestionAnswerMessage` (interactive backchannel),
`InterruptProcessUserMessage` (interruption), `ClearContextUserMessage`
(context reset — retargeted by Task 1.1's comment update). Today these
vanish silently. The frontend gates *should* prevent them being sent for
pi, so an arriving one is a gate-failure signal — exactly what FOLLOWUPS-9
was about. The requirements decision: warn-and-drop (dead-letter
visibility), no user-facing change; capability tranches replace
warn-and-drop with real handlers as they land (interruption → phase 02,
context reset → 04, session resume → 06, backchannel → 07).

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — in
  `_push_message`, before the final `return False`, log a warning (the
  module already uses `loguru`'s `logger`) naming the concrete dropped
  message type (e.g. via `type(message).__name__`) and the task id; keep
  the CAPABILITY-GAP comment accurate (it shrinks as tranches land).
  Scope the warning to the capability-correlated message types named
  above; genuinely-generic messages that the base class handles after the
  `False` return (`StopAgentUserMessage`,
  `RemoveQueuedMessageUserMessage`, manual-sync messages — see the
  comment at 159-161) must NOT warn (they are handled, not dropped).
- `sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py` — unit
  coverage: pushing each capability-correlated message type to a PiAgent
  logs the warning and returns unhandled; pushing
  `StopAgentUserMessage` does not produce the dead-letter warning.

## Implementation details

1. Distinguish "dropped" from "deferred to base": only warn for message
   types the base class will NOT handle (the four capability-correlated
   types). The cleanest shape: an explicit tuple/match of those types →
   warn + `return False`; default branch stays silent `return False`.
2. Warning text should make triage trivial: message type name + a hint
   that a frontend gate should have prevented it (the FOLLOWUPS-9
   linkage), so a log-grep during incident triage tells the story.
3. Use `logger.warning` (not `info` — `_handle_extension_error` at
   511-524 uses `info` for non-actionable telemetry; a dropped control
   message is actionable).

## Testing suggestions

- Unit: `agent_wrapper_test.py` — loguru capture pattern (the suite
  already exercises `_push_message` paths; extend beside the existing
  drop coverage referenced by the marker near line 500).
- Integration (no observable UI change expected — suites stay green):
  `tests/integration/frontend/test_pi_basic.py`,
  `tests/integration/frontend/test_minimum_interface_conformance.py`.

## Gotchas

- Do NOT implement any real handling here (no abort send, no
  new_session) — phases 02/04/06/07 own those; this task is visibility
  only (REQ-BASE-7: zero behavior change).
- Don't warn on `ChatInputUserMessage` (handled) or base-class-handled
  types — a noisy dead-letter log is as useless as a silent one.
- Keep the return-contract intact: `_push_message` must still return
  `False` for unhandled messages so base-class generic handling runs.

## Verification checklist

- [ ] Each of the four capability-correlated message types produces
      exactly one warning naming its type (unit-tested).
- [ ] `StopAgentUserMessage` / `RemoveQueuedMessageUserMessage` produce
      no dead-letter warning and still stop/remove correctly.
- [ ] No new agent messages emitted; pi turn behavior unchanged.
- [ ] Integration tests: `test_pi_basic.py`,
      `test_minimum_interface_conformance.py` pass unchanged.
