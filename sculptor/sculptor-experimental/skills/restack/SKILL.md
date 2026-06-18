---
name: restack
description: |
  Propagate a branch's changes down its stacked children by merging the updated
  parent into each stacked branch, in order from base to tip.
when_to_use: |
  Invoke when you've changed an earlier branch in a stack (created via
  /sculptor-experimental:stack) and want those commits to flow into the branches
  stacked on top of it — e.g. "update the stack", "restack", "propagate my
  changes up the stack", or after committing a fix on a base branch that the
  later branches build on. It merges each parent's new commits into its children
  so every branch in the stack ends up with the proper state.
user_invocable: true
---

# Restack

ARGUMENTS: $ARGUMENTS

Propagate the current branch's changes into the branches stacked on top of it.
Each stacked branch was created off — and targets — its parent (that's what
`/sculptor-experimental:stack` sets up), so "propagating" means **merging** each
parent's updated tip into its child, in order from base to tip.

This is a **merge-based** restack: it brings the parent's new commits into each
child with a merge commit. It does **not** rewrite history, so no force-push is
needed and open MRs/PRs keep their commits and review threads. The merge also
keeps each child's scoped diff correct — after merging parent `P` into child `C`,
the diff of `C` against `P` is exactly `C`'s own changes.

This skill uses the `sculpt` CLI and operates directly on the shared on-disk git
repo. The agent shell already has `SCULPT_WORKSPACE_ID` (current workspace) and
`SCULPT_PROJECT_ID` set.

`$ARGUMENTS` is optional. It may name a different root branch to propagate from;
if empty, propagate from the current branch.

## Step 0 — Refuse if not in a worktree workspace

Restacking only works in **worktree** workspaces. Every branch in the stack lives
in its own `git worktree` sharing one on-disk `.git`, which is what lets this
skill resolve and merge them locally. From a clone or in-place workspace the
stacked branches aren't locally resolvable.

```bash
sculpt workspace show "$SCULPT_WORKSPACE_ID" --json | jq -r .strategy
```

If the result is **not** `WORKTREE`, stop and tell the user (using their strategy
name):

> Restacking isn't supported from a `<strategy>` workspace — the stacked branches
> aren't locally resolvable. Restack from a worktree workspace instead.

Only proceed if the strategy is `WORKTREE`.

## Step 1 — Discover the stack

1. Resolve the **root** branch — the branch whose changes you're propagating
   down. Use `$ARGUMENTS` if it names a branch; otherwise the current branch:

   ```bash
   git rev-parse --abbrev-ref HEAD
   ```

2. List the project's workspaces (stdout is clean JSON; the human-readable
   preamble goes to stderr):

   ```bash
   sculpt workspace list --json
   ```

   Each item has `id`, `strategy`, `source_branch`, `target_branch`,
   `requested_branch_name`, and `is_deleted`.

3. Build the stack graph. A workspace `C` is a **stacked child** of branch `P`
   when **all** of:
   - `C.is_deleted` is false and `C.strategy == "WORKTREE"`,
   - `C.requested_branch_name` is set (this is C's own branch), and
   - `C.target_branch`, **with any leading remote prefix stripped**, equals `P`.

   The target may be stored either bare (`my-branch`) or remote-qualified
   (`origin/my-branch`) — strip a leading `origin/` (or other remote) before
   comparing. Starting from the root branch, collect its children, then their
   children, and so on, recording edges `(parent_branch, child_branch)` in
   **base→tip order** (parents before children). Guard against cycles and against
   a branch listing itself as its own parent.

4. Map each branch in the stack to its on-disk worktree path:

   ```bash
   git worktree list --porcelain
   ```

   Match on branch name (strip the `refs/heads/` prefix). Skip — with a warning —
   any stacked branch that has no live worktree (e.g. its workspace was deleted);
   also skip its descendants, since their parent can't be resolved.

5. If the root has no stacked children, report that nothing is stacked on it and
   stop.

Show the user the discovered stack as a tree (root at the bottom of the stack,
descendants above) before changing anything.

## Step 2 — Pre-flight

**Root branch must be committed.** Only committed work propagates. In the current
worktree:

```bash
git status --porcelain
```

If non-empty, list the affected paths and ask via the AskUserQuestion tool
(`mcp__sculptor__ask_user_question`) whether to commit them first (infer a concise
message and run `git add -A && git commit -m "<msg>"`, surfacing the message), or
proceed propagating only the already-committed work, or abort.

**Dirty stacked branches.** A merge won't run cleanly on a dirty tree. Check each
child's worktree:

```bash
git -C "<child-worktree>" status --porcelain
```

If any stacked branch is dirty, **do not pick a policy yourself** — list the dirty
branches and ask the user how to resolve via the AskUserQuestion tool
(`mcp__sculptor__ask_user_question`), offering at least:
- **Stash & re-apply** — `git -C <wt> stash push -u` before that branch's merge,
  `git -C <wt> stash pop` after (warn that the pop can itself conflict).
- **Skip dirty branches** — leave each dirty branch (and its descendants)
  untouched and report them.
- **Abort** — stop the whole restack so the user can clean up first.

Note any stacked workspace with an actively-running agent: merging under a busy
agent can disrupt its working tree. The dirty check guards uncommitted work, but
flag busy agents so the user can pause them if needed.

## Step 3 — Merge top-down

Process edges in base→tip order, so each parent is finalized before its children.
For each edge `(P, C)` (where `<C-worktree>` is C's worktree path), merge the
parent's current tip into the child:

```bash
git -C "<C-worktree>" merge --no-edit "<P>"
```

Because edges are processed top-down, by the time you merge `P` into `C` the
parent `P` has already received everything below it, so `C` transitively gets the
whole chain's changes. `git merge` brings in only what `C` doesn't already have
(it merges from the current merge-base), so there's no duplication.

- **Already up to date** — git reports "Already up to date."; record C as
  unchanged (nothing new below it).
- **Merged** — record C's new merge-commit SHA.
- **Conflict** — abort and don't leave a half-finished merge:

  ```bash
  git -C "<C-worktree>" merge --abort
  ```

  Mark C as conflicted, **skip all of C's descendants** (their parent didn't
  update), and continue with branches not under C.

If "Stash & re-apply" was chosen for a dirty branch, stash before its merge and
pop after (report if the pop conflicts).

## Step 4 — Report

Summarize the result as a tree, with per-branch status:
- ✅ **merged** — show the new merge-commit short SHA.
- ➖ **up to date** — already contained its parent's changes.
- ⏭️ **skipped** — dirty/declined/no worktree (give the reason).
- ❌ **conflict** — needs a manual merge; suggest the command
  (`git -C <wt> merge <P>`) so the user can resolve it.

Merging does **not** rewrite history, so the updated branches need no force-push —
a normal `git push` from each branch's workspace adds the new merge commit to its
MR/PR when the user is ready. Leave pushing to them.
