# Terminal Agents — Architecture

## Executive Summary

Terminal agents add a third kind of agent alongside the natively-parsed
Claude and pi harnesses: an agent whose main panel is a **terminal** (a
persistent PTY) instead of a chat. Two flavors ship — a *plain Terminal*
(a bare shell) and *registered terminal agents* (a predetermined program,
e.g. the Claude Code TUI, launched inside that shell with optional rich
integration). Sculptor never parses a terminal agent's output; instead the
running program reports coarse status (`busy`/`idle`/`waiting`),
file-change, and session-id events to a local HTTP signal API, which drives
the same tab indicators and diff-refresh that native agents use.

**Before:** an agent is always a chat-stream harness (Claude or pi),
selected per-workspace via the DELIBERATE-TEMPORARY `Workspace.harness`
column; the main panel is always the chat interface; status is derived
entirely by parsing the agent message stream.

**After:** agent type is a **per-agent** choice made at the `+` button
(Claude / pi / Terminal / each registered terminal agent). A terminal
agent is still a `Task` carrying an `AgentTaskInputsV2`, but with a new
terminal-flavored `AgentConfig`; it runs through a dedicated task handler
that spawns a PTY rather than the chat loop, presents a terminal panel via
the capability-gate system, and derives status from signal events.

---

## Current Architecture

```
                          ┌─────────────────────────────────────────────┐
   + button (AgentTabs)   │ create_workspace_agent / start_task (app.py)│
   one-click create  ───► │   agent_config = _agent_config_for_workspace│
                          │     (reads Workspace.harness — TEMPORARY)   │
                          └───────────────────┬─────────────────────────┘
                                              │ Task(input_data=AgentTaskInputsV2(
                                              │        agent_config=Claude|Pi))
                                              ▼
                          ┌─────────────────────────────────────────────┐
   task dispatch          │ tasks/api.py run_task: match input_data      │
   (tasks/api.py)         │   AgentTaskInputsV2 → run_agent_task_v1       │
                          └───────────────────┬─────────────────────────┘
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ run_agent_task_v1 (chat loop)                                          │
   │  • acquire environment (agent_environment_context)                     │
   │  • WAIT for initial chat message  ◄── blocks prompt-less agents        │
   │  • create_agent_for_run(context) → Claude/Pi/Hello Agent (registry)    │
   │  • poll agent / pump messages / handle AskUserQuestion / sync artifacts│
   │  • on_diff_needed → workspace_service.maybe_refresh_workspace_diff      │
   └──────────────────────────────────────────────────────────────────────┘

   Harness seam:  Harness (name, capabilities()) ── get_harness_for_config ──► Claude/Pi/Hello
   Capabilities flow to FE via CodingAgentTaskView.harness_capabilities (computed_field).

   Status:  CodingAgentTaskView.status walks the message stream
            (RequestStarted/Complete, AskUserQuestion, …) → TaskStatus → tab dots.

   Terminal infra (workspace-scoped, NOT task-scoped):
   ┌─────────────────────────────────────────────────────────────────────┐
   │ LocalTerminalManager registry, keyed by make_terminal_id(env_id,idx) │
   │  • SpawnedPtyProcess: posix_spawn helper → pty.fork → login shell -l  │
   │  • persists across WS disconnect; torn down on workspace teardown     │
   │  WS route: /api/v1/workspaces/{id}/terminal/{index}/ws (app.py)       │
   │  FE client: useTerminal.ts (xterm.js) + TerminalPanel.tsx             │
   └─────────────────────────────────────────────────────────────────────┘
```

Key facts the design builds on:

- **`AgentConfig` is already per-task.** `AgentTaskInputsV2.agent_config`
  (`database/models.py`) holds an `AgentConfigTypes` discriminated union
  (`HelloAgentConfig | ClaudeCodeSDKAgentConfig | PiAgentConfig`). The
  per-workspace `Workspace.harness` column and `_agent_config_for_workspace`
  (`web/app.py:1576`) only pick *which* config to stamp at creation time —
  they are the DELIBERATE-TEMPORARY shim this feature removes.
- **Harness registry** (`agents/harness_registry.py`) is the single place
  that maps a config → `Harness` (`get_harness_for_config`) and a run
  context → `Agent` (`create_agent_for_run`). A new harness/agent = one
  import + one `case` in each function.
- **Capability gate** (`interfaces/agents/harness.py` `HarnessCapabilities`
  + FE `useCapabilityGate.ts`/`CapabilityGate.tsx` + `useTaskHelpers.ts`
  hooks). Each capability is a bool with *no default*, surfaced per-task via
  `CodingAgentTaskView.harness_capabilities`.
- **PTY infrastructure** (`local_terminal_manager.py`,
  `spawned_pty_process.py`): a fork-safe PTY that runs a **login shell**,
  persists across WebSocket disconnect, and is registered in a global
  map keyed by `(environment_id, terminal_index)`. The shell env is scrubbed
  of `SCULPT_*`/`SCULPTOR_*`/`SESSION_TOKEN` and then re-augmented from
  `extra_env`.
- **Task runner blocks on an initial chat message** before it starts the
  agent (`wait_for_initial_message_and_process_queue` in
  `tasks/handlers/run_agent/setup.py`) — so a terminal agent cannot reuse
  `run_agent_task_v1` unchanged.

---

## Proposed Architecture

