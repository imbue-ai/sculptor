# Preserve Terminal-Agent Type When Auto-Creating Agents (SCU-1504) — Architecture

## Executive Summary

The CI Babysitter auto-creates an agent to fix a failed pipeline or a merge
conflict. Today it inherits the workspace's most-recent *model* and chat-config
type, but explicitly skips terminal agents and always falls back to a Claude
chat agent — switching tools out from under a terminal-only user. This change
makes the babysitter (a) inherit the most-recently-used (MRU) agent type
*including* driveable terminal agents, or pin a specific harness, and (b) drive
a registered terminal agent by writing to its PTY through the same guarded path
as `/terminal/input`, rather than the chat message queue. When the MRU is a
terminal that cannot receive automated prompts, the babysitter goes inert and
surfaces a human-readable reason instead of silently spawning Claude.

**Before:** every babysitter spawn is a Claude/Pi chat agent; terminal MRUs are
skipped; delivery is always via the message queue.

**After:** a user-global setting picks **MRU** (default) or a **specific
driveable harness**. The babysitter spawns a chat agent (Claude/Pi, message
queue) *or* its own registered-terminal task (PTY write) *or* nothing at all
(disabled, with a reason surfaced in the PR dropdown).

## Current Architecture

```
PrPollingService ──observer queue──▶ CIBabysitterCoordinator (single consumer thread)
                                          │  _handle_status → classify_transitions
                                          │  PIPELINE_FAILED / MERGE_CONFLICT
                                          ▼
                                     _dispatch_prompt
                                          │  (enabled? retired? paused? at_cap? dedup?)
                                          ▼
                                     _ensure_babysitter_task ──▶ _create_babysitter_task
                                          │                          │
                                          │   _select_model_for_workspace (skips terminals)
                                          │   _select_chat_agent_config_for_workspace
                                          │        └── SKIPS terminals, returns Claude/Pi  ◀── the gap
                                          ▼
                                     task_service.create_message(ChatInputUserMessage)   ◀── message-queue delivery only
                                          ▼
                                     "CI Babysitter" chat Task (persistent)

PR dropdown status:  GET /workspaces/{id}/ci_babysitter
   → _build_ci_babysitter_state_response → coordinator.get_state_snapshot
   → CIBabysitterWorkspaceStateResponse { paused, retry_count, retry_cap, retired, at_cap }
```

Separately, the reverse channel that drives a *registered* terminal agent
already exists for user-facing features (Commit, Create PR, custom actions):

```
POST /api/v1/agents/{id}/terminal/input   (app.py::post_agent_terminal_input)
   Guard 1: RegisteredTerminalAgentConfig AND accepts_automated_prompts
   Guard 2: scan_terminal_signal_state(get_live_messages_for_task) → run_started AND latest ∈ {IDLE, WAITING}
   Guard 3: get_terminal_manager(make_agent_terminal_id(task)) is live
   → terminal_manager.write(bracketed-paste + text [+ CR])
```

The babysitter and this terminal-input path have never met. This feature joins
them.

## Proposed Architecture

```
   CIBabysitterCoordinator._dispatch_prompt   ── delivery-agnostic POLICY (one place) ──
     enabled? retired? paused? at_cap? per-transition dedup?            [REQ-LEGACY-2/3]
                          │
                          ▼
            _resolve_babysitter_agent(workspace, config, txn)
                          │
         ┌────────────────┼──────────────────────────┐
         ▼                ▼                           ▼
   ChatAgent        DriveableTerminal            Disabled(reason)
   (Claude/Pi)      (RegisteredTerminal,         — no spawn; reason
         │           accepts_automated)            surfaced in status
         └───────┬────────┘                         snapshot, return
                 ▼
        _ensure_babysitter_task(state, resolved_config)
                 │   one memoized "CI Babysitter" Task, reused across retries
                 │   (config = chat OR registered-terminal; PTY spawns for terminal)
                 ▼
        deliver_prompt_to_agent(task, prompt_text, config)   ◀── single delivery SEAM
                 │   dispatch on task.input_data.agent_config:
         ┌───────┴───────────────────────────────────┐
         ▼ (chat)                                     ▼ (terminal)
  create_message(ChatInputUserMessage)        offload to worker thread:
  synchronous enqueue, always succeeds          subscribe_to_task → wait for IDLE/WAITING
   [REQ-AGENT-3]                                  signal (deterministic; ~30s backstop)
                                                  then deliver_prompt_to_terminal_agent
                                                  (Guards 1–3, bracketed-paste write)
                                                  [REQ-AGENT-4 / DRIVE-1/2; shared w/ /terminal/input]
                                                  on backstop timeout → transient reason
                                                  [REQ-DRIVE-4 / DISABLE-6]
```

