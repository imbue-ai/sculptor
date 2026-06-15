# Task 11.1: Background tasks — turn it ON for pi (`supports_background_tasks`)

> **SCOPE REVERSAL (Danver, 2026-06-13).** This capability was originally
> deferred (feasibility verdict (iv) — "blocked on pi-core"). That deferral is
> **withdrawn**: we are pursuing it now. The original premise was that only a
> throwaway extension *simulation* existed; since then the **sub-agents
> extension** landed (`sculptor/sculptor/agents/pi_agent/extensions/sculptor_subagent.ts`
> + `subagent.py`), proving that spawning child `pi` processes and streaming
> their async progress while the parent run proceeds is a real, shipped
> Sculptor-pinned-extension mechanism. See `feasibility.md` §11 "REVERSAL".
> pi-core remains immutable — **extensions only**.

## Goal

Flip `supports_background_tasks` to `True` for pi, delivering BOTH:

1. **Backgrounded tool calls** — a long-running tool (e.g. `bash`/Exec) can be
   run in the background: the agent turn does not block on it, and Sculptor
   surfaces it as a background task that later reports completion.
2. **Subagents / Tasks in flight while the main thread stays interactive** —
   the user can send messages to the main pi agent while spawned
   subagents/tasks are still running, instead of being blocked until they
   finish.

## Requirements addressed

REQ-CAP-BACKGROUND-TASKS (now pursued, not deferred); REQ-CAP-ALL-1..7;
REQ-EXT-1..5 (any new/extended extension); REQ-TEST-1/2/4. The reversal itself
is recorded in `feasibility.md` §11.

## Background

Sculptor's pi harness (`sculptor/sculptor/agents/pi_agent/`) wraps the pinned
`pi --mode rpc` CLI. **Base your work on the current `sculptor-oss/main`** (the
open-source remote `imbue-ai/sculptor`) — 10 of 11 target capabilities have
already merged there (interruption, tool rendering, session resume, context
reset, compaction, backchannel, skills, image input, file attachments,
sub-agents). This is the last capability.

**Claude's background-task contracts (mirror these — they are harness-agnostic):**
- `BackgroundTaskStartedAgentMessage` and `BackgroundTaskNotificationAgentMessage`
  (`sculptor/sculptor/interfaces/agents/agent.py:369,379`), emitted by Claude's
  output processor (`agents/default/claude_code_sdk/output_processor.py:648`
  start, `:674` notification).
- `pending_background_task_ids: frozenset[str]` on the task view
  (`sculptor/sculptor/web/derived.py:801`) — drives the frontend's
  background-task surface (see `frontend/src/common/state/atoms/tasks.ts`,
  `taskDetailReducers.ts`, `hooks/useTaskHelpers.ts`).
- The base tranche already added the gate substrate for this flag:
  `taskSupportsBackgroundTasksAtomFamily` (`tasks.ts`) +
  `useTaskSupportsBackgroundTasks` (`useTaskHelpers.ts`). The flag is currently
  `False` on `PiHarness.capabilities()`
  (`sculptor/sculptor/agents/pi_agent/harness.py`).

**The mechanism precedent (your starting point):** the sub-agents tranche's
`subagent.py` parses structured per-child progress (`parse_subagent_progress`,
`build_child_content_blocks`) streamed over a parent tool's
`tool_execution_update.partialResult`, and `sculptor_subagent.ts` spawns each
child as its own `pi` process. Study both in full — they demonstrate the spawn +
async-progress + lifecycle pattern you will adapt for backgrounding. The pi RPC
facts (turn boundary = `agent_end`; `follow_up`/`steer` queue commands;
`pi.sendUserMessage(..., {deliverAs:"followUp"})` and `ctx.ui.notify` for
out-of-band injection) are characterized in
`agent_docs/pi-basic/pi-0.78.0-rpc.md` (readable from the spec workspace — see
"Source").

## Source of this spec (agent_docs not yet on main)

The pi-capabilities cycle docs are **not on `sculptor-oss/main`** (the migration
PR is unmerged). Read them from the spec workspace
(`sculpt workspace show ws_01ktse3t2aemva4m9ge4ftz7f2`) at the absolute path
`/Users/danver/.sculptor/workspaces/5e33186403e74c98b43673c92c995f89/code/agent_docs/pi-capabilities/`:
`goals.md`, `requirements.md`, `architecture.md` (§4.10), `feasibility.md` (§11
incl. the REVERSAL). The pi RPC reference is at
`…/code/sculptor/agent_docs/pi-basic/pi-0.78.0-rpc.md`. Do **not** commit any
`agent_docs` files — your MR is background-tasks CODE only.

## Step 0 — re-investigate feasibility (mandatory)

The original verdict predates the sub-agent landing, so **confirm the mechanism
empirically before building**, for EACH of the two behaviours:
1. Can a Sculptor-pinned extension start a tool/command in the background and
   report its lifecycle as structured progress (the `subagent.py` pattern),
   such that Sculptor can emit `BackgroundTaskStarted/Notification` and populate
   `pending_background_task_ids`?
2. Can the main pi run remain promptable while that background work proceeds —
   i.e. can Sculptor accept and dispatch a new user `prompt` (or `follow_up`)
   while a backgrounded tool/subagent is still in flight, and reconcile the
   completion back into the conversation?