```
   + split button (AgentTabs)            ┌──────────────────────────────────────┐
   ─ plain click: last-used type         │ CreateAgentRequest.agent_type         │
   ─ chevron: [Claude] [pi*] [Terminal]  │   Claude | Pi | Terminal | <reg id>   │
     [<registered agents…>]   ──────────►│ create_workspace_agent / start_task   │
   (* pi only if ENABLE_MULTI_HARNESS)   │  agent_type → AgentConfig (factory)   │
                                         └──────────────────┬───────────────────┘
                                                            ▼  AgentTaskInputsV2(agent_config=
                                                            │    Terminal | RegisteredTerminal)
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │ tasks/api.py run_task: AgentTaskInputsV2 case branches on agent_config type:  │
   │   Claude/Pi/Hello  → run_agent_task_v1 (unchanged chat loop)                  │
   │   Terminal/Reg     → run_terminal_agent_task_v1   (NEW)                       │
   └──────────────────────────────────┬──────────────────────────────────────────┘
                                       ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │ run_terminal_agent_task_v1 (NEW, no chat loop)                               │
   │  • acquire environment (reuse agent_environment_context)                      │
   │  • emit EnvironmentAcquiredRunnerMessage (wires workspace_id, diff path)      │
   │  • spawn an agent-scoped PTY (terminal manager keyed by task id)              │
   │      – inject signal-API env (endpoint, agent id, session token) + SCULPT_*  │
   │      – plain Terminal: just the login shell                                   │
   │      – registered: write the launch (or resume) command into the shell        │
   │  • loop: watch shell liveness + shutdown_event; periodic diff refresh (3s)    │
   │  • teardown: stop the PTY                                                      │
   └──────────────────────────────────────────────────────────────────────────────┘

   Signal API (NEW)              Status driver (NEW)               FE presentation
   ┌────────────────────┐        ┌───────────────────────┐        ┌────────────────────────┐
   │ POST /api/v1/agents│        │ signal → synthetic     │        │ supports_chat_interface│
   │   /{id}/signal     │ ─────► │  runner message;       │ ─────► │  = false →             │
   │  busy|idle|waiting │        │  status branch reads   │        │ render TerminalPanel   │
   │  files-changed     │ ─┐     │  latest → tab dots     │        │ (agent PTY route)      │
   │  session-id        │  │     └───────────────────────┘        └────────────────────────┘
   │ (sculpt signal …)  │  └─► files-changed → maybe_refresh_workspace_diff
   └────────────────────┘     session-id    → persisted on task (for resume)

   Status: signal → synthetic runner message; status branch reads latest
           signal since the last run-start marker (run-scoped — resets on
           backend restart so a stale 'waiting' is never resurrected).
   FE presentation: harness_capabilities.supports_chat_interface = false →
           render TerminalPanel(agent PTY route) instead of the chat interface.
   Auth: reuse the session token (injected via PTY extra_env); scope by agent id.

   Harness registry: get_harness_for_config gains the Terminal harness
   (all-false chat caps + supports_chat_interface=false). create_agent_for_run
   is NOT extended — the terminal handler owns the PTY directly.

   Registration (NEW): per-registration TOML files under
   ~/.sculptor/terminal_agents/, re-read on menu open. Bundled Claude Code
   example shipped as a copyable sample (absent from the menu until copied).
```

---

## Component Deep Dives

### 1. Agent-type model (REQ-TYPE-1, TYPE-3, TYPE-4)

Introduce two new variants on the existing `AgentConfigTypes` union in
`interfaces/agents/agent.py`:

- `TerminalAgentConfig` — a plain terminal (bare shell). Carries nothing
  beyond the discriminator.
- `RegisteredTerminalAgentConfig` — a registered terminal agent. Carries the
  **registration identity** and the resolved launch parameters needed to run
  and (later) resume the program: the display name, the launch command, the
  optional resume-command template, and integration metadata. Stamped at
  creation time from the registration so the task is self-describing even if
  the registration file later changes.

Because `agent_config` is *already* a per-task field, "agent type is a
per-agent property" (REQ-TYPE-1) needs no schema change to the task — only
the new config variants and a creation path that stamps the chosen one.

`Workspace.harness` (the DELIBERATE-TEMPORARY column) and
`_agent_config_for_workspace` are removed (REQ-TYPE-3). The creation path
takes the agent type from the request instead — see §6. Migration of
existing pi workspaces is discussed in *Migration Strategy*.

Pi remains gated behind `ENABLE_MULTI_HARNESS`; Claude, Terminal, and
registered terminal agents are available to everyone (REQ-TYPE-4). The gate
applies only to which **menu entries** are offered, not to the config union.

### 2. Terminal harness & capability gating (REQ-UI-1, UI-2, UI-3)

Add a `TerminalHarness` (and register it in `harness_registry.py` for the
two new configs) whose `capabilities()` returns the **all-false** chat
capability set — mirroring how `PiHarness` declares its degraded surface.
With every chat capability false, the existing `CapabilityGate` /
`useTaskSupports*` hooks already hide the per-affordance chat controls
(interruption, skills, fast mode, context reset, attachments, …) with no new
conditionals — satisfying REQ-UI-2.

