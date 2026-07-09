# SCU-1776: Serialize pi completion wake-ups through Sculptor's message FIFO (simplified)

## Simplification memo

The original design's core cut is correct and kept: the bug is a **when/where +
who complect** — two turn-initiators (Sculptor's prompt pump and the pi-side
extension wake-up) braided through one event stream that has a single boundary
marker (`agent_end`). The fix un-braids by making Sculptor the only initiator.
This pass found three residual braids in the original design and cut them, and
records the guard-deletion audit.

**Ledger:**

1. **Wake text: a third rendering of the same fact** *(why/policy scattered)*.
   The original kept "parity with the extension's phrasing", introducing a
   bespoke wake string alongside the existing `_format_subagent_completion` /
   `_format_background_completion` renderings of the same completion fact.
   "Parity" is an *easy* claim (familiar/comparable), not a *simple* one. Cut:
   **one rendering per completion type, shared by the UI notification and the
   wake prompt** — one place to change how a completion reads. Artifact bonus:
   the background wake now carries the summary (output tail) the notification
   already carries, so the model learns the result, not just "finished". The
   original's "(label) is lost" delta dissolves — the shared rendering never
   had one.

2. **Wake turn: a second, hand-synced turn lifecycle** *(modular but
   complected)*. The original said "mirror today's `_consume_reaction_turn`" —
   copying a subset of the turn lifecycle (in-flight id, `_turn_in_flight`,
   interrupt-state clearing, escalation cancel, answer finalization) into a
   second site that must stay in sync with `_run_prompt_turn` by hand; a Stop
   landing during a wake turn exercises whichever flags the copy remembered to
   set. Cut: **one turn-driving lifecycle** used by both user turns and wake
   turns, parameterized by exactly the two genuine differences — payload
   construction (rich user payload vs bare wake prompt) and failure policy
   (user turn failures propagate; wake turn failures log and resolve the cycle
   `interrupted=True`). "Copy the 12 lines" was *easy*; one lifecycle is
   *simple*.

3. **Wake message type: keep it out of the wire union** *(data +
   representation)*. Reusing `ChatInputUserMessage` for the wake (considered)
   would be *easy* (no new type) but braids internal scheduling into
   user-chat semantics (plan-mode flags, request-id derivation, persistence
   expectations). Adding the wake to the serializable `Message` union would
   leak an internal concern into a shared contract. Cut: a module-private
   dataclass; the FIFO's element type widens to the internal union
   `Message | _ReactionWakeMessage`. The wake is not a user message; nothing
   should be able to treat it as one.

**Guard-deletion audit (Check A):**

- *Extension `sendUserMessage` deleted.* Invariant "the agent reacts to
  completions" is now enforced by the wrapper enqueueing the wake at the same
  seam that parses the completion notify (both the in-turn and idle-drain
  paths call `_handle_*_completion`). Tests that asserted the pi-initiated
  reaction are rewritten to assert the wake prompt turn.
- *Idle-drain `ParsedAgentStart` arm (and `_consume_reaction_turn`) deleted.*
  Invariant "pi never self-starts a run" is enforced by (a) removing the only
  cause — the extension wake-up — and (b) `--no-extensions -e <pinned>`, which
  prevents any foreign extension from loading. A `logger.warning` tripwire
  replaces the arm. **Factual precondition to verify in Phase 4 against real
  pi:** nothing else in pi 0.80.2 self-starts runs between prompts (the
  real-pi suite plus the incident-shape auto-qa run would surface a
  violation as this warning).
- *`_REACTION_WINDOW_SECONDS` / awaiting-reaction bookkeeping deleted.* Its
  job (keep the idle-drain polling until the pi-initiated reaction arrived)
  has no successor because the wake is enqueued synchronously when the notify
  is parsed; the drain still runs while `_background_tasks` /
  `_subagent_tasks` are non-empty, which is the only window completions can
  arrive in. Unit tests around awaiting-reaction are replaced by FIFO-enqueue
  assertions.
- *Terminal-only wake:* no guard needed — the extensions' `finish()` is the
  sole notify emitter and only sends `"completed" | "failed"` (wire
  contract), so every parsed completion is terminal. (Permissive parsing of a
  malformed status is a pre-existing property of the notification path; the
  wake adds no new decision on it.)

**Check B (inert-claim scan):** no field in this design is claimed
documentation-only. `_ReactionWakeMessage.text` is read to build the prompt;
completion payload fields keep their existing readers.

**Left alone (inherent complexity):** pi's followUp-drain semantics and the
single `agent_end` boundary are the environment, not the design's fault; the
in-turn vs idle-drain duality of completion surfacing is inherent to
completions racing turns and stays.

---

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
payloads) is unchanged; only the wake-up moves. Each concern below is one
strand.

### 1. Extensions: stop initiating turns

Delete the `pi.sendUserMessage(...)` call (and its comment) from
`sculptor_subagent.ts` and `sculptor_background.ts`. The extensions still:
spawn children, stream/accumulate events, fire the completion `notify`, and
kill children on `session_shutdown`. Update both headers: completion is
reported via notify; *Sculptor* initiates the reaction turn.

