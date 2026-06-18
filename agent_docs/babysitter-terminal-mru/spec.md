# Preserve Terminal-Agent Type When Auto-Creating Agents (SCU-1504)

## Overview

When Sculptor automatically creates an agent on the user's behalf — today
this is the **CI babysitter**, which spawns an agent to fix a failed
pipeline or resolve a merge conflict — it should respect the kind of agent
the user has been working with in that workspace.

Right now the babysitter inherits the workspace's most-recent agent *model*
and chat-config type (Claude vs Pi), but it **explicitly skips terminal
agents** (`coordinator.py::_select_chat_agent_config_for_workspace`). A user
who works exclusively with terminal agents gets a Claude chat agent spawned
into their workspace when CI fails — switching tools out from under them.

The motivation: if a user is intending to use their terminal agents, we
should be diligent about preserving that behavior. Auto-created agents should
prefer the most-recently-used (MRU) agent type, including terminal agents.

### Investigation: is the "can't deliver a prompt" constraint real?

Partly, and it's narrower than "all terminal agents." You can always write
bytes to a PTY, but that is not the same as delivering a prompt:

- **Plain `TerminalAgentConfig`** is a bare login shell. There is no AI
  program listening; written text executes as shell commands. A prompt
  cannot be delivered. (Constraint is real.)