The **top-level panel switch** (render a terminal instead of the entire chat
interface, REQ-UI-1) is coarser than any single affordance gate. **Decision:
a dedicated coarse capability bool** on `HarnessCapabilities` (e.g.
`supports_chat_interface`, False for the terminal harness). The frontend
reads it through the same per-task `CodingAgentTaskView.harness_capabilities`
channel and a `useTaskSupports*` hook, and `WorkspacePage`/`ChatPanelContent`
switch the main panel on it — keeping the decision inside the capability
system (REQ-UI-2) rather than an ad-hoc config-type check in the frontend.
Because `HarnessCapabilities` fields have no defaults, adding this bool forces
every harness constructor to declare its stance (grep-complete).

A terminal agent's tab is an ordinary agent tab (REQ-UI-3): rename, archive/
delete, and status dots all work because the agent is a normal `Task`; only
its status *source* differs (§5).

### 3. Terminal-agent process & PTY lifecycle (REQ-TERM-1, LIFE-1…LIFE-5)

A terminal agent runs through a **dedicated task handler**,
`run_terminal_agent_task_v1`, dispatched from `tasks/api.py run_task` by
branching the existing `AgentTaskInputsV2` case on the `agent_config` type.
A dedicated handler (rather than reusing `run_agent_task_v1`) is required
because the chat handler blocks on an initial chat message before starting
the agent, and carries request/AskUserQuestion/artifact machinery a terminal
agent never uses.

**Construction seam (decision):** the handler owns the PTY **directly** — no
`TerminalAgent` and no `create_agent_for_run` branch for terminal configs.
Only `get_harness_for_config` is extended (it must be, so capabilities and
status resolve — §2, §5); `create_agent_for_run` stays chat-only with a
comment noting terminal configs are handled by `run_terminal_agent_task_v1`
and never reach it (its sole caller, `run_agent_task_v1`, only runs for chat
configs, so an unknown-config raise there is unreachable, not a hazard). A
`TerminalAgent` implementing the message-stream `Agent` ABC was rejected:
because it buys no loop reuse (the dedicated handler is needed regardless),
`pop_messages`/`push_message` would be dead surface that falsely implies
message semantics. See *Alternatives Considered*.

The handler:

1. Acquires the environment via the existing
   `workspace_service.agent_environment_context` and emits
   `EnvironmentAcquiredRunnerMessage` (so the workspace/diff plumbing is
   wired identically to native agents).
2. Spawns an **agent-scoped PTY**. The PTY reuses the
   `LocalTerminalManager` / `SpawnedPtyProcess` machinery (login shell,
   fork-safety, persistence across WS disconnect) but is keyed by **task id**
   rather than `(environment_id, terminal_index)`, so it is addressable as
   *this agent's* terminal and never collides with the workspace terminal
   panel's index space.
3. For a **plain Terminal** (REQ-TERM-1): nothing further — the login shell
   is the agent.
4. For a **registered** agent (REQ-LIFE-5): writes the launch command into
   the shell (as if typed), so the program runs **as a shell job**. When it
   exits (`/exit`, crash) the user lands back at the prompt in the same
   terminal — no auto-relaunch on self-exit — and status returns to neutral.
5. Runs a lightweight loop: keep the task RUNNING while the shell is alive,
   honor `shutdown_event`, and drive the periodic diff refresh (§7).
6. On archive/delete/teardown (REQ-LIFE-2): stops the PTY (terminate the
   shell, close the primary fd, unregister) as part of normal task teardown.

Persistence when the tab is hidden / window closes (REQ-LIFE-1) is inherent:
the PTY is owned by the backend task, not the WebSocket; closing the panel
only drops the WS, exactly as today's terminal panel behaves.

Restart behavior (REQ-LIFE-3, LIFE-4): because terminal agents are normal
idempotent tasks, a backend restart re-queues and re-runs the handler, which
re-creates the PTY. A plain Terminal comes back as a **fresh shell**
(REQ-LIFE-4). A registered agent **auto-relaunches** (REQ-LIFE-3): if a
session id was reported (§4) and the registration has a resume template, the
handler runs the resume command (e.g. `claude --resume <id>`); otherwise it
runs the plain launch command. Scrollback before the restart is not
preserved.

### 4. Signal API & sculpt CLI (REQ-SIG-1, SIG-2, SIG-3, SIG-4)

A **local HTTP event API** on the Sculptor server accepts small JSON events
posted on behalf of a specific terminal agent (REQ-SIG-1). Proposed shape: a
per-agent endpoint (e.g. `POST /api/v1/agents/{agent_id}/signal`) taking
`{event, …}`. The v1 vocabulary is exactly **busy**, **idle**,
**waiting-on-input**, **files-changed**, and **session-id** (REQ-SIG-4);
unknown events are logged and ignored so the contract is forward-compatible.

Sculptor injects the env vars a hook needs to call the API (REQ-SIG-2) into
the terminal session via the PTY's `extra_env` (the same channel the
`SCULPT_*` vars already use): the endpoint/base URL, the agent (task)
identity, and an auth token.

**Auth (decision): reuse the existing session-token mechanism.** The signal
endpoints live under `/api/`, so they are already covered by
`SessionTokenMiddleware` with no new auth code. `SpawnedPtyProcess` scrubs
inherited `SESSION_TOKEN` from the shell but re-adds anything in `extra_env`
(`_scrub_shell_env`: a scrubbed key is then "not in env", so `extra_env`
repopulates it), so reuse is just a matter of injecting the token into the
terminal-agent PTY's `extra_env` — no change to the scrub list. The token
authenticates the *session*; the **agent identity** is supplied separately by
injecting the task id (the existing `SCULPT_AGENT_ID` var), and each signal
call is **scoped by agent id in the path** (`/api/v1/agents/{agent_id}/…`).
Exact variable names are plan-level. The tradeoff — the full local-API token
now lives inside the terminal session — is recorded in *Risks*.

