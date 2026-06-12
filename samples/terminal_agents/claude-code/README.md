# Claude Code as a Sculptor terminal agent

This sample registers the [Claude Code](https://claude.com/claude-code) TUI
as a Sculptor *terminal agent*: it runs in a real terminal inside a Sculptor
workspace tab — so you can use your Claude subscription's TUI directly —
while still getting Sculptor's diff panel, status dots, and restart resume.

## Install

Copy both files into `~/.sculptor/terminal_agents/` (create the directory if
it doesn't exist):

```bash
mkdir -p ~/.sculptor/terminal_agents
cp claude-code.toml claude-code-hooks.json ~/.sculptor/terminal_agents/
```

No restart needed — the agent-type menus re-read the directory every time
they open. "Claude Code" appears in the `+` menu's type list and in the
new-workspace agent picker.

## How it works

- `claude-code.toml` is the registration. Its **filename stem is the
  registration id** (`claude-code`); renaming the file changes the id (agents
  you already created keep working — their launch settings were stamped at
  creation).
- The launch command starts `claude` with `--settings` pointing at
  `claude-code-hooks.json`, whose hooks report state to Sculptor through the
  `sculpt signal` CLI (on PATH inside every agent terminal):
  - `SessionStart` reports the session id (for resume) and `idle`;
  - `UserPromptSubmit` → `busy` (spinner on the tab);
  - `Stop` → `idle`;
  - `Notification` → `waiting` (attention dot when Claude needs input);
  - `PostToolUse` on file-editing tools → `files-changed` (refreshes the
    diff panel promptly).
  Every hook is fail-open (`|| true`) — a broken integration degrades to a
  plain terminal, it never breaks the TUI.
- After a Sculptor restart, the agent relaunches with
  `claude --resume <session id>` so the conversation continues.

## Version note

Verified against Claude Code 2.x (hook events `SessionStart`,
`UserPromptSubmit`, `Stop`, `Notification`, `PostToolUse`; flags
`--settings`, `--resume`). Hook names occasionally evolve between CLI
releases — if a hook stops firing, check `claude --help` and the Claude Code
hooks documentation.