The coordinator gains one decision point (`_resolve_babysitter_agent`) and one
**unified delivery seam** (`deliver_prompt_to_agent`). All babysitter *policy*
is upstream of the seam and delivery-agnostic, so a future behavior fix lands
once. The chat branch is the existing flow, untouched (REQ-LEGACY-2); the
terminal branch is the only genuinely new mechanism.

## Component Deep Dives

### 1. Babysitter-agent setting (`CIBabysitterConfig`)

`CIBabysitterConfig` (`config/user_config.py:86`) gains a field selecting the
babysitter agent (REQ-SET-1), defaulting to MRU (REQ-SET-2). The value is one
of:

- **MRU** — inherit the workspace's most-recent agent type, per-workspace.
- **A specific driveable harness** — Claude, Pi, or a registered terminal agent
  (referenced by its `registration_id`) that has `accepts_automated_prompts`.

**Decided:** the value is a small **typed discriminated model** (a union of
`MRU | Claude | Pi | Registered{registration_id}`) rather than a bare string, so
the harness kind and the `registration_id` are explicit and validated, and the
resolver branches on the type. (Q&A.)

The setting is user-global, like the rest of `CIBabysitterConfig` — not
per-workspace (spec Non-Goals).

### 2. Settings selector (frontend)

`CIBabysitterSettingsSection.tsx` gains a "Babysitter agent" selector (REQ-SET-3)
listing **Most recently used** plus every *currently driveable* harness:

- **Claude** — always present.
- **Pi** — only when `enable_pi_agent` (the experimental-settings toggle,
  `user_config.py:252`) is true. Confirmed in Q&A: Pi appears in the selector
  only when it is enabled in experimental settings, and the resolver treats a
  pinned-Pi-while-disabled as an unavailable harness (REQ-SET-5 / DISABLE-5).
- **Each registered terminal agent** with `accepts_automated_prompts=True`,
  read from `GET /api/v1/terminal-agent-registrations`
  (`load_registrations()`), filtered to the opt-in ones.

Plain `TerminalAgentConfig` and non-opt-in registrations never appear
(REQ-SET-4). The selector commits through the existing `commit()` /
`onSettingChange(UserConfigField.CI_BABYSITTER, …)` whole-object PUT pattern.

### 3. Agent resolution (`_resolve_babysitter_agent`)

Replaces today's `_select_chat_agent_config_for_workspace`
(`coordinator.py:355`, which skips terminals). Returns a small tagged result:

- **`ChatAgent`** carrying `ClaudeCodeSDKAgentConfig | PiAgentConfig`
- **`DriveableTerminal`** carrying a `RegisteredTerminalAgentConfig`
- **`Disabled`** carrying a reason string (and a kind: persistent vs transient)

Resolution:

- **Specific harness set (REQ-AGENT-1):** build that harness regardless of MRU.
  - Claude / Pi → `ChatAgent`.
  - `registered:<id>` → look up the registration via `get_registration(id)`. If
    it still exists *and* `accepts_automated_prompts` → `DriveableTerminal`
    (config stamped exactly as `_agent_config_for_request` does, `app.py:1621`).
    Otherwise → `Disabled` (pinned harness unavailable, REQ-SET-5 / DISABLE-5).
    Pi pinned while `enable_pi_agent` is off → `Disabled` for the same reason.
- **MRU set (REQ-AGENT-2):** take the single most-recent non-babysitter task
  from `_workspace_agent_tasks_most_recent_first` (already terminal-inclusive;
  the *skip* lived only in the two `_select_*` helpers).
  - No prior task → `ChatAgent(Claude)` (REQ-AGENT-6).
  - `ClaudeCodeSDKAgentConfig` / `PiAgentConfig` → `ChatAgent` (REQ-AGENT-3).
  - `RegisteredTerminalAgentConfig` with `accepts_automated_prompts` →
    `DriveableTerminal` (REQ-AGENT-4), re-stamped from the *live* registration
    so a since-revoked opt-in is honored (the task's stamped config could be
    stale — see Risks).
  - plain `TerminalAgentConfig`, or registered without opt-in → `Disabled`
    (REQ-AGENT-5 / DISABLE-2).

