# Slash Commands

Type `/` in the Sculptor input box to open the command and skill picker. The picker shows session commands handled by Sculptor itself, skills that run through Claude Code, and a set of `sculptor:*` skills bundled with the app.

---

## Session commands

These run locally and affect the current agent session.

### `/clear`

Clears the conversation history for the current agent, freeing its context. Use this when you're starting a new task and don't need the previous conversation carried forward.

### `/compact`

Summarizes the conversation so far into a short context-summary block, freeing context without losing the thread. Useful in long sessions where you're approaching the context limit.

### `/copy`

Copies the last assistant response's text to your clipboard.

---

## Skills

These are forwarded to Claude Code, which runs them as full agents with their own tools. Unlike session commands, skills can spawn parallel subagents, read files, and adapt to your codebase.

### `/batch <instruction>`

Run a prompt or command across multiple files. The agent decomposes the work into independent units and executes them in parallel.

Example: `/batch migrate src/ from Solid to React`

### `/context`

Visualize the current context usage. Opens a breakdown of what's taking up tokens in the current conversation so you can decide whether to `/compact` or `/clear`.

### `/loop [interval] <prompt>`

Run a prompt or slash command on a recurring interval. Useful for polling a deployment, watching a PR, or periodically re-running another skill. Omit the interval to let the model self-pace.

Example: `/loop 5m check if the deploy finished`

### `/simplify [focus]`

Review changed code for reuse, quality, and efficiency issues, then fix them. Pass text to focus on a specific concern.

Example: `/simplify focus on memory efficiency`

---

## Bundled `sculptor:*` skills

These ship with Sculptor and are available in every workspace.

### `/sculptor:fix-bug`

Fix a bug using test-driven development. Input: a description of the bug to fix, or a bug ticket ID.

### `/sculptor:help`

Answer questions about Sculptor by fetching the live docs. Use this when you want a quick answer without leaving the chat.

### `/sculptor:sculpt-cli`

Interact with Sculptor programmatically using the `sculpt` CLI — create tasks, list tasks, or manage projects.

### `/sculptor:setup-repo`

Create or update the repo's Sculptor configs (`.sculptor/code.md` and `.sculptor/testing.md`). These files teach Sculptor how to build, run, and test changes in the current codebase.

---

## Your own skills and commands

Sculptor also surfaces any skills or commands you've installed under `~/.claude/skills/` or `~/.claude/commands/`, as well as any under the current repo's `.claude/` directory. These appear in the picker alongside the built-ins, sorted alphabetically.

For everything else, see the [Claude Code commands reference](https://code.claude.com/docs/en/commands).
