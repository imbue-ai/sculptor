# Claude Code as a Sculptor terminal agent

This registration runs the [Claude Code](https://claude.com/claude-code) TUI
as a Sculptor *terminal agent*: it runs in a real terminal inside a Sculptor
workspace tab — so you can use your Claude subscription's TUI directly —
while still getting Sculptor's diff panel, status dots, and restart resume.

It is also the reference example for writing your own terminal-agent
registrations.

## Installed by default

Sculptor installs these two files into `<sculptor folder>/terminal_agents/`
(`~/.sculptor/` for the app, `<repo>/.dev_sculptor/` when running from
source) the first time the backend starts, so "Claude Code" appears in the
`+` menu's type list and in the new-workspace agent picker out of the box.

The installed copy is **yours**:

- **Edit it** — Sculptor never overwrites an existing file.
- **Delete it** — deletion sticks; the files are not re-installed on the
  next start.
- Menus re-read the directory every time they open, so changes apply
  without a restart.

(Manual install, e.g. after deleting it: copy both files into
`<sculptor folder>/terminal_agents/` and point the two `--settings` paths in
the TOML at the copied hooks file.)

## How it works

- `claude-code.toml` is the registration. Its **filename stem is the
  registration id** (`claude-code`); renaming the file changes the id (agents
  you already created keep working — their launch settings were stamped at
  creation).
- The launch command runs in the agent's login shell and uses env vars
  Sculptor injects into every terminal-agent shell, so no machine-specific
  paths are baked into the file:
  - `$SCULPT_CLAUDE_BIN` — Sculptor's managed Claude binary (falls back to
    `claude` from PATH);
  - `$SCULPT_PLUGINS_DIR` — the bundled Sculptor plugin directories, loaded
    via `--plugin-dir` (same plugins chat agents get: `sculptor-plugin`,
    `sculptor-workflow`, `sculptor-experimental`).
- It launches with `--dangerously-skip-permissions` (matching how Sculptor
  runs Claude for chat agents); the settings file skips the one-time
  bypass-permissions disclaimer so the TUI lands directly at its prompt.
- `--settings` points at `claude-code-hooks.json`, whose hooks report state
  to Sculptor through the `sculpt signal` CLI (on PATH inside every agent
  terminal):
  - `SessionStart` reports the session id (for resume) and `idle`;
  - `UserPromptSubmit` → `busy` (spinner on the tab);
  - `Stop` → `idle`;
  - `Notification` → `waiting` (attention dot when Claude needs input);
  - `PostToolUse` on file-editing tools → `files-changed` (refreshes the
    diff panel promptly).
  Every hook is fail-open (`|| true`) — a broken integration degrades to a
  plain terminal, it never breaks the TUI.
- After a Sculptor restart, the agent relaunches via
  `resume_command_template` (`--resume <session id>`) so the conversation
  continues.

## Version note

Verified against Claude Code 2.x (hook events `SessionStart`,
`UserPromptSubmit`, `Stop`, `Notification`, `PostToolUse`; flags
`--settings`, `--resume`, `--dangerously-skip-permissions`, `--plugin-dir`;
settings key `skipDangerousModePermissionPrompt`). Hook names occasionally
evolve between CLI releases — if a hook stops firing, check `claude --help`
and the Claude Code hooks documentation.