Sculptor ships thin `sculpt` CLI subcommands wrapping the HTTP API
(REQ-SIG-3): `sculpt signal busy|idle|waiting`, `sculpt signal
files-changed`, `sculpt signal session-id <id>`. These read the injected env
vars and POST to the API, so shell hooks (e.g. Claude Code hooks) never
hand-roll HTTP. They slot into the existing typer CLI (`sculptor/cli/`)
beside `sculpt agent` / `sculpt workspace`.

### 5. Status driver (REQ-SIG-5, SIG-6 — spec Open Question)

Native status is derived by `CodingAgentTaskView.status` walking the chat
message stream. Terminal agents have no such stream; their status comes from
signal events and must drive the **same** tab indicators (REQ-SIG-5).

**Decision: signals become synthetic runner messages** on the task, and
`CodingAgentTaskView.status` gains a terminal-harness branch that reads the
latest one. This reuses the entire existing path end-to-end — message
persistence/replay, the SSE `TaskUpdate` stream, `updated_at`/unread
tracking, and `getAgentDotStatus` in `AgentTabs.tsx` — with one new branch
and no new wire format, subscription, or frontend status field. It also
inherits the task's restart/idempotency story (messages already replay on
restart) instead of needing a second, parallel status channel to reconcile.

**Status is run-scoped, not carried across a backend restart.** A signal
reflects the program's *live* state. On a backend restart the task re-runs
and a registered agent is relaunched (possibly via `claude --resume`); the
resumed program's actual state is whatever the relaunched process
re-establishes — in particular we cannot assume a `waiting-on-input` from
before the crash is still pending (a `--resume` typically lands at a ready
prompt, not re-blocked on the prior question). So the status derivation must
**reset to neutral on each (re)start** and only honor signals from the
*current* run; the relaunched program's hooks re-drive it. A convenient
anchor already exists: `EnvironmentAcquiredRunnerMessage` is ephemeral and
re-emitted at every run start, so "the latest status signal since the most
recent run-start marker" resets for free across a restart.

Within a single run the indicators map by kind:

- **busy / idle** → drive the live spinner; a busy→idle transition does
  **not** mark the tab unread.
- **waiting-on-input** → drives the waiting/attention dot while the run is
  live.

The status messages must **survive a frontend reload** (page refresh while
the backend task is alive) so the dot is correct after refresh, but must
**not survive a backend restart** (per the run-scoped invariant above). The
precise message types and the persistent/ephemeral mechanism that achieves
"survives reload, resets on restart" are plan-level — the **invariant** (a
restart never resurrects a stale `waiting`) is the architectural commitment.
Because of this, terminal `waiting` is deliberately **not** modeled as a
persisted content message that would bump `updated_at` across restarts; any
unread/attention treatment for terminal `waiting` is run-scoped.

A **files-changed** event triggers the existing
`maybe_refresh_workspace_diff` path (REQ-SIG-6), reusing `on_diff_needed`;
it is not a status message. A **session-id** event is persisted on the task
for resume (§3) and is likewise not status.

The rejected alternative — a **status field on the task** read directly by
the view — is fewer moving parts at the event layer but introduces a second
status channel parallel to the message stream, with its own restart
reconciliation and no automatic unread/`updated_at` behavior. See
*Alternatives Considered*.

No-signal agents (plain terminals, or registered agents whose integration is
absent/broken) show a calm **neutral status** (REQ-TERM-2): with no signal
ever received, the driver yields the neutral/idle indicator — integration is
purely additive and a broken hook degrades to plain-terminal behavior.

### 6. Agent-type selection UI (REQ-TYPE-2, TYPE-5, TYPE-6)

The `+` button in `AgentTabs.tsx` becomes a **split button** (REQ-TYPE-6): a
plain click instantly creates an agent of the **last-used type** (initially
Claude), preserving today's one-click flow; an attached chevron opens a menu
listing Claude, pi (only when `ENABLE_MULTI_HARNESS`), Terminal, and every
registered terminal agent (REQ-TYPE-2). The menu is populated from the
current registration set, re-read on menu open (REQ-REG-3). The last-used
type is remembered client-side.

`createWorkspaceAgent` / `CreateAgentRequest` gain an **agent-type** field
(the existing `model` field stays for chat agents). The new-workspace flow
(`AddWorkspacePage` / `CreateWorkspaceRequestV2`) offers the same full
agent-type choice for the workspace's first agent, replacing its flag-gated
workspace-harness picker (REQ-TYPE-5); it still creates the first agent with
no initial prompt.

Backend: `start_task` / `create_workspace_agent` map the requested
agent-type → `AgentConfig` via a small factory that replaces
`_agent_config_for_workspace`. For a registered type, the factory resolves
the registration (§8) and stamps a `RegisteredTerminalAgentConfig`.

**Default tab naming (decision):** registered agents default-name from the
registration **display name**; plain terminals get **"Terminal N"** (reusing
the lowest-available-number scheme of `_compute_next_agent_name`). Native
agents auto-name from the conversation, which terminal agents can't; the user
can still rename either (REQ-UI-3).