Model inheritance (`_select_model_for_workspace`) is unchanged for the chat
path; it has no meaning for terminal agents and is not consulted on the terminal
path.

### 4. Unified prompt delivery (`deliver_prompt_to_agent`) — the single seam

This is the structural keystone. The babysitter's *policy* — every gate
(enabled / retired / paused / at_cap), the per-transition dedup, the retry-count
bookkeeping, the memoized-task reuse, and the lifecycle — lives **once** in
`_dispatch_prompt` and is **delivery-agnostic**. The only thing that differs
between a chat agent and a terminal agent is *how the prompt physically
reaches the agent*. That difference is isolated behind one function:

> `deliver_prompt_to_agent(task, prompt_text, config)` — dispatches on
> `task.input_data.agent_config` and is the *sole* place the chat-vs-terminal
> mechanism diverges.

- **Chat branch (Claude / Pi):** exactly today's flow — select the model
  (`_select_model_for_task`), build a `ChatInputUserMessage`, and
  `task_service.create_message` inside the existing transaction. Synchronous,
  effectively always succeeds (it enqueues onto the task's message queue).
- **Terminal branch (driveable registered terminal):** hand off to the terminal
  drive (Component 5) — wait for the deterministic readiness signal, then write
  to the PTY via the shared `deliver_prompt_to_terminal_agent` helper.

Why this matters (the design concern that motivated it): keeping two parallel
dispatch paths would force every future babysitter behavior fix — a new dedup
rule, a retry-cap tweak, a new retire condition — to be written twice and drift.
With the seam, those fixes touch `_dispatch_prompt` once and apply to both agent
kinds for free.

**Honest asymmetry.** The two branches are not symmetric in *failure mode*: chat
delivery is fire-and-forget; terminal delivery is asynchronous and fallible (it
can time out and must run off-thread). The seam unifies the *call site* and all
policy upstream of it — it does not pretend the terminal mechanism is as simple
as an enqueue. `deliver_prompt_to_agent` returns a small result the caller uses
to set/clear the transient disabled reason; the chat branch always returns
"delivered."

### 5. Terminal delivery behind the seam: spawn + signal-driven drive

When resolution is `DriveableTerminal`, `_ensure_babysitter_task` builds the
Task with the `RegisteredTerminalAgentConfig` instead of a chat config. Creating
and starting the task eagerly spawns the agent-scoped PTY and launches the
registered program (`run_terminal_agent_task_v1`, `v1.py:98`), which emits the
`EnvironmentAcquiredRunnerMessage` run anchor and — once the program's status
hooks fire — `IDLE`/`WAITING` signals.

The terminal branch of `deliver_prompt_to_agent` calls a **shared low-level
helper extracted from `post_agent_terminal_input`** —
`deliver_prompt_to_terminal_agent(task, text, submit=True)` — that enforces
Guards 1–3 and performs the bracketed-paste write (REQ-DRIVE-1). The endpoint
becomes a thin caller of the same helper, so the security-sensitive guards can
never drift between the user-facing reverse channel and the babysitter.

A freshly spawned program is not instantly at its prompt, so the terminal branch
waits for it to become ready (REQ-DRIVE-2). **Readiness is a deterministic
event, not a guess:** the program's status hooks post an `IDLE`/`WAITING` signal
(`post_agent_signal` → ephemeral `TerminalAgentSignalRunnerMessage`) — the exact
signal Guard 2 of `/terminal/input` already keys off. The babysitter
**subscribes to the task's message stream** (`task_service.subscribe_to_task`,
which is seeded with current messages on subscribe and then pushed every new
message including ephemeral signals) and blocks until
`scan_terminal_signal_state` over the accumulated messages reports
`run_started AND latest ∈ {IDLE, WAITING}`. It then writes. The wait is bounded
by a **backstop timeout** whose *only* role is the never-ready pathology (hooks
broken, program crashed) — REQ-DRIVE-4: on backstop expiry the babysitter gives
up for this cycle and records a transient reason (REQ-DISABLE-6). In the normal
case the babysitter reacts the instant the signal arrives, so the backstop can
be generous (decided: ~30s) without slowing the happy path.

