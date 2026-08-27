# SCU-1776: Serialize pi completion wake-ups through Sculptor's message FIFO

## Problem

When a pi sub-agent or background task completes, the pinned extensions
(`sculptor_subagent.ts`, `sculptor_background.ts`) wake the agent with
`pi.sendUserMessage(..., {deliverAs: "followUp"})`. If the completion lands
while a run is in flight (routine for fast children that finish during the
launch run), pi queues the wake-up **inside the run** and drains it at the next
turn boundary — the run continues with reaction turns instead of ending.
`agent_end`, the only turn boundary Sculptor's wrapper recognizes, is deferred
until the whole reaction chain finishes. Consequences (all observed in the
SCU-1776 incident logs and reproduced against real pi 0.80.2):

- Queued user messages wait indefinitely (`_process_message_queue` services one
  message per `agent_end`) — "the message to the outer agent is queued and
  waiting".
- The in-flight request cycle swallows the reaction turns, so the UI shows one
  endless "thinking" turn.
- `abort` (Stop) kills only the current *turn*; pi then drains the next queued
  wake-up, so no `agent_end` arrives within the 5s escalation grace window and
  Sculptor SIGTERMs a healthy pi.

Root cause, one sentence: **the extension wake-up is a second turn-initiator
inside pi, racing Sculptor's prompt pump; Sculptor's design assumes it is the
only initiator.**

## Fix

Make Sculptor the only turn-initiator. The `notify` data channel (completion
payloads) is unchanged; only the wake-up moves.

### 1. Extensions: remove the pi-side wake-up

Delete the `pi.sendUserMessage(...)` call (and its comment) from
`sculptor_subagent.ts` and `sculptor_background.ts`. The extensions still:
spawn children, stream/accumulate events, fire the completion `notify`, and
kill children on `session_shutdown`. Update both file headers: completion is
reported out-of-band via notify; *Sculptor* initiates the reaction turn.

### 2. Wrapper: enqueue a wake message on the input FIFO

New module-private message type in `agent_wrapper.py`:

```python
@dataclass
class _ReactionWakeMessage:
    text: str  # the wake prompt sent to pi verbatim
```

At the single seam where each completion is reconciled — the end of
`_handle_subagent_completion` and `_handle_background_completion` (both are
reached from the in-turn notify path AND the idle-drain path) — build the wake
text and `self._input_agent_messages.put(_ReactionWakeMessage(text=...))`.

Wake text (parity with what the extensions used to send, so model-visible
behavior is preserved):

- Sub-agents: `Your delegated sub-agent task ({label}) finished: {status} —
  {done}/{total} done, {failed} failed.` with `label` = the single child's
  label, or `{N} sub-agents` for a batch — derived from
  `SubagentCompletion.children`.
- Background: `Your background task finished: {status}{ (exit {code})}.`
  (The extension interpolated a label it held locally;
  `BackgroundTaskCompletion` does not carry one, and extending the notify wire
  contract just for the label is not worth it — the model still has the
  launching tool call in context.)

### 3. Wrapper: service the wake from the FIFO

`_process_message_queue` gets a `_ReactionWakeMessage` branch that calls
`_run_wake_turn(message)`:

- Emit `RequestStartedAgentMessage` with a fresh request id (the wake is not a
  reply to any user message).
- Send `{"type": "prompt", "id": <fresh>, "message": wake.text}` and consume
  with `_consume_until_turn_end(prompt_id)`.
- Non-fatal error handling, mirroring today's `_consume_reaction_turn`: a
  `PiCrashError` is logged and the cycle resolves `interrupted=True`; it must
  not tear down the agent.
- Emit terminal `RequestSuccessAgentMessage`.

FIFO ordering gives the fix its guarantees: a user message queued before the
completion is answered *first* (the ticket's expected behavior); a Stop ends
the current turn and pi is genuinely idle afterwards (nothing queued pi-side),
so interrupts resolve within the grace window.

### 4. Delete the reaction-window machinery

With no pi-initiated runs left, remove:

- `_note_awaiting_reaction`, `_is_awaiting_reaction`,
  `_awaiting_reaction_count`, `_awaiting_reaction_deadline`,
  `_REACTION_WINDOW_SECONDS`
- `_consume_reaction_turn` and the idle-drain's `ParsedAgentStart` arm.
  Replace the arm with a loud `logger.warning` (a pi-initiated run now
  indicates a protocol violation; its events would otherwise silently corrupt
  the next turn).
- The `_is_awaiting_reaction()` term in `_has_background_tasks`.

Update stale prose: `agent_wrapper.py` module docstring + the notify-path
comments, `harness.py` capability comments, `subagent.py` / `background.py`
module docstrings, `sculptor_subagent.ts` / `sculptor_background.ts` headers.

## Behavior deltas (accepted)

- Reaction ordering: previously a mid-run wake ran *before* queued user
  messages (pi drained followUps first); now user messages win. This is the
  bug fix.
- A Stop no longer implicitly cancels pending reactions mid-chain (it never
  cleanly did); queued wakes still run afterwards as individually stoppable,
  bounded turns.
- A wake enqueued but not yet serviced is lost on process restart — parity
  with today (pi's in-memory followUp queue is equally lost).
- Background wake text loses its `({label})` interpolation.

## Test plan

- **Failing-first unit tests** (`agent_wrapper_test.py`): completion (subagent
  + background, in-turn + idle-drain) enqueues a `_ReactionWakeMessage`; FIFO
  order puts an already-queued user message first; `_run_wake_turn` sends the
  wake prompt RPC and wraps the turn in its own request cycle; a wake-turn
  `PiCrashError` is non-fatal.
- **Updated tests**: `agent_wrapper_test.py` reaction-machinery tests;
  `fake_pi.py` loses `_emit_reaction_turn` + `reaction` directive args (the
  wake now arrives as a real prompt fake_pi answers with its default echo);
  `test_pi_sub_agents.py` / `test_pi_background_tasks.py` assert the wake turn
  via the echoed wake text instead of scripted reactions.
- **Real-pi verification (Phase 4)**: run `real_pi/test_sub_agents.py` and
  `real_pi/test_background_tasks.py`; drive the incident shape via
  `/auto-qa-changes` (instant children + long launch run + mid-run user
  message + Stop) and capture before/after evidence.