### 7. Periodic diff refresh for terminal agents (REQ-TERM-3)

Terminal agents keep the workspace diff reasonably fresh via a cheap
**periodic refresh**, akin to the existing ~3s branch polling, calling
`maybe_refresh_workspace_diff`. It is encapsulated (driven from the terminal
handler / a small poller) so it can later be replaced by a file watcher
without touching callers. A `files-changed` signal (§4) provides an
additional, event-driven refresh on top of the periodic one.

### 8. Registration model & bundled Claude Code example (REQ-REG-1, REG-2, REG-3, CLAUDE-1)

Terminal agents are registered via **user-scope declarative config** under
`~/.sculptor/` (REQ-REG-1) — no repo-scope registration and no settings UI
in v1.

**Decision: a directory of per-registration files**,
`~/.sculptor/terminal_agents/`, one **TOML** file per registered agent. Each
file is a declarative registration carrying at minimum a **display name** and
the **launch command**, and optionally a **resume command template**
referencing a persisted session id and integration/hook config (REQ-REG-2).
TOML is chosen for hand-authoring (comments, low punctuation noise); the
loader validates each file into a pydantic registration model and **skips +
logs** invalid files so one bad file can't break the menu. The `+` menu
re-reads the directory on open (REQ-REG-3) — a cheap directory scan that
needs no Sculptor restart, and keeps third-party registrations out of the
core `UserConfig`.

Sculptor ships a **bundled example registration for the Claude Code TUI**
(REQ-CLAUDE-1) as a **copyable sample** (e.g. shipped in a samples location /
documented snippet), *not* auto-installed into `~/.sculptor/terminal_agents/`
— so it is absent from the menu until the user copies it in, satisfying "not
always-present in the menu." It demonstrates the full integration: Claude
Code hook config that calls `sculpt signal …` to report
busy/idle/waiting/files-changed and the session-id for resume.

### 9. Prompt-based features & the CI babysitter (REQ-TYPE-1, TYPE-3, UI-1, UI-2)

Several features act *on behalf of* the user by sending a
`ChatInputUserMessage` into a chat agent's stream: the **Commit button**
(`fileBrowser/CommitButton.tsx` → `chatActions.sendMessage(commit_prompt)`),
the **Create PR/MR button** (`PrButton.tsx` →
`sendMessage("<pr_creation_prompt> …")`), and **custom actions**
(`ActionsPanel.tsx`). A terminal agent has no message stream, so each must
resolve a target. v1 ships **both** tiers below.

**Fallback — gate off (always correct).** When the active agent is a terminal
agent that can't accept an automated prompt, these affordances are **disabled
via `supports_chat_interface`** — the same capability that swaps the panel
(§2), so no ad-hoc per-feature conditionals. Because diffs, branch info, and
the commit bar are workspace-shared (REQ-TYPE-1), the user can still commit /
open a PR by switching to a chat agent in the same workspace, or by acting in
the terminal directly.

**Automated prompts to the terminal agent (in scope for v1).** The missing
piece is only a *reverse* channel: the signal API is program→Sculptor; the
PTY already provides Sculptor→program via `LocalTerminalManager.write` (the
path keystrokes take). For a registered agent whose program accepts typed
prompts (e.g. the Claude Code TUI), writing the prompt text into the agent's
PTY *is* "the user typed this prompt," so the same buttons can drive a
terminal agent. (Note: "automated prompt" here means Sculptor sending the
user's own action prompt on their behalf — unrelated to the
"prompt-injection" security term.) Three guards keep this additive and safe:

1. **Opt-in per registration.** The registration declares
   `accepts_automated_prompts` (carried on `RegisteredTerminalAgentConfig`,
   surfaced on the task view). Plain terminals and non-opt-in registrations
   keep the gated-off fallback — a bare shell would treat the prompt as a
   bogus command.
2. **State-aware.** Send only when the last signal shows the agent at its
   prompt (idle/waiting); never into a bare shell after the program
   self-exited (REQ-LIFE-5, status neutral). The signals already collected
   (§5) provide exactly this.
3. **Atomic multi-line paste.** Multi-line prompts (the PR prompt) are wrapped
   in **bracketed-paste mode** (`ESC[200~…ESC[201~`) so the TUI receives one
   paste and controls submission; a submit key is sent after. Avoids
   premature line-by-line submission.

The write happens **server-side**: `POST /api/v1/agents/{id}/terminal/input`
(session-token auth, scoped by agent id) → terminal manager `write()`. Server
side (vs. the frontend writing its open WS) works regardless of whether the
terminal panel is mounted/focused and keeps the PTY server-owned, consistent
with the signal API. The frontend resolves each button's target: chat agent →
`sendMessage` (today); automated-prompt-capable terminal agent at a prompt →
the terminal-input endpoint; otherwise disabled.

**CI babysitter** (`services/ci_babysitter_service/coordinator.py`) is
separate: it creates its **own** native chat agent task to fix pipelines (it
needs the message stream) and never drives a terminal agent. It currently
selects its config via `workspace.harness` (`coordinator.py:297`), which this
feature **deletes** (REQ-TYPE-3); it must instead create a default chat agent
(Claude, or pi when `ENABLE_MULTI_HARNESS`) directly. This is a required
ripple of the harness-column removal, not optional.

---

## Data Model Changes

