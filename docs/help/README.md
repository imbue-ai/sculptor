# Sculptor Help

Sculptor is a desktop app for running coding agents in parallel. Each task gets
an isolated working copy of your repo — a **workspace** — so agents can work side
by side without merge chaos. You review their changes and open a pull request
when you're ready.

This is the user guide. For contributor and developer documentation, see
[`docs/development/`](../development/).

## Core concepts

- **Workspaces** — isolated working copies of your repo, git worktrees by
  default. Your current branch and uncommitted work are never touched.
- **Agents** — AI coding assistants that run inside a workspace. Several can run
  in parallel, and multiple agents can share a single workspace.
- **Changes** — review an agent's edits, commit them, and open a pull request.

## Documentation

### Using Sculptor

- [Getting Started](getting_started.md) — first-run setup and your first task.
- [Workspaces](workspaces.md) — worktrees, branches, modes, and per-repo setup.
- [Chat](chat.md) — the chat input: model picker, context usage, plan/fast/effort,
  mentions, and slash commands.
- [Terminal](terminal.md) — the built-in terminal, scoped to the workspace.
- [Agents](agents.md) — running multiple agents in parallel within one workspace.
- [Changes](changes.md) — reviewing the agent's diff, committing, and discarding.
- [Pull Requests](pull_requests.md) — opening a GitHub PR and tracking its status.
- [Skills](skills.md) — the bundled `sculptor-workflow` and `sculptor-experimental`
  skills you can run from `/`.
- [Command Palette](command_palette.md) — `Cmd+K` to search and jump around the app.
- [Settings](settings.md) — a tour of the settings sections.

### Experimental

- [Container Backend](experimental/container_backend.md) — run the backend in
  Docker or on a remote machine via a custom backend command.

You can also ask questions interactively with the `/sculptor:help` slash command
inside the app.