**Threading.** The readiness wait blocks on the subscription queue until the
signal arrives (or the backstop fires); the coordinator's consumer loop
(`_consumer_loop`) is single-threaded and must stay responsive to other
workspaces' PR updates. The spawn-wait-write sequence therefore runs on a
**worker thread** off `self.concurrency_group`, not inline in `_dispatch_prompt`.
`_dispatch_prompt` ensures the task exists and hands the drive to the worker,
which opens the `subscribe_to_task` context, drains the queue with a per-`get`
timeout that sums to the overall backstop, and writes on the first qualifying
signal. The dedup/retry-count bookkeeping under `self._lock` is applied at
dispatch time (as today), so a slow terminal write cannot double-dispatch.

### 6. Retries reuse the terminal task (REQ-DRIVE-3, REQ-LIFE-1)

`_ensure_babysitter_task` already memoizes `state.babysitter_task_id` and reuses
it across retries. The terminal task follows the same rule: a second failure
(within `retry_cap`) reuses the same "CI Babysitter" terminal task and schedules
another drive — re-waiting for the program to be at its prompt, then writing the
new prompt. This mirrors how chat retries post a new message to the same task.
The task is never auto-archived on cycle resolution; it retires only on
MR merge/close or explicit user action (REQ-LIFE-1), identical to the chat task.

### 7. Disabled-status surfacing (`get_state_snapshot`)

`get_state_snapshot` (`coordinator.py:126`) and the response model
(`CIBabysitterWorkspaceStateResponse`, `app.py:1869`) gain an optional
`disabled_reason` (REQ-DISABLE-3). The PR dropdown (`PrDetailDropdown.tsx`)
renders the reason and reflects the inert state in the enable/pause toggle
(REQ-DISABLE-4).

Crucially the reason is computed **proactively on every status read**, not only
after a failure (REQ-DISABLE-1). That means `get_state_snapshot` must run the
same `_resolve_babysitter_agent` against the workspace's current MRU + config —
which requires a transaction read (today the snapshot is pure in-memory). The
snapshot path therefore opens a transaction and resolves driveability:

- MRU mode, MRU non-driveable → persistent reason (REQ-DISABLE-2).
- Specific harness unavailable → persistent reason (REQ-DISABLE-5).
- Driveable terminal that couldn't be reached this cycle → **transient** reason
  (REQ-DISABLE-6), stored on `CIBabysitterState` by the worker thread and
  cleared once the agent is reached or the cycle resolves
  (PIPELINE_PASSED / merge/close).

Persistent reasons are *derived* (recomputed each read from MRU+config) so they
self-heal when the user fixes the cause; the transient reason is *stored* on the
state because it reflects a runtime event the next read can't re-derive.

## Data Model Changes

- **`CIBabysitterConfig`** (`config/user_config.py`): new field selecting the
  babysitter agent (MRU | specific harness). Default = MRU (REQ-SET-2).
  Backwards-compatible (new field with default), like every other config field.
- **`CIBabysitterState`** (`ci_babysitter_service/state.py`): new field holding
  the current **transient** disabled reason (REQ-DISABLE-6), defaulting to None.
- **`CIBabysitterWorkspaceStateView`** (`coordinator.py`) and
  **`CIBabysitterWorkspaceStateResponse`** (`app.py`): new optional
  `disabled_reason: str | None` (REQ-DISABLE-3). Regenerate TS types
  (`just generate-api`) so the frontend atom/response shape picks it up.
- No DB migration: `CIBabysitterConfig` lives in the user config file, and
  `CIBabysitterState` is in-memory.

## Migration Strategy

None required. The new config field is additive with a default that reproduces
today's behavior for the Claude/Pi case; existing configs deserialize unchanged.
In-memory coordinator state is rebuilt lazily per workspace on first poll, so no
state migration. The only externally visible change for an existing Claude/Pi
user is nil (REQ-LEGACY-2); a terminal-only user newly gets either a driven
terminal babysitter or a disabled-with-reason status instead of a surprise
Claude agent.

## Files to Modify / Create / Delete

**Modify**

- `sculptor/sculptor/config/user_config.py` — add the babysitter-agent field to
  `CIBabysitterConfig` (REQ-SET-1/2).
- `sculptor/sculptor/services/ci_babysitter_service/coordinator.py` — replace
  `_select_chat_agent_config_for_workspace` with `_resolve_babysitter_agent`;
  keep all policy in `_dispatch_prompt` and route the actual send through the new
  `deliver_prompt_to_agent` seam (chat = `create_message`; terminal = the
  signal-driven worker drive); thread the resolved config into
  `_ensure_babysitter_task` / `_create_babysitter_task`; add the
  transient-reason bookkeeping and the overlapping-drive guard; extend
  `get_state_snapshot` to compute `disabled_reason` proactively (REQ-AGENT-*,
  DRIVE-*, DISABLE-*).
