# Terminal Agents

## Overview

Sculptor has historically supported only Claude agents, with full message-stream
parsing and a rich chat UI. In-progress work is adding pi as a second natively
supported harness. This feature adds a second, complementary kind of flexibility:
**terminal agents** — agents whose "chat window" is replaced by a terminal, in
which any program (typically an agent TUI) runs.

Three tiers of agent types should be selectable when adding a new agent via the
`+` button in the agent tab bar:

1. **Claude / pi** — existing natively supported harnesses (unchanged).
2. **Terminal** — a bare terminal in place of the agent chat; the user runs
   whatever they want.
3. **Registered terminal agents** — a terminal that launches a predetermined
   program (e.g. Claude Code's own TUI), with a degree of rich integration into
   Sculptor via hooks/wrappers: idle/busy state, waiting-on-question detection,
   file-modification → diff refresh, and other integrations as appropriate.

It is explicitly NOT a goal to parse the message stream of terminal agents —
there is no rich chat UI for them.

Motivation:

- Claude Code is about to disable subscription pricing in SDK mode; running
  Claude Code's own TUI inside Sculptor lets users keep using their
  subscriptions.
- When Claude Code ships features Sculptor can't yet visualize, users can fall
  back to the TUI for full access.
- Users should be able to run any agent (or program) they want — including ones
  Sculptor has never heard of — and even add plugins/extensions that provide the
  richer terminal-agent integration themselves.

## User Scenarios

### Plain terminal in place of chat

User clicks `+` in the agent tab bar and picks **Terminal** (`REQ-TYPE-2`). A
new agent tab opens whose main panel is a terminal running a shell in the
workspace's code directory (`REQ-TERM-1`). They run anything they like — a
REPL, an unsupported agent, `htop`. The tab shows a neutral status (no
busy/waiting dots, `REQ-TERM-2`); the diff view stays reasonably fresh via
periodic refresh (`REQ-TERM-3`). Closing the window doesn't kill the shell
(`REQ-LIFE-1`); after a Sculptor restart the tab comes back with a fresh shell
(`REQ-LIFE-4`).

### Claude Code TUI as a registered terminal agent

The bundled Claude Code registration is installed out of the box
(`REQ-CLAUDE-1`); the user clicks `+` and picks **Claude Code**. A terminal opens with the `claude`
TUI already running in the workspace code directory — billed against their
subscription, with every TUI feature available. Hooks installed by the
registration report signals (`REQ-SIG-3`/`REQ-SIG-4`): while Claude works the
tab shows the busy spinner; when it asks a question the tab shows the
waiting/attention dot (`REQ-SIG-5`); after edits, the diff panel refreshes
(`REQ-SIG-6`). The user answers questions by typing in the terminal — Sculptor
never parses the conversation.

### Resume after Sculptor restart

The Claude Code hook reported its session id earlier (`REQ-SIG-4`), which
Sculptor persisted. The user quits Sculptor mid-session. On relaunch, the
agent's terminal is recreated and the registration's resume template runs
(e.g. `claude --resume <session_id>`), restoring the same conversation
(`REQ-LIFE-3`). Terminal scrollback from before the restart is not preserved.

### Quitting the TUI drops to a shell

The user types `/exit` in the Claude TUI (or the program crashes). Because the
program runs inside a shell session, they land at a normal prompt in the same
terminal (`REQ-LIFE-5`); the tab returns to neutral status. They can rerun the
program by hand, or just use the shell.

### Mixed workspace

A workspace has a native Claude agent, a pi agent, and a Claude Code terminal
agent side by side (`REQ-TYPE-1`). All share the same code directory; diffs,
branch info, and the commit bar behave identically regardless of which agent
made the changes.

### Registered agent without working hooks

A user registers an agent whose integration is missing or broken. Everything
still works as a plain terminal: the program launches, the user interacts in
the terminal, status stays neutral, diffs refresh periodically
(`REQ-TERM-2`/`REQ-TERM-3`). Integration is purely additive.

## Requirements

### Agent type selection (TYPE)

- `REQ-TYPE-1`: Agent type MUST be a **per-agent** property chosen at agent
  creation time. A single workspace MAY contain a mix of Claude, pi, terminal,
  and registered terminal agents.
- `REQ-TYPE-2`: The `+` button in the agent tab bar MUST let the user choose
  among: Claude, pi, Terminal, and every registered terminal agent.
- `REQ-TYPE-3`: The existing workspace-bound harness selection
  (`Workspace.harness`, marked DELIBERATE-TEMPORARY) MUST be replaced by the
  per-agent selection, including for pi.
- `REQ-TYPE-4`: Pi MUST appear in the type picker only when the existing
  multi-harness setting (`ENABLE_MULTI_HARNESS`) is on; Claude, Terminal, and
  registered terminal agents are available to everyone.
- `REQ-TYPE-5`: The new-workspace flow MUST offer the same full agent-type
  choice for the workspace's first agent, replacing its current flag-gated
  workspace-harness picker. (The flow creates the first agent with no initial
  prompt today; that stays unchanged.)
- `REQ-TYPE-6`: The `+` button MUST be a **split button**: a plain click
  instantly creates an agent of the last-used type (initially Claude),
  preserving today's one-click flow; an attached chevron opens the type menu
  listing Claude, pi (when enabled), Terminal, and registered terminal
  agents.

### Registration (REG)

- `REQ-REG-1`: Terminal agents MUST be registerable via **user-scope
  declarative config** (under `~/.sculptor/`). No repo-scope registration and
  no settings UI in v1.
- `REQ-REG-2`: A registration MUST carry at minimum: a display name and the
  command to launch. It MAY carry integration config, including a
  **resume command template** that references a persisted session id (e.g.
  `claude --resume {session_id}`).
- `REQ-REG-3`: The `+` menu MUST reflect the current set of registrations
  without requiring a Sculptor restart (SHOULD: re-read on menu open).

### Integration signal contract (SIG)

- `REQ-SIG-1`: The integration contract MUST be a **local HTTP event API** on
  the Sculptor server. Hooks/wrappers/extensions post small JSON events on
  behalf of a specific terminal agent.
- `REQ-SIG-2`: Sculptor MUST inject env vars into the terminal session that
  hooks need to call the API: endpoint URL, the agent/task identity, and an
  auth token.
- `REQ-SIG-3`: Sculptor MUST ship thin `sculpt` CLI subcommands wrapping the
  HTTP API (e.g. `sculpt signal busy|idle|waiting`, `sculpt signal
  files-changed`, `sculpt signal session-id <id>`), so shell-based hooks (like
  Claude Code hooks) don't need to hand-roll HTTP calls.
- `REQ-SIG-4`: The v1 event vocabulary is exactly: **busy**, **idle**,
  **waiting-on-input** (agent asked a question), **files-changed**, and
  **session-id** (report the harness-native session identifier for resume).
  The API MUST be designed so new event types can be added later without
  breaking existing integrations (unknown events are logged and ignored).
- `REQ-SIG-5`: Status events MUST drive the same tab indicators native agents
  use (busy spinner, waiting/attention dot). The unread dot is deliberately
  NOT driven by terminal signals in v1 — signals are run-scoped status, not
  content (see architecture §5).
- `REQ-SIG-6`: A files-changed event MUST trigger a workspace diff refresh
  (the existing `maybe_refresh_workspace_diff` path).

### Terminal behavior & no-signal mode (TERM)

- `REQ-TERM-1`: A plain "Terminal" agent's main panel MUST be a terminal
  running a shell in the workspace's code directory — no chat UI, no message
  parsing.
- `REQ-TERM-2`: Terminal agents that have emitted no signals (plain terminals,
  or registered agents whose integration is absent/broken) MUST show a calm
  **neutral status** — no busy/waiting indicators. Integration is purely
  additive; a broken integration degrades to plain-terminal behavior.
- `REQ-TERM-3`: For terminal agents, the workspace diff MUST stay reasonably
  fresh via a cheap **periodic refresh** (akin to the existing 3s branch
  polling). This MAY later be replaced by a file watcher; the periodic
  mechanism should be encapsulated so that swap is easy.

### Lifecycle (LIFE)

- `REQ-LIFE-1`: A terminal agent's process MUST keep running when its tab is
  hidden or the window closes (same persistence as today's terminal-panel
  PTYs).
- `REQ-LIFE-2`: The process MUST be terminated when the agent is
  archived/deleted or its workspace is torn down.
- `REQ-LIFE-3`: After a Sculptor/backend restart, registered terminal agents
  MUST be auto-relaunched. If a session id was reported (`REQ-SIG-4`) and the
  registration has a resume template (`REQ-REG-2`), relaunch MUST use it so
  the agent resumes its session; otherwise relaunch runs the plain launch
  command. (`claude --continue` is not sufficient — multiple sessions can
  exist, so the preserved session id is required.)
- `REQ-LIFE-4`: Plain "Terminal" agents have nothing to resume — after a
  restart they MUST be recreated as a fresh shell.
- `REQ-LIFE-5`: A registered terminal agent's program MUST run **inside a
  shell session**, so that when the program exits (user quits the TUI, or it
  crashes) the user lands at a normal shell prompt in the same terminal.
  Status returns to neutral; the user can rerun the program by hand. No
  auto-relaunch on self-exit.

### UI (UI)

- `REQ-UI-1`: For terminal agents, the terminal MUST occupy the space the chat
  panel occupies for native agents. There is no chat input, message list,
  model picker, or other chat-specific affordance for terminal agents.
- `REQ-UI-2`: Chat-oriented surfaces MUST be hidden or disabled via the
  existing capability-gate system (`HarnessCapabilities` /
  `useCapabilityGate`) rather than ad-hoc conditionals, extending the pattern
  established by the pi work.
- `REQ-UI-3`: A terminal agent's tab MUST behave like any other agent tab:
  it can be renamed, archived/deleted, and shows status dots (driven by
  signals per `REQ-SIG-5`, or neutral per `REQ-TERM-2`).

### Bundled Claude Code example (CLAUDE)

- `REQ-CLAUDE-1`: Sculptor MUST ship a registration for the Claude Code TUI
  that is **installed out of the box** (auto-installed once into the
  user-scope registrations directory, for both the packaged app and dev
  instances) as an ordinary **user-owned** registration: the user can edit
  or delete it, edits are never overwritten, and deletion sticks across
  restarts. It doubles as the reference example for third-party
  registrations and demonstrates the full integration: hook config reporting
  busy/idle/waiting/files-changed and session-id for resume, launched with
  the same plugins and permission mode as Sculptor's native Claude agents.
  *(Amended: v1 originally shipped this as a copy-to-enable sample that was
  absent from the menu by default.)*

## Non-Goals

- Parsing the message stream of terminal agents or rendering a rich chat UI for
  them.
- Repo-scope (`.sculptor/`) registrations or a settings UI for managing
  registrations — v1 is user-scope config files only.
- Output-stream heuristics for status (e.g. inferring busy from terminal
  activity) — no signals means neutral status.
- A filesystem watcher for diff freshness — v1 uses periodic refresh, designed
  to be swappable later.
- Signal vocabulary beyond busy/idle/waiting-on-input/files-changed/session-id
  (the API is extensible, but no further events ship in v1).
- A non-removable built-in Claude Code menu entry — the bundled registration
  is installed as user-owned files the user can edit or delete. *(Amended:
  originally this non-goal also excluded installing it by default at all;
  REQ-CLAUDE-1 now requires out-of-the-box installation.)*

## Open Questions

For the architect / plan phases:

- **Status driver**: `TaskStatus` today is derived by parsing the agent
  message stream (`derived.py`). Terminal agents need a different driver —
  e.g. signal events become synthetic runner/agent messages, or a separate
  status field on the task. Pick whichever integrates most cleanly with the
  existing tab-indicator and stream plumbing.
- **Registration file format**: exact schema and layout under `~/.sculptor/`
  (single file vs. one file per registration; TOML/JSON; how "enabling" the
  bundled Claude example works mechanically).
- **Env var names and token scoping** for the signal API (`REQ-SIG-2`):
  per-task token vs. reuse of the existing session-token mechanism; exact
  variable names.
- **Workspace.harness migration**: how existing pi workspaces map onto
  per-agent configs when the DELIBERATE-TEMPORARY workspace-bound selection is
  removed (`REQ-TYPE-3`).
- **Default tab naming** for terminal agents (e.g. registration display name,
  "Terminal n" for plain terminals) — native agents auto-name from the
  conversation, which terminal agents can't do.