- **`interfaces/agents/agent.py`** — add `TerminalAgentConfig` and
  `RegisteredTerminalAgentConfig` to `AgentConfigTypes`. `RegisteredTerminal
  AgentConfig` fields: registration id/name, launch command, resume template
  (optional), integration metadata, and `accepts_automated_prompts` (+
  optional submit/key config) for the automated-prompt path (§9). (Exact
  fields finalized in the plan.)
- **`database/models.py`** — remove `Workspace.harness` (DELIBERATE-TEMPORARY)
  per REQ-TYPE-3 via a schema migration; persist the reported **session id**
  for registered agents (likely on `AgentTaskStateV2`, alongside
  `last_processed_message_id`) for resume (REQ-LIFE-3). No terminal-status
  field is added — status is carried by synthetic runner messages (§5).
- **Registration config** — a pydantic registration model loaded from
  per-registration TOML files in `~/.sculptor/terminal_agents/` (§8), plus the
  bundled Claude Code example shipped as a copyable sample.
- **`interfaces/agents/harness.py`** — add the coarse `supports_chat_interface`
  bool to `HarnessCapabilities` (False for the terminal harness; True for
  Claude/pi/hello). No-default field, so every constructor site is forced to
  declare it.
- **`web/data_types.py`** — `CreateAgentRequest` / `CreateWorkspaceRequestV2`
  gain an agent-type field; drop the `harness` field. New request/response
  types for the signal API and (if needed) listing registrations for the
  menu.
- **Signal events** — a small JSON event schema (`event` + payload); the v1
  vocabulary is closed (busy/idle/waiting/files-changed/session-id) but the
  parser ignores unknown events (REQ-SIG-4).
- **TS types** — regenerate via `just generate-api`; new `ElementIds` for the
  split button, type menu, and terminal panel need regeneration.

---

## Migration Strategy

`Workspace.harness` is DELIBERATE-TEMPORARY and only consulted at agent
*creation* time (`_agent_config_for_workspace`). Existing tasks already
carry their own `agent_config` in `AgentTaskInputsV2`, so removing the
column requires **no per-task data migration** — already-created pi/Claude
agents keep running from their stored config. The only behavioral change is
that *new* agents take their type from the creation request instead of the
workspace column. **Decision: drop the column now** via a schema migration;
the `CreateWorkspaceRequestV2.harness` field and the recent-workspaces
response field that echo it are removed with it.

This is an online change with no compatibility window concern: terminal
agents are additive, and the config union is forward-compatible (older tasks
never carry the new variants).

---

## Files to Modify / Create / Delete

**Create**
- `sculptor/sculptor/tasks/handlers/run_terminal_agent/v1.py` — the terminal-
  agent task handler (PTY spawn, launch/resume, periodic refresh, teardown).
- `sculptor/sculptor/agents/terminal_agent/harness.py` — `TerminalHarness`
  (all-false chat capabilities + presentation marker).
- A small terminal-session helper for the handler (agent-scoped PTY keyed by
  task id, launch/resume command, teardown) — reusing `LocalTerminalManager`/
  `SpawnedPtyProcess`. No `TerminalAgent`/`Agent` implementation is added
  (construction seam = lean; see §3).
- Signal-API route module under `sculptor/sculptor/web/` (e.g.
  `terminal_signal.py`).
- `sculptor/sculptor/cli/…` — `sculpt signal …` subcommands.
- Registration model + loader (under `imbue_core/.../sculptor/` or
  `sculptor/sculptor/services/…`) and the bundled Claude Code example
  registration (+ its hook config) shipped with the app.
- Frontend: a terminal-agent main-panel component (reusing `useTerminal.ts`);
  split-button + type-menu UI in/around `AgentTabs.tsx`.

**Modify**
- `sculptor/sculptor/interfaces/agents/agent.py` — new `AgentConfig` variants.
- `sculptor/sculptor/agents/harness_registry.py` — register terminal harness
  + agent/handler resolution for the new configs.
- `sculptor/sculptor/tasks/api.py` — branch `AgentTaskInputsV2` on
  `agent_config` type → terminal handler.
- `sculptor/sculptor/web/app.py` — agent-type→config factory (replace
  `_agent_config_for_workspace`); agent-scoped terminal WS route; wire signal
  API; drop `harness` usage.
- `sculptor/sculptor/web/derived.py` — terminal-harness branch in
  `CodingAgentTaskView.status` reading the latest signal since the last
  run-start marker (run-scoped, §5).
- `sculptor/sculptor/web/data_types.py` — request/response type changes.
- `sculptor/sculptor/database/models.py` — remove `Workspace.harness`; persist
  session id for registered-agent resume.
- `sculptor/sculptor/services/ci_babysitter_service/coordinator.py` — stop
  reading `workspace.harness` (deleted); create a default chat agent directly
  (§9).
- `sculptor/frontend/.../fileBrowser/CommitButton.tsx`,
  `components/PrButton.tsx`, `panels/ActionsPanel.tsx` — resolve the button
  target: gate off for terminal agents that can't accept an automated prompt;
  route to the terminal-input endpoint for automated-prompt-capable terminal
  agents at a prompt (§9).
- (Automated-prompt path, §9) terminal-input route
  `POST /api/v1/agents/{id}/terminal/input` in `web/app.py` → terminal
  manager `write()` with bracketed-paste wrapping.
- `sculptor/frontend/src/pages/workspace/components/AgentTabs.tsx` — split
  button + type menu.