- `sculptor/sculptor/services/ci_babysitter_service/state.py` — add the
  transient-reason field (REQ-DISABLE-6).
- `sculptor/sculptor/web/app.py` — extract the guarded PTY-write body of
  `post_agent_terminal_input` into a shared
  `deliver_prompt_to_terminal_agent` helper; add `disabled_reason` to
  `CIBabysitterWorkspaceStateResponse` and `_build_ci_babysitter_state_response`.
- `sculptor/frontend/src/pages/settings/components/CIBabysitterSettingsSection.tsx`
  — add the "Babysitter agent" selector (REQ-SET-3/4).
- `sculptor/frontend/src/pages/workspace/components/PrDetailDropdown.tsx` —
  render `disabledReason`; reflect inert state in the toggle (REQ-DISABLE-4).
- `sculptor/frontend/src/common/state/atoms/userConfig.ts` — atom for the new
  config field.
- Generated API types (`sculptor/frontend/src/api/types.gen.ts` etc.) via
  `just generate-api`.

**Create**

- A home for the shared terminal-delivery helper and the readiness-wait — likely
  a small module under `tasks/handlers/run_terminal_agent/` or `web/`, so both
  `app.py` and the coordinator import it without a layering cycle (see Open
  Questions). Plus the `_resolve_babysitter_agent` result types (can live in
  `coordinator.py` or a sibling module).

**Delete**

- `_select_chat_agent_config_for_workspace` (subsumed by
  `_resolve_babysitter_agent`).

## Alternatives Considered

- **Setting encoding — bare string sentinel** (`"mru" | "claude" | "pi" |
  "registered:<id>"`) vs a **discriminated model**. The string is terse but
  pushes parsing/validation into every reader and makes `registration_id`
  implicit. Rejected in Q&A in favor of the typed discriminated model.
- **Poll-and-guess terminal readiness** (loop on `get_live_messages_for_task`
  with sleeps, or a fixed delay before writing) vs **subscribing to the real
  signal**. Rejected: the program emits a deterministic `IDLE`/`WAITING` signal,
  so `subscribe_to_task` lets the babysitter react exactly when ready — no
  guessing, and the timeout degrades to a pure never-ready backstop.
- **Drive the user's live terminal session** instead of spawning a dedicated
  babysitter task. Rejected by the spec (REQ-AGENT-4): hijacking the user's
  session is intrusive and races their own typing. The babysitter always owns
  its task.
- **Duplicate the `/terminal/input` guard logic in the coordinator** rather than
  extracting a shared helper. Rejected: two copies of a security-sensitive guard
  drift; a single helper keeps the babysitter and the endpoint identically gated.
- **Two parallel dispatch paths** (a `_dispatch_chat_prompt` and a
  `_dispatch_terminal_prompt`, each with their own gate/dedup/retry handling)
  vs **one policy path with a `deliver_prompt_to_agent` seam**. Rejected the
  split: it would force every future babysitter behavior fix to be written twice
  and risk the two copies drifting. The seam keeps all policy in one place and
  isolates only the delivery mechanism (Q&A-driven).
- **Block the consumer thread on readiness** instead of offloading to a worker.
  Rejected: a slow/never-ready terminal would stall every other workspace's PR
  processing. Offload keeps the coordinator responsive (REQ-DRIVE-4 forbids
  silent spinning).
- **Silently fall back to Claude when the MRU is a non-driveable terminal** (the
  status quo). Rejected by the spec's core motivation — that is exactly the
  tool-switch we are removing (REQ-AGENT-5).
- **Store the disabled reason once at failure time** instead of recomputing each
  status read. Rejected for persistent reasons: REQ-DISABLE-1 requires the
  reason to appear *before* any failure and to self-heal when the user changes
  the MRU or fixes the registration.

## Risks and Mitigations

- **Readiness is deterministic, not guessed.** The babysitter waits for the
  program's real `IDLE`/`WAITING` signal via `subscribe_to_task`, so it never
  writes into an unknown state on the happy path. The residual **TOCTOU** —
  program goes busy between the signal and the write — is inherent and accepted,
  identical to `/terminal/input` today; Guard 2 in the shared helper re-checks
  at write time so a stale signal still can't slip a write through.