Record findings briefly in the MR. If either behaviour hits a genuine pi-core
wall (not merely effort), **PAUSE and ask Danver** (REQ-INV-6) — do not silently
re-defer and do not flip the flag for a half-working simulation.

## Files to modify/create (expected — verify against actual main)

- `sculptor/sculptor/agents/pi_agent/extensions/` — a background-task extension
  (or an extension of the existing subagent one) that backgrounds work and emits
  structured lifecycle progress. REQ-EXT rules apply (in-repo, reviewed, pinned
  with the binary, user-invisible, no secrets, no telemetry).
- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — dispatch the
  extension's background-lifecycle signals into
  `BackgroundTaskStartedAgentMessage` / `BackgroundTaskNotificationAgentMessage`;
  allow the main turn to yield while background work continues, and accept a new
  user message mid-flight (the interactive-main-thread requirement) — the harder
  half; study how the turn loop (`_consume_until_turn_end` /
  `_process_message_queue`) and the message queue interact, and how phase-02
  interruption and phase-06 session state compose with a turn that yields early.
- `sculptor/sculptor/agents/pi_agent/` — a parser for the background-progress
  payload if it differs from `subagent.py`'s (reuse where possible).
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_background_tasks=True`; update the stance comment.
- `harness_test.py`, `agent_wrapper_test.py`, `subagent`-adjacent tests —
  stances + unit coverage for the parser and the dispatch/yield logic.
- `sculptor/sculptor/testing/fake_pi.py` — a directive family to script a
  backgrounded tool/subagent lifecycle (start → in-flight → completion
  notification) deterministically, including a main-thread message arriving
  while background work is "running".
- `sculptor/tests/integration/frontend/` — a gate/behaviour test: under pi the
  background-task surface works and the main thread accepts input mid-background.
- `sculptor/tests/integration/real_pi/test_background_tasks.py` — mirror
  `real_claude/test_background_tasks.py` (and `test_monitor_tool.py` /
  `test_schedule_wakeup.py` where they exercise backgrounding) for the two
  behaviours.

## Testing suggestions

- Unit: progress-payload parsing; start/notification message emission;
  `pending_background_task_ids` population/clearing; the main-turn-yields +
  accepts-new-message path; interruption composes (aborting cancels background
  children — no orphan `pi` processes).
- Integration (fake_pi): scripted background tool + a main-thread message sent
  while it runs → both resolve; the background surface renders under pi.
- Real (`just test-real-pi`): the new `test_background_tasks.py` end-to-end with
  a real backgrounded command and a real interactive message mid-flight. Run the
  FULL real_pi suite + a real-claude rerun for the evidence bundle. To get API
  keys you MAY `source ~/.anthrocreds` (do NOT read its contents); activate node
  via nvm from `~/.nvm` before `just` recipes.

## Gotchas

- pi-core immutable — extensions only. A pinned-version bump needs Danver's
  explicit permission BEFORE bumping.
- No-orphan rule: a backgrounded child `pi` process must be killed on
  interrupt/stop and on agent shutdown (compose with phase-02 interruption;
  reuse the subagent extension's abort/child-kill handling).
- Don't double-count: a backgrounded subagent is both a sub-agent render AND a
  background task — keep the `parent_tool_use_id` sub-agent grouping working
  while also emitting the background-task lifecycle; don't render the same work
  twice or leave a `pending_background_task_id` that never clears.
- The interactive-while-running requirement changes turn semantics: be precise
  about when the main turn's `RequestSuccess` is emitted vs when background work
  completes — the user must be unblocked without the conversation losing the
  eventual completion notification.

## Verification checklist

- [ ] Step-0 feasibility findings recorded; no silent re-deferral; any pi-core
      wall escalated to Danver (REQ-INV-6).
- [ ] A backgrounded tool call runs without blocking the turn; start +
      completion surface via `BackgroundTask*` messages and
      `pending_background_task_ids`.
- [ ] The user can message the main pi agent while a subagent/task is in flight;
      the completion is reconciled back into the conversation.
- [ ] Interrupt/stop and shutdown leave no orphan background `pi` processes.
- [ ] `supports_background_tasks=True`; stance tests updated; no fail-open / no
      dead affordance.
- [ ] REQ-EXT checklist for any new/extended extension (in-repo, pinned set,
      user-invisible, no secrets/telemetry).
- [ ] Integration tests + new `real_pi/test_background_tasks.py`; FULL `real_pi/`
      suite green at merge; deterministic gates single-run green; real-claude
      rerun green.

## Branch / PR conventions

Own workspace on `danver/pi-capabilities-background-tasks`, **rooted on
`sculptor-oss/main`** (the new base — local `main` is the stale frozen private
tip; fetch `sculptor-oss` and reset onto `sculptor-oss/main` first). `just
rebuild` on the fresh worktree. Commit rules: `just format` / `check` /
`test-unit` when committing; trailer `Co-authored-by: Sculptor <sculptor@imbue.com>`.
Push ONLY your branch to `sculptor-oss`; open a PR against `imbue-ai/sculptor`
(base `main`) with a world-readable description per the Public Visibility rules,
noting the spec lives in the spec workspace / unmerged migration PR, ending with
"(Sent by Claude)" on its own final line; announce per the post-mr-to-slack
skill. Never force-push; never merge your own PR.
