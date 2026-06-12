---
name: stack
description: |
  Stack a new workspace on top of the current branch — a handoff into a NEW
  workspace whose new branch is based off, and targets, the current branch.
when_to_use: |
  Invoke when the user wants to branch off the current work into a separate,
  parallel workspace stacked on the current branch — e.g. "stack a new agent on
  this", "spin off a follow-up based on this branch", or to keep the current
  agent focused while a fresh agent tackles a dependent piece of work. The new
  branch is based off the current branch AND targets it, so its diff and any MR
  are scoped to just the changes made on top of the current work.
user_invocable: true
---

# Stack

ARGUMENTS: $ARGUMENTS

## Step 0 — Refuse if not in a worktree workspace

Stacking is only supported in **worktree** workspaces. The stacked workspace is
created via `git worktree add` in the project's on-disk git repo, and only
worktree source workspaces share that git (so the current branch is locally
resolvable). From a clone or in-place workspace, the stacked workspace cannot
find the current branch as a ref — pushing to origin doesn't help because
`git worktree add` doesn't DWIM a bare branch name to `origin/<branch>`.

Check the strategy first:

```bash
sculpt workspace show "$SCULPT_WORKSPACE_ID" --json | jq -r .strategy
```

If the result is **not** `WORKTREE`, stop and tell the user (using their
strategy name):

> Stacking isn't supported from a `<strategy>` workspace — the stacked workspace
> wouldn't be able to base off your current branch. Use
> `/sculptor-experimental:handoff` (new agent in the same workspace) to continue
> this work, or move it into a worktree workspace first.

Only proceed if the strategy is `WORKTREE`.

## Steps 1–4 — Hand off into a new workspace

Stacking is a **handoff into a new workspace**, specialized for building on top
of the current branch. Follow the `/sculptor-experimental:handoff` skill — invoke
it and do what its **"new workspace"** path does (run the pre-flight commit
check, compose a self-contained context-summary prompt, create the workspace +
agent with `sculpt run`, then report the new IDs) — with these differences:

1. **Don't ask which destination.** Stacking always creates a *new workspace*, so
   skip handoff's Step 1 question entirely.
2. **Target the current branch.** Pass `--target-branch <current-branch>` in
   addition to `--branch <current-branch>`. This scopes the new workspace's
   diff/MR to only the changes stacked on top of the current branch, instead of
   the repo's default target (e.g. `main`). This is the defining trait of a
   stack.

So the create command (handoff's Step 4 new-workspace command, with `--target-branch` added) is:

```bash
git rev-parse --abbrev-ref HEAD   # current branch = source AND target

sculpt run \
  --strategy worktree \
  --branch "<current-branch>" \
  --target-branch "<current-branch>" \
  --name "<short task name>" \
  --json \
  "<context-summary prompt>"
```