- **Backstop never-fires-falsely.** Because the wait is event-driven, the
  backstop timeout only matters when the signal genuinely never arrives (broken
  hooks / crashed program). A generous value (~30s) therefore costs nothing on
  the happy path and simply bounds the pathological case (REQ-DRIVE-4).
- **Stale stamped opt-in.** A task's `RegisteredTerminalAgentConfig` stamps
  `accepts_automated_prompts` at creation; the registration may have since
  flipped it off. Mitigation: on the MRU terminal path, re-resolve against the
  *live* registration (`get_registration`) before treating it as driveable, and
  Guard 1 in the shared helper re-checks at write time.
- **Consumer-thread starvation from terminal waits** — mitigated by offloading
  the wait/write to a worker thread (Component 4).
- **Snapshot read cost.** Computing `disabled_reason` per status read now opens a
  transaction and resolves the MRU. The PR popover fetches one workspace at a
  time (see `ciBabysitterFetchSeqAtom` note), so cost is bounded; if it proves
  hot, the resolution can be memoized against the MRU task id.
- **Worker/consumer state races.** Retry-count and dedup bookkeeping stays under
  `self._lock` at dispatch time; the worker only writes the transient reason and
  the PTY. No new lock-ordering hazard introduced.
- **Overlapping drives on one terminal task.** A second failure with a *new*
  `pipeline_id` passes dispatch dedup and could start a second worker while the
  first is still waiting for the prompt — two workers racing to write the same
  PTY. Mitigation: a per-state "drive in progress" flag set under `self._lock`
  when a terminal drive is handed to a worker and cleared when it finishes; a new
  dispatch that finds it set coalesces (the in-flight drive will write the latest
  prompt) rather than spawning a second worker. The chat path has no analogue —
  `create_message` just enqueues.
- **Never-ready terminal parks the workspace** — explicitly forbidden
  (REQ-DRIVE-4). Mitigation: the bounded wait gives up for the cycle, sets the
  transient reason, counts against `retry_cap`, and retries on the next failure.

## Testing Strategy

- **Coordinator unit tests** (`coordinator_test.py`) for `_resolve_babysitter_agent`
  across the matrix: MRU Claude/Pi/driveable-terminal/plain-terminal/non-opt-in/
  none; specific-harness Claude/Pi/registered-available/registered-revoked
  (REQ-AGENT-*, REQ-SET-5). FakeClaude-style fixtures already model workspace
  agent tasks in this file.
- **Terminal-drive tests:** a fake terminal task that reaches IDLE delivers the
  prompt via the shared helper; one that never reaches its prompt times out,
  records the transient reason, and counts against `retry_cap` (REQ-DRIVE-2/4).
  Assert retries reuse the same task id (REQ-DRIVE-3, REQ-LIFE-1).
- **Shared-helper tests:** the extracted `deliver_prompt_to_terminal_agent`
  enforces Guards 1–3 (existing `/terminal/input` test coverage should be
  re-pointed at / re-used for the helper).
- **Status-snapshot tests:** `disabled_reason` is populated proactively for a
  non-driveable MRU and clears when the MRU becomes driveable or the cycle
  resolves (REQ-DISABLE-1/6).
- **Frontend integration** (`tests/integration/frontend/test_ci_babysitter.py`):
  the selector lists only driveable harnesses (REQ-SET-3/4); the PR dropdown
  shows the disabled reason and inert toggle (REQ-DISABLE-2/4).

## Open Questions

Resolved during Q&A (kept here as a record):

- **Setting encoding** (REQ-SET-1) — typed discriminated model, not a string
  sentinel.
- **Readiness** (REQ-DRIVE-2) — event-driven via `subscribe_to_task` on the real
  `IDLE`/`WAITING` signal; the timeout is a ~30s never-ready backstop only, not a
  guessed readiness delay.
- **Stale opt-in** — re-resolve against the live registration on the MRU path.
- **Pi in the selector** — listed only when `enable_pi_agent` (experimental
  settings) is on; pinned-Pi-while-off is treated as unavailable.

Resolved by analysis (no user input needed):

- **Home of the shared delivery helper** — the coordinator already imports from
  the web layer (`web.derived`, `web.pr_polling_service`, `web.data_types`), so
  placing `deliver_prompt_to_terminal_agent` in the web layer and importing it
  from both `app.py` and the coordinator introduces no new dependency cycle. Plan
  picks the exact module.

Remaining (Plan may pick these up):

- None blocking. The exact backstop constant and per-`get` poll granularity are
  implementation tuning within the decided ~30s envelope.