- `sculptor/frontend/src/pages/workspace/panels/useTerminal.ts` — generalize
  the terminal path (accept an agent-scoped route, not only workspace+index).
- `sculptor/frontend/src/pages/workspace/.../WorkspacePage.tsx` /
  `ChatPanelContent.tsx` — presentation switch (chat vs terminal panel).
- `sculptor/frontend/src/pages/add-workspace/AddWorkspacePage.tsx` — agent-
  type choice for the first agent (replace harness picker).
- `sculptor/sculptor/constants.py` / settings — `ENABLE_MULTI_HARNESS`
  interplay for gating the pi menu entry (registrations live in their own
  `~/.sculptor/terminal_agents/` directory, not `UserConfig` — §8).

**Delete**
- `_agent_config_for_workspace` (`web/app.py`) and the `Workspace.harness` /
  `CreateWorkspaceRequestV2.harness` shims marked DELIBERATE-TEMPORARY.

---

## Alternatives Considered

- **Reuse `run_agent_task_v1` for terminal agents** (route them through the
  chat loop with an inert `Agent`). Rejected: the loop blocks on an initial
  chat message before starting the agent and carries request/AUQ/artifact
  machinery that is dead weight and a correctness hazard for terminal agents.
  A dedicated handler is simpler and safer.
- **`TerminalAgent` implementing the `Agent` ABC, built via
  `create_agent_for_run`** (registry symmetry). Rejected: it yields no loop
  reuse (the dedicated handler is needed regardless), so `pop_messages`/
  `push_message`/`wait` become dead, misleading surface on a PTY that has no
  message stream.
- **A parallel `create_terminal_session_for_run` registry seam** (honest
  `TerminalSession`, preserves "registry owns construction"). Reasonable, but
  rejected for v1 on YAGNI: there is exactly one terminal-session backend, so
  a single-case dispatch is ceremony; `get_harness_for_config` already keeps
  the harness registered in one place. Revisit if a second terminal backend
  (remote/devcontainer) appears.
- **Status field on the task** (read directly by the view, instead of
  synthetic messages — §5). Rejected: it adds a second status channel
  parallel to the message stream, needs its own restart reconciliation, and
  doesn't get unread/`updated_at` behavior for free the way a content
  message does.
- **Output-stream heuristics for status** (infer busy from terminal
  activity). Rejected per spec Non-Goals — no signals means neutral status.
- **A filesystem watcher for diff freshness** in v1. Rejected per spec
  Non-Goals — periodic refresh, encapsulated for a later swap.
- **Reuse the workspace+index terminal route** for the agent's PTY. Rejected:
  it shares an index space with the workspace terminal panel and isn't
  addressable as "this agent's terminal"; an agent-scoped route is cleaner.
- **Parse terminal agent output into a chat UI.** Rejected per spec — terminal
  agents explicitly have no rich chat UI.
- **Repo-scope registrations / settings UI.** Rejected per spec — v1 is
  user-scope declarative config only.
- **Automated prompts via the frontend's open terminal WebSocket** (write the
  prompt from the button into the mounted xterm/WS). Rejected in favor of the
  server-side `…/terminal/input` endpoint (§9): the latter works regardless of
  whether the terminal panel is mounted/focused and keeps the PTY server-owned
  and auth-checked, matching the signal API.
- **Running Commit/PR as a deterministic git operation** for terminal agents
  (bypass the agent, run git directly). Rejected: it changes the semantics
  (no AI-authored commit message / PR body) and can't run while the program
  holds the shell foreground; the automated-prompt path preserves the
  agent-driven behavior.

---

## Risks and Mitigations

- **Hidden coupling to the chat loop.** Many subsystems assume an agent is a
  chat task (status derivation, diagnostics menu, workspace peek, unread
  tracking). *Mitigation:* terminal agents remain normal `Task`s with a
  `CodingAgentTaskView`; only `status` and the main-panel presentation
  branch on the terminal harness, everything else degrades to neutral/empty.
  Audit each `CodingAgentTaskView` computed field for terminal-harness
  behavior during the plan.
- **PTY launch race for registered programs.** Writing the launch command
  into the shell before it is ready could drop characters. *Mitigation:*
  spawn the login shell, then write the command on shell-ready, matching how
  the existing PTY handles input; the program runs as a job so a slightly
  late write still works.
- **Signal API auth / token exposure.** Auth reuses the global session token
  (§4), which is injected into the terminal-agent PTY env — so any program in
  that terminal can reach the full local `/api/`, a broader surface than the
  signal endpoints. *Mitigation:* the backend binds loopback-only and the
  token already gates all `/api/` today; the signal endpoints additionally
  scope each call to its agent id (`/api/v1/agents/{agent_id}/…`). If tighter
  least-privilege is wanted later, swap to a per-agent minted token without
  changing the event contract.
- **Restart resume correctness.** Relaunching with a stale/absent session id
  could start the wrong conversation or none. *Mitigation:* persist the
  reported session id; fall back to the plain launch command when absent;
  `--continue`-style resume is explicitly insufficient (multiple sessions).
- **Stale status across restart.** A `waiting-on-input` reported before a
  backend crash may not be true after the program is relaunched/resumed, so a
  persisted status would mislead. *Mitigation:* status is **run-scoped** (§5)
  — the derivation only honors signals since the most recent run-start marker,
  so a restart resets to neutral and the relaunched program re-drives it.