### 2. Wrapper: schedule the reaction on the input FIFO

Module-private, not part of the `Message` wire union:

```python
@dataclass
class _ReactionWakeMessage:
    text: str  # sent to pi verbatim as the wake prompt
```

`_input_agent_messages` widens to `Queue[Message | _ReactionWakeMessage]`.

At the end of `_handle_subagent_completion` and
`_handle_background_completion` (the single seam both the in-turn notify path
and the idle-drain path go through), enqueue
`_ReactionWakeMessage(text=<the same summary string the completion
notification carries>)` — i.e. the existing `_format_subagent_completion` /
`_format_background_completion` output. One completion fact, one rendering,
two consumers (UI notification and model wake).

FIFO ordering gives the fix its guarantees: a user message queued before the
completion is answered *first*; after a Stop, pi is genuinely idle (nothing
queued pi-side), so interrupts resolve within the grace window.

### 3. Wrapper: one turn lifecycle, two entry points

`_process_message_queue` gets a `_ReactionWakeMessage` branch. Both user
messages and wakes drive the **same turn lifecycle** (today's
`_run_prompt_turn` body: in-flight request id, interrupt-state reset,
`_turn_in_flight`, escalation cancel, pending-answer finalization, transient
retry), parameterized by the only two genuine differences:

- **Payload**: user turns build the rich payload
  (`_build_prompt_payload`: attachments, images, plan-mode prefix); a wake
  turn sends `{"type": "prompt", "id": <fresh>, "message": wake.text}`.
- **Failure policy and request cycle**: user turns keep the existing
  `_handle_user_message` wrapper (errors serialize to the user / propagate).
  A wake turn wraps in its own minimal cycle — `RequestStarted(fresh id)` →
  consume → `RequestSuccess` — and a turn failure is logged and resolved
  `interrupted=True`; it must never tear down the agent.

No second hand-synced lifecycle: an interrupt during a wake turn behaves
exactly like an interrupt during a user turn because it runs the same code.

### 4. Delete the reaction-window machinery

With no pi-initiated runs left, remove:

- `_note_awaiting_reaction`, `_is_awaiting_reaction`,
  `_awaiting_reaction_count`, `_awaiting_reaction_deadline`,
  `_REACTION_WINDOW_SECONDS`
- `_consume_reaction_turn` and the idle-drain's `ParsedAgentStart` arm,
  replaced by a `logger.warning` tripwire (a pi-initiated run is now a
  protocol violation; see memo for the surviving enforcement).
- The `_is_awaiting_reaction()` term in `_has_background_tasks`.

Update stale prose: `agent_wrapper.py` module docstring + notify-path
comments, `harness.py` capability comments, `subagent.py` / `background.py`
module docstrings, both extension headers.

## Behavior deltas (accepted)

- Reaction ordering: previously a mid-run wake ran *before* queued user
  messages (pi drained followUps first); now user messages win. This is the
  bug fix.
- Wake prompt text changes from the extensions' phrasing to the notification
  summary (`Sub-agents completed: 1 done, 0 failed (of 1).` /
  `Background task completed (exit code 0).\n\n<output tail>`); the model now
  sees the background output tail it previously had no access to.
- A Stop no longer implicitly cancels pending reactions; queued wakes run
  afterwards as individually stoppable, bounded turns (parity with pi's old
  drain behavior, minus the wedge).
- A wake enqueued but not yet serviced is lost on process restart — parity
  with today (pi's in-memory followUp queue is equally lost).

## Test plan

- **Failing-first unit tests** (`agent_wrapper_test.py`):
  - a surfaced sub-agent completion (in-turn and idle-drain) enqueues a
    `_ReactionWakeMessage` whose text is the notification summary;
  - same for a background completion;
  - FIFO order: a user message queued before the completion is serviced
    before the wake;
  - servicing a wake sends the wake prompt RPC bracketed by its own
    `RequestStarted`/`RequestSuccess` cycle;
  - a wake turn hitting `PiCrashError` resolves `interrupted=True` without
    raising (the agent survives).
- **Updated tests** (follow the deletions): the awaiting-reaction /
  auto-resume wrapper tests are rewritten against the wake contract;
  `fake_pi.py` loses `_emit_reaction_turn` + the `reaction` directive arg (the
  wake now arrives as a real prompt fake_pi answers with its default echo);
  `test_pi_sub_agents.py` / `test_pi_background_tasks.py` assert the wake turn
  via the echoed wake text, and gain the ticket's scenario: a user message
  sent while children run is answered independently of (and never blocked by)
  the wake.
- **Real-pi verification (Phase 4)**: run `real_pi/test_sub_agents.py` and
  `real_pi/test_background_tasks.py`; drive the incident shape via
  `/auto-qa-changes` (instant children + long launch run + mid-run user
  message + Stop) and capture before/after evidence. This also verifies the
  memo's precondition that pi never self-starts runs (the tripwire warning
  must not fire).
