---
name: handoff
description: |
  Hand off the current work to a fresh agent — either a new agent in the SAME
  workspace, or a new workspace — seeded with a summary of the current context.
when_to_use: |
  Invoke when the user wants to continue the current work with a fresh agent —
  e.g. "hand this off", "start fresh but keep the context", or when the current
  context window is large and a clean restart would help. Works in two modes: a
  new agent in the same workspace (shares the branch and files), or a brand-new
  workspace on its own branch off the current one.
user_invocable: true
---

# Handoff

ARGUMENTS: $ARGUMENTS

Hand off the current work to a fresh agent, seeded with a summary of the current
context. `$ARGUMENTS` (if provided) describes what the new agent should focus on
next; if empty, infer it from the recent conversation.

This skill uses the `sculpt` CLI. The agent shell already has
`SCULPT_WORKSPACE_ID` (current workspace) and `SCULPT_PROJECT_ID` set.

## Step 1 — Choose the destination

The handoff can land in one of two places:

- **New agent, same workspace** — shares this workspace's filesystem and branch,
  so it picks up exactly where this one left off (including uncommitted changes).
- **New workspace** — a fresh, isolated workspace on its own auto-named branch
  cut from the current branch, for continuing the work in a clean checkout.

If `$ARGUMENTS` already makes the choice clear (e.g. it mentions "new agent",
"same workspace", or "new workspace"), use that. **Otherwise, ask the user which
one with your question tool** — `mcp__sculptor__ask_user_question` if it's available, otherwise the built-in `AskUserQuestion` — and
wait for the answer before creating anything. (The tool call raises the
"waiting for input" status that alerts the user; don't ask in plain text.)

## Step 2 — Pre-flight: commit uncommitted work (new-workspace mode only)

**Skip this step if the user chose "new agent, same workspace"** — the same
workspace shares this working tree, so uncommitted work is visible to the new
agent as-is.

For **new workspace** mode, the new workspace is cut from a commit on the
current branch in the project's on-disk git repo. Anything not committed won't
be visible to the new agent. Walk the user through it so they're never
surprised.

Run from the repo root:

```bash
git status --porcelain
```

If the output is non-empty, list the affected paths (just the paths, not the
diffs) and ask with your question tool:

> You have N uncommitted change(s). Commit them before handing off?
> - **Yes, commit them** — write a concise commit message inferred from the
>   conversation and run `git add -A && git commit -m "<msg>"`. Surface the
>   message you used in your next text reply so the user can amend if they want.
> - **No, leave them** — the new agent won't see those changes.

Do **not** prompt for a push. The new workspace shares the user repo's `.git`,
so committed work is visible to it locally — pushing to origin is a separate
concern (CI, MR linkage, code-review visibility) the user can do when they're
ready, and Sculptor's in-workspace diff display doesn't require origin
connectivity either (`origin/*` refs are seeded locally at workspace creation).

## Step 3 — Compose the handoff prompt

Write a self-contained prompt so the new agent can continue without access to
this conversation:

- A summary of the task and the current state of the work.
- Key context: relevant files, decisions made, what is done, what remains, and
  anything already tried that didn't work.
- The next concrete step(s) to take (from `$ARGUMENTS` or the inference above).

Summarize; don't dump the whole transcript.

## Step 4 — Create the handoff

**New agent, same workspace** — the new agent shares this workspace's branch and
files, so reference them by path; it can see them (and uncommitted changes)
directly:

```bash
sculpt agent create \
  -w "$SCULPT_WORKSPACE_ID" \
  --name "<short task name>" \
  --json \
  --prompt "<the prompt from step 3>"
```

**New workspace** — first get the current branch, then create a workspace + agent
based off it:

```bash
git rev-parse --abbrev-ref HEAD   # the source branch

sculpt run \
  --strategy worktree \
  --branch "<current-branch>" \
  --name "<short task name>" \
  --json \
  "<the prompt from step 3>"
```

`--strategy worktree --branch <current>` creates the new workspace on a fresh,
auto-named branch cut from the current branch — the same mechanism the UI uses —
so the committed work carries over.

> **Use `sculpt run`, not `sculpt workspace create`.** `sculpt run` creates the
> workspace, its agent, *and* the git worktree in one step. `sculpt workspace
> create` only registers a workspace record — no agent, no checkout — so it
> renders as a blank screen in the UI. To add an agent to an already-empty
> workspace, run `sculpt agent create -w <ws_id> -p "..."`.

Add `-m sonnet` (or another model) to override the default model.

## Step 5 — Report back

Parse the JSON output and tell the user the new agent ID (and the new workspace
ID, when a new workspace was created) so they can switch to it.
