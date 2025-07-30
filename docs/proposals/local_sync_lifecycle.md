---
gitlab_mrs:
linear_issues: https://linear.app/imbue/issue/PROD-1377/spec-out-local-sync-lifecycle-robustness-state-graph
last_updated: 2025-07-29
---

# Local Sync Lifecycle Management

## Problem
> When user does incompatible git stuff we want to stop syncing, but can't because the stash handling is coupled.

`// TODO better lower-collision term than worktree`<br/>
The `local_sync_service` handles git and worktree synchronization between the user and the agent task container.
Local sync has two states at the moment: `OFF` and `ACTIVELY_SYNCING(task)`.
Because the sync uses stateful, user-facing, and relatively-uncontrolled 3rd party code to manage the local sync job, many currently-unaccounted-for states can arise.

**Consequences** of weird states:
1. `mutagen` will continue to sync between a possibly-active agent's worktree, potentially causing confusion/unexpected edits on both sides.
2. git sync will stop working if user and agent branches diverge even a little, and that fact is not well-surfaced.
3. If the user gets into a transient or dirty git state (IE rebasing/merging/cherry-picking), we can't exit sync cleanly, or even really at all without either mangling their current state or losing track of the local sync stash (a git stash + untracked files backup managed by sculptor).
4. If the user shuts down sculptor in a dirty git state, their stash will likely go unrecovered.
5. If the user manually pops the stash, kill mutagen, or otherwise tampers with the underlying states we rely on, they will likely lose stashed untracked files and have other state inconsistencies in their db.

These conflicts all compound one another: `mutagen` dirties the tree, the dirty tree prevents sync exit, preventing sync exit makes it hard for a user to stop mutagen.

### WIPs / Stop-gaps

The following tickets will lay groundwork for lifecycle awareness & our ability to control the transitions as needed:

* [PROD-807]+[PROD-1372] will make state transitions hinge on `is_local_sync_transition_safe`
* [PROD-807] (`no-watch` mode) will enable us to manually control `mutagen sync flush` timing and add checks to avoid the hypothetical dirty-state death spiral.

## Lifecycle Design
> Decouple stash handling, add a pause state.

We can do better than the above by unbundling some of the currently-coupled local sync systems:
1. [PROD-1364] will decouple the local sync stash/untracked file backup from the overall lifecycle, allowing it to be left for manual handling in complicated cases.
2. [PROD-848] will introduce a "paused" state to the local sync job, which we only use when sync is on another branch or in an error state.
3. [PROD-1402] will expose the causes for the pause to the user for resolution.

Putting everything together, we get the following state diagram:
![lifecycle excalidraw](../diagrams/git_sync_state_diagram.svg)
> <small>Generated from `sculptor/docs/proposals/diagrams/git_sync_state_diagram.excalidraw`,
> which can be opened with IDE extensions or http://excalidraw.com/</small>

The most important decisions above are:
1. Pausing is not manually toggle-able. User should just stop sync instead.
2. The only time an existing stash prevents an action is when attempting to start a new sync from a dirt tree.
   Otherwise we can just leave it lying around.

This means the user can always choose to discard the paused local sync and leave the stash behind without worrying about it if they've already moved on to other work.

#### Probable future work

There will probably also be lots of thorny edge-case handling like [PROD-1403] (crash recovery cleanup).
In particular, it is possible for a user to pop the git stash manually, leaving behind an untracked file backup.

* [PROD-807]: https://linear.app/imbue/issue/PROD-807/no-watch-mode-adjust-mutagen-handling-to-sync-on-user-worktree-changes
* [PROD-846]: https://linear.app/imbue/issue/PROD-846/prevent-startingstopping-local-sync-in-mergerebase-states
* [PROD-1372]: https://linear.app/imbue/issue/PROD-1372/error-handling-stopgap-only-unsync-on-error-if-is-local-sync
* [PROD-1364]: https://linear.app/imbue/issue/PROD-1364/decouple-local-sync-stash-track-the-sculptor-stashbackup
* [PROD-848]: https://linear.app/imbue/issue/PROD-848/pause-or-bail-out-of-local-sync-on-incompatible-git-state-changes
* [PROD-1402]: https://linear.app/imbue/issue/PROD-1402/local-sync-pause-state-surface-causes-to-user
* [PROD-1403]: https://linear.app/imbue/issue/PROD-1403/local-sync-cleanup-and-stash-recovery-after-crash