- **Prompt-based features pointed at a terminal agent.** Commit / Create PR /
  custom actions send a chat message; a terminal agent can't receive one,
  and the CI babysitter reads the soon-deleted `workspace.harness`.
  *Mitigation:* gate the affordances by `supports_chat_interface` as the
  fallback (§9); update the CI babysitter to create a native chat agent
  directly. Audit every `chatActions.sendMessage` call site during the plan.
- **Automated prompt sent into the wrong program state (§9).** Writing a
  prompt into a bare shell (program self-exited) or a busy program would run
  garbage or be mangled. *Mitigation:* opt-in per registration
  (`accepts_automated_prompts`), send only when the last signal shows the
  agent at its prompt, and wrap multi-line text in bracketed paste so the TUI
  controls submission. The text is escaped/validated server-side.
- **Registration re-read churn / malformed configs.** Re-reading on menu open
  could surface a broken file. *Mitigation:* validate declaratively, skip +
  log invalid entries, keep the menu functional.
- **Capability matrix drift.** `HarnessCapabilities` has no defaults — adding
  the terminal harness forces every constructor site to be updated. *That is
  the intended grep-completeness guard*, not a risk, but the plan must touch
  all sites.

---

## Testing Strategy

- **Backend unit:** the agent-type→config factory; `run_task` dispatch to the
  terminal handler; `TerminalHarness.capabilities()` (all-false); the
  status-driver mapping (each signal → expected `TaskStatus`, no-signal →
  neutral, **and status reset across a simulated restart** — a pre-restart
  `waiting` must not survive); the registration loader
  (valid/invalid/enable-bundled); the CI babysitter creating a native chat
  agent without `workspace.harness`.
- **Prompt-based feature targeting:** Commit / Create PR / custom-action
  affordances are disabled for a terminal agent that can't accept an automated
  prompt, present for chat agents in the same workspace, and (§9) route to the
  terminal-input endpoint for an automated-prompt-capable terminal agent at a
  prompt; the send is blocked when the agent is neutral/exited; multi-line
  prompts paste atomically (bracketed paste) without premature submission.
- **Signal API:** event acceptance + auth (token required, agent-scoped),
  unknown-event ignore, files-changed → diff refresh, session-id persistence;
  `sculpt signal …` subcommands hit the API with injected env.
- **Lifecycle:** PTY spawn for plain vs registered; program-exit drops to
  shell (REQ-LIFE-5); restart re-creates fresh shell (LIFE-4) and resumes via
  session id (LIFE-3); teardown on archive/delete stops the PTY (LIFE-2);
  PTY survives WS disconnect (LIFE-1).
- **Frontend / integration:** split button one-click + chevron menu
  (incl. pi gating), terminal panel replaces chat for terminal agents,
  capability-gated chat affordances hidden, status dots driven by signals,
  neutral status with no signals. Reuse the existing terminal/FakeClaude
  integration-test harnesses where possible.
- **End-to-end (bundled Claude Code):** enable the example, create the agent,
  verify busy/waiting/idle dots and diff refresh while interacting only via
  the terminal.

---

## Open Questions

These are carried into Q&A and the plan; spec Open Questions are tagged.

1. **Status driver (spec):** RESOLVED — synthetic runner messages, **run-scoped**
   (latest signal since the last run-start marker; resets on backend restart so
   a stale `waiting` is never resurrected) (§5). Exact message types /
   persistence mechanism are plan-level under that invariant.
2. **Registration file format (spec):** RESOLVED — a directory of
   per-registration TOML files at `~/.sculptor/terminal_agents/`, re-read on
   menu open; bundled Claude example shipped as a copyable sample (§8).
3. **Signal API token (spec):** RESOLVED — reuse the session-token mechanism
   (injected via terminal-agent PTY `extra_env`); agent identity via the task
   id, calls scoped by agent id in the path (§4). Exact env var names are
   plan-level.
4. **`Workspace.harness` migration (spec):** RESOLVED — drop the column now via
   schema migration; no per-task migration needed.
5. **Presentation switch:** RESOLVED — a dedicated `supports_chat_interface`
   bool on `HarnessCapabilities` drives the chat→terminal panel switch (§2).
6. **Construction seam:** RESOLVED — the handler owns the PTY directly; only
   `get_harness_for_config` is extended, no `TerminalAgent`/`Agent` impl (§3).
7. **Default tab naming (spec):** RESOLVED — registration display name for
   registered agents; "Terminal N" for plain terminals (§6).
8. **Prompt-based features (review):** RESOLVED — Commit / Create PR / custom
   actions gate off via `supports_chat_interface` as a fallback and route to
   the automated-prompt path for capable terminal agents (§9, item 10); the CI
   babysitter creates its own native chat agent and stops reading the deleted
   `workspace.harness`.
9. **Status-after-restart correctness (review):** RESOLVED — terminal status is
   run-scoped and never persisted across a restart, so a resumed program that
   is no longer waiting is not shown as waiting (§5).
10. **Automated-prompt path — v1 scope (review):** RESOLVED — in scope for v1.
    Commit / Create PR / custom actions work for `accepts_automated_prompts`
    registered agents via the server-side `…/terminal/input` reverse channel,
    state-gated and bracketed-paste-wrapped (§9). (Flag named
    `accepts_automated_prompts`, not "prompt injection," to avoid colliding
    with the security term.)