- **`RegisteredTerminalAgentConfig`** runs a TUI program (e.g. claude-code).
  It *can* receive a pasted prompt, but only when the registration opted in
  via `accepts_automated_prompts=True` (defaults `False`), the program is at
  its prompt (`IDLE`/`WAITING` status signal, which requires the
  registration's status hooks), and the PTY is live. The existing
  `/terminal/input` endpoint already enforces these guards.
- **Delivery-channel mismatch.** The babysitter delivers its prompt today by
  putting a `ChatInputUserMessage` on the task message queue
  (`coordinator.py`). Terminal agents have no message-queue subscription —
  their handler only keeps a PTY alive. Driving a terminal agent therefore
  needs a PTY-write path, not the message queue.

**Conclusion:** the babysitter can reliably drive a registered terminal agent
that opted into automated prompts, and only that. Plain terminals and
non-opt-in registered agents cannot be driven.

### Approach: a configurable agent choice (not hardcoded MRU)

Rather than hardcode "always inherit the MRU type," the CI Babysitter settings
page gains a setting that lets the user choose which agent the babysitter uses:

- **Most recently used (MRU):** inherit the type of the workspace's most-recent
  agent, per-workspace.
- **A specific harness:** always use one chosen agent across all workspaces.

Because the babysitter must deliver a prompt, a *specific-harness* choice can
only ever be a **driveable** agent: Claude, Pi, or a registered terminal agent
with `accepts_automated_prompts=True`. Plain terminals and non-opt-in
registered agents never appear as explicit choices — there is no way to drive
them.

Behavior by setting:

- **Specific harness chosen:** the babysitter always spawns and drives that
  agent, regardless of the workspace's MRU. For a registered terminal agent
  this means spawning its own task (same registration) and writing the fix-CI
  prompt to the PTY through a delivery path gated like `/terminal/input`.
- **MRU chosen, MRU is driveable** (Claude / Pi / opt-in registered terminal):
  spawn and drive that type. For a registered terminal agent, spawn its own
  task and drive it via the PTY.
- **MRU chosen, MRU is a non-driveable terminal** (plain shell, or registered
  without opt-in): the babysitter does **not** spawn anything for that
  workspace. It marks itself disabled and surfaces *why* in the PR dropdown's
  babysitter status, so the user understands it can't act on their workflow.

In the driveable terminal case the babysitter spawns its **own** dedicated task
(consistent with today's "CI Babysitter" task pattern) rather than hijacking
the user's live session.

## User Scenarios

### Claude/Pi user — unchanged (REQ-AGENT-3, REQ-LEGACY-2)
A user works with Claude in a workspace. A pipeline fails. The babysitter
(setting = MRU) resolves the MRU as Claude, spawns its dedicated "CI
Babysitter" chat task, and delivers the fix-CI prompt via the message queue —
exactly as today. Same flow if the MRU is Pi.

### Driveable terminal user — babysitter drives their tool (REQ-AGENT-4, REQ-DRIVE-1)
A user works with a registered terminal agent that opted into automated
prompts (e.g. a claude-code registration). A pipeline fails. The babysitter
(MRU) sees the MRU is a driveable registered terminal agent and spawns its own
task using the same registration. Once that agent's program has started and
reached its prompt (`IDLE`/`WAITING`), the babysitter writes the fix-CI prompt
to its PTY — gated exactly like `/terminal/input`. The user's own tool fixes
CI. A second failure (within the retry cap) reuses the same babysitter task and
writes a new prompt once it is again at its prompt (REQ-DRIVE-3).

### Plain-terminal user — babysitter goes inert and says why (REQ-AGENT-5, REQ-DISABLE-1)
A user works only with plain terminal agents (bare shells). The PR dropdown's
babysitter status shows a disabled state with a reason: the most-recent agent
is a terminal that can't receive automated prompts. No agent is spawned on
failure. The reason hints at the remedy: pick a specific harness in settings,
or use a chat / opt-in terminal agent (REQ-DISABLE-2).

### Power user pins a specific harness (REQ-AGENT-1, REQ-SET-3)
A user opens CI Babysitter settings and changes "Babysitter agent" from "Most
recently used" to a specific driveable harness (Claude, Pi, or a registered
terminal agent that accepts automated prompts). From then on, every workspace's
babysitter uses that harness regardless of its MRU — and the disabled state
above no longer applies, because the chosen harness is always driveable.

### Settings selector (REQ-SET-3, REQ-SET-4)
On the CI Babysitter settings page the user sees a "Babysitter agent" selector
listing "Most recently used" plus each currently driveable harness. Plain
terminals and non-opt-in registered agents never appear — they cannot be
driven.

## Requirements

### Setting & configuration (`REQ-SET-*`)
- **REQ-SET-1:** The user-global `CIBabysitterConfig` MUST gain a field that
  selects the babysitter agent: either "most recently used" or a specific
  driveable harness identifier.
- **REQ-SET-2:** The setting MUST default to "most recently used."
- **REQ-SET-3:** The CI Babysitter settings page MUST present a selector
  offering "Most recently used" plus every currently driveable harness: Claude,
  Pi (when pi-agent is enabled), and each registered terminal agent with
  `accepts_automated_prompts=True`.
- **REQ-SET-4:** Plain `TerminalAgentConfig` agents and registered agents
  without `accepts_automated_prompts` MUST NOT be selectable as a specific
  harness.
- **REQ-SET-5:** If a pinned specific harness becomes unavailable (pi-agent
  disabled, the registration deleted, or `accepts_automated_prompts` flipped
  off), the babysitter MUST go disabled with a reason (see REQ-DISABLE-5) — it
  MUST NOT silently fall back to MRU or Claude.

### Agent selection at spawn time (`REQ-AGENT-*`)
- **REQ-AGENT-1:** When the setting is a specific harness, the babysitter MUST
  spawn and drive that harness for every workspace, ignoring workspace MRU.
- **REQ-AGENT-2:** When the setting is MRU, the babysitter MUST resolve from the
  workspace's single most-recent non-babysitter agent — it MUST NOT skip
  terminal agents to fall through to an older chat agent (the current
  `_select_chat_agent_config_for_workspace` behavior changes here).
- **REQ-AGENT-3:** When the resolved agent is Claude or Pi, the babysitter MUST
  behave as today (spawn the chat task, deliver via the message queue).
- **REQ-AGENT-4:** When the resolved agent is a driveable registered terminal
  agent, the babysitter MUST spawn its **own** task using the same registration
  and drive that task — it MUST NOT write into the user's existing session.
- **REQ-AGENT-5:** When the resolved agent (MRU mode) is a non-driveable
  terminal agent, the babysitter MUST NOT spawn a task for that workspace.
- **REQ-AGENT-6:** When a workspace has no prior non-babysitter agent, the
  babysitter MUST fall back to Claude.

### Driving a terminal agent (`REQ-DRIVE-*`)
- **REQ-DRIVE-1:** The babysitter MUST deliver its prompt to a registered
  terminal agent by writing to that agent's PTY, gated identically to
  `/terminal/input`: the config is a `RegisteredTerminalAgentConfig` with
  `accepts_automated_prompts`, the current run's latest signal is `IDLE` or
  `WAITING`, and a live PTY exists.
- **REQ-DRIVE-2:** The babysitter MUST wait for a freshly-spawned terminal
  agent to reach `IDLE`/`WAITING` before writing (the program must start up
  first), within a bounded window.
- **REQ-DRIVE-3:** Retries (further failures up to `retry_cap`) MUST reuse the
  same babysitter terminal task, writing a new prompt when it is again at its
  prompt — mirroring how chat-agent retries post new messages today.
- **REQ-DRIVE-4:** If a terminal agent that was expected to be driveable cannot
  be reached within the readiness bound (PTY never ready, hooks silent, program
  crashed), the babysitter MUST surface a transient reason (REQ-DISABLE-6),
  give up for the current cycle, and retry on the next CI failure signal
  (counting against `retry_cap`). It MUST NOT spin silently and MUST NOT park
  the workspace permanently on a one-off hiccup.

### Spawned terminal-task lifecycle (`REQ-LIFE-*`)
- **REQ-LIFE-1:** A babysitter-spawned terminal task MUST follow the same
  lifecycle as today's chat babysitter task: it is reused across retries, it
  surfaces as a "CI Babysitter" tab, and it stays alive until the user
  explicitly acts on it or it retires on MR merge/close. The babysitter MUST
  NOT auto-archive it when a CI cycle resolves.

### Disabled status surfacing (`REQ-DISABLE-*`)
- **REQ-DISABLE-1:** In MRU mode, whenever a workspace's MRU is non-driveable,
  the PR dropdown babysitter status MUST show a disabled state with a
  human-readable reason. This MUST be computed per-workspace on every status
  read (proactively, not only after a failure).
- **REQ-DISABLE-2:** The reason MUST explain that the most-recent agent is a
  terminal that can't receive automated prompts, and SHOULD hint at the remedy.
  Proposed copy: *"Your most-recent agent is a terminal that can't receive
  automated prompts, so the CI Babysitter can't act here. Pick a specific
  agent in CI Babysitter settings, or use a chat or prompt-enabled terminal
  agent."*
- **REQ-DISABLE-3:** The babysitter status view exposed to the frontend
  (`CIBabysitterWorkspaceStateView` / `CiBabysitterWorkspaceStateResponse`) MUST
  carry a new optional disabled-reason field.
- **REQ-DISABLE-4:** In the disabled state the dropdown's enable/pause toggle
  SHOULD reflect that the babysitter is inert, not that it will act.
- **REQ-DISABLE-5:** When a pinned specific harness is unavailable (REQ-SET-5),
  the status MUST show a disabled reason naming the problem. Proposed copy:
  *"The CI Babysitter's selected agent is no longer available. Choose another
  in CI Babysitter settings."*
- **REQ-DISABLE-6:** When a driveable terminal agent can't be reached for the
  current cycle (REQ-DRIVE-4), the status MUST show a transient reason. Proposed
  copy: *"Couldn't reach the terminal agent's prompt; will retry on the next
  failure."* This reason MUST clear once the agent is reached or the cycle
  resolves.

### Preserve existing behavior (`REQ-LEGACY-*`)
- **REQ-LEGACY-1:** User-initiated agent creation (the `+` button / Cmd+K MRU
  via `lastUsedAgentType`) MUST remain unchanged.
- **REQ-LEGACY-2:** The Claude/Pi chat-agent babysitter path (message-queue
  delivery, model inheritance, retry cap, pause, retired) MUST remain
  unchanged.
- **REQ-LEGACY-3:** Existing per-workspace pause and global `enabled` controls
  MUST continue to work and compose with the new setting.

## Non-Goals

- This does NOT change user-initiated agent creation. The frontend already
  preserves the MRU agent type (including terminal/registered) via
  `lastUsedAgentType` for the `+` button / Cmd+K. Scope is auto-creation.
- This does NOT make plain terminal agents or non-opt-in registered agents
  driveable. Driveability remains gated by `accepts_automated_prompts`.
- This does NOT introduce per-workspace babysitter configuration; the agent
  setting is user-global like the rest of `CIBabysitterConfig`.

## Open Questions

- **Readiness bound value (REQ-DRIVE-2):** the exact timeout for a
  freshly-spawned terminal agent to reach its prompt is a tuning detail for the
  architecture/plan phase (the never-ready *behavior* is settled in REQ-DRIVE-4).
- **Reason copy:** the proposed disabled-reason strings (REQ-DISABLE-2/5/6) are
  starting points; final wording can be tightened during implementation.
