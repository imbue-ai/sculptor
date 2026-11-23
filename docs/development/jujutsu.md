# Design: Native Jujutsu (jj) support

Status: **built**. The preparatory cleanup and every feature ticket
(sections D13 and D14) are merged into main, the last on 2026-11-19; four
follow-up cleanup tickets remain open (Open questions). This is the design
of record: the brief, decisions 1 to 20, and the detailed design adjusted to
them and to the cleanup validation of 2026-11-16. Section D15 lists the pull
requests and where the code differs from the design. Decision 20, taken on
2026-11-23, is not built yet.

## Goal

Add native [Jujutsu](https://jj-vcs.github.io/jj/) (jj) support to Sculptor.
The implementation reuses design patterns already established in the codebase
so that jj lands with a minimum of fuss, edge cases, or weird trees. In return,
Sculptor gains much better support for managing and manipulating workspaces
with jj.

Sculptor presupposes git as the version control system. This work augments
almost every surface where git is used with optional jj support.

## Components

### 1. Vendored jj skill

The jj agent skill at <https://github.com/danverbraganza/jujutsu-skill> is
vendored into the Sculptor repo. A justfile target updates the vendored copy;
running it regularly is the responsibility of the developers.

### 2. jj as an optional managed dependency

jj is an optional managed dependency, following the same structure as pi and
claude:

- It is not required to be installed at startup.
- It is managed from its own page in the settings panel.
- Users either download a managed binary or set the path to a system `jj`.
- With the managed binary chosen, it is the only jj that Sculptor and the
  processes it launches run (decision 20).

**JJ_AVAILABLE** is the master setting for jj: whether jj is enabled at all. It
is not an independent, saved boolean. It is derived: JJ_AVAILABLE is true
exactly when the managed jj or the configured jj binary is reachable and valid.

### 3. Repository configuration

Repositories gain two values, presented on the repository configuration screen.

When JJ_AVAILABLE is false, both controls are displayed but disabled, each with
the tooltip: "Ensure that jujutsu VCS is available in the settings panel to use
these features".

**(a) Is this repository a colocated jj repository?** A switch, derived from
the truth on disk. When on, the repo is a jj colocation and the switch is
locked on: Sculptor never converts a jj repo back to non-jj. Tooltip: "Sculptor
will not destroy your jj colocation. Use the command line to complete this if
you are sure." When off and the user turns it on, the control enters a loading
state, "Initializing jujutsu colocation". When jj succeeds, the switch
transitions to on, and (b) is automatically set to true.

**(b) Use jj for new workspaces created in this repository.** Captures "this is
a jj colocation and I want to use jj while interacting with it". With it on,
the jj features work; with it off, they are intentionally disabled and only git
operations are used. This value is sticky per workspace: a workspace created in
jj mode remains a jj workspace even if the switch is later turned off.

### 4. Workspaces

Sculptor workspaces are jj workspaces. This is the primary change. A workspace
created with the jj flag on becomes a jj workspace. Multiple agents running in
one Sculptor workspace share the same jj workspace.

Every git integration point a Sculptor workspace renders (branch name, target
branch, pull request details, and others) has a jj equivalent in a jj
workspace. The diff panel uses a jj version: "Commits" becomes "Revisions".

Any agent running in a jj Sculptor workspace has the jj skill pre-activated
immediately.

### 5. Settings page contents

Defined in the detailed design, section D11.

## Decisions

Decisions 1 to 7 were taken on 2026-10-28, 8 to 18 on 2026-11-03, 19 on
2026-11-11, and 20 on 2026-11-23; 16 and 19 were revised on 2026-11-13. All
are binding.

1. **The minimum jj version is the pinned version.** Decided at 0.46.0; the
   pin moved to 0.47.1 with PR #504 on 2026-11-11, so the floor is 0.47.1
   from then on. The managed download installs the pin, and JJ_AVAILABLE
   includes the minimum-version check for a system `jj`. One tested baseline
   keeps the surface small, and the flags Sculptor relies on (`jj workspace
   add --no-colocate`; pushing a new bookmark with no extra flag) exist from
   0.46. After a pin bump, developer worktrees must re-run `just install-jj`
   or the jj test fixtures fail with "jj >= <pin> not found". The vendored
   skill states the jj it was tested with, which can trail the pin: "Tested
   with jj v0.46.0" (v0.37.0 when this was decided).
2. **jj workspaces are jj-only, not git worktrees.** A Sculptor workspace
   started with jj is created non-colocated: it contains `.jj` and no `.git`.
   Workspaces started with jj and workspaces started with git are disjoint
   kinds of thing. Everything Sculptor needs in a jj workspace is implemented
   on jj alone, which forces Sculptor and every agent to avoid using git inside
   the workspace.
   - Accepted consequences: tooling inside the workspace that shells out to git
     does not work (build scripts, version stamping, pre-commit and husky
     hooks, lint-staged, editor git integrations such as the VS Code gutter).
     Repos using submodules or LFS cannot use jj mode. The jj implementation
     must be complete before jj mode is usable at all, because nothing
     git-based degrades gracefully.
   - **This is a two-way door.** Should git compatibility inside jj workspaces
     be wanted later, adding git back (colocated secondary workspaces exist
     from jj 0.46) on top of a verified pure-jj implementation is easier than
     building and verifying both at once.
3. **Bookmarks.** A jj workspace may have 0, 1 or many bookmarks. With 0 or
   many, the UI renders something clever (section D10). On the first turn,
   Sculptor attempts to set one bookmark. Agents are reminded on an ongoing
   basis to update the bookmark when it is relevant.
4. **Cleanup is validated by survey, not by a ratchet.** The preparatory
   cleanup is checked by a fresh code survey. Correction from the survey: a
   missed git call inside a jj workspace does *not* always fail loudly. At
   least five existing sites swallow git failures and would degrade silently
   (the PR poller, the terminal diff refresher, the branch-rename hint, one
   diff path, and the turn diff tracker). The seam therefore includes a
   tripwire that raises when git is run in a checkout that has `.jj` and no
   `.git`, and the closing survey checks swallowed-error sites explicitly.
5. **Tests.** jj is pinned in CI and in the offload images.
6. **Terminal agents get no pre-activation.** Only the bundled skill's own
   trigger applies to them. Pre-activation covers Claude SDK chat agents and pi
   agents, which receive a per-workspace system prompt.
7. **Snapshot file-size limit.** jj's maximum snapshot file size is
   configurable. Sculptor's setting and jj's configuration are kept in sync.
8. **A configured jj identity is part of JJ_AVAILABLE.** A missing
   `user.name` or `user.email` is a blocker. The Jujutsu settings page offers
   a one-click form, prefilled from the git identity, that writes the user's
   jj config.
9. **The snapshot file-size limit defaults to 10 MiB**, written into each jj
   workspace's config. jj's own 1 MiB default silently leaves updated
   lockfiles untracked.
10. **Bookmark mechanics.** Sculptor creates the requested bookmark on the
    newest described change at the end of each turn until one exists. A
    deduplicated reminder nudges the agent when the bookmark lags. The Commit
    button also advances it.
11. **Header rendering.** Primary bookmark; a `+N` chip for more; the
    requested name ghosted when there is none; an `↑k` marker when described
    revisions sit above the bookmark; PR status for the primary bookmark only
    in v1.
12. **Mode picker.** When a repository creates jj workspaces, jj replaces
    Worktree in the picker. Clone and In-place stay git under their flags.
    There is no per-workspace git override. Creation is blocked, with a link
    to the Jujutsu page, when jj is unavailable.
13. **Stale working copies are recovered manually**, never automatically.
14. **Deleting a jj workspace deletes its bookmarks too.** The existing
    branch deletion policy (`never`, `delete_if_safe` by default, `always`)
    applies unchanged. Section D3 defines "safe" for jj and uses `jj bookmark
    forget --include-remotes`, which never propagates a deletion to the
    remote on a later push.
15. **jj prompts are optional overrides.** jj-specific commit, PR and
    CI-babysitter prompts live on the Jujutsu page. When unset, the git
    prompts are reused as they are, and Sculptor still appends its
    jj-specific suffix.
16. **Pre-activation** is a first-message Skill-tool reminder plus standing
    rules in the system prompt. The skill ships as its own plugin,
    `sculptor-jj`, loaded for every agent in every workspace (revised
    2026-11-13 with PR #509; the original decision loaded it only in jj
    workspaces). The skill's own description decides when it applies. The
    skill text is not pasted into the system prompt.
17. **Legacy clone mode is out of scope.**
18. **Version policy.** The pin equals the floor (0.46.0 when decided, 0.47.1
    since PR #504), any later 0.x is accepted, bumps are manual, and there is
    no daily bump bot.
19. **Superseded 2026-11-13.** The `sh -c '<script>'` convention for commands
    typed into the user's shell existed only to carry a conditional `${...}`
    expansion in the terminal-agent registration. With the plugin loaded
    unconditionally (decision 16) the registration is a plain command again;
    the wrapper and its style-guide section were removed in PR #509, and the
    loader rejects `${...}` as an unknown placeholder as it did before. For
    the next registration author: the loader rejects any `{...}` that is not
    a known placeholder, zsh does not word-split an unquoted expansion, and
    `${` is a syntax error in fish and tcsh.
20. **The managed jj is the only jj inside Sculptor.** This applies the
    general rule in [Managed tools are overrides inside
    Sculptor](managed_tools.md) to jj.
    - With jj set to Managed, Sculptor and every process it launches run the
      managed jj when they run `jj` by name. That holds in jj and git
      workspaces alike, whatever the user's shell profile puts first on PATH.
    - Workspace terminals put Sculptor's jj first again after the profile has
      run, as terminal agents and the setup command already do.
    - Managed never falls back to a jj on PATH. Without a managed copy, jj is
      not installed.
    - A user who wants Sculptor to run their own jj chooses Custom.
    - A jj the user runs outside Sculptor belongs to the user. When it is too
      old to read what Sculptor's jj writes, Sculptor says so on the Jujutsu
      page and before colocating a repository, and blocks nothing. This
      replaces the `SHADOWED` readiness blocker.
    - D15 lists what is not built yet.

The global default-target-branch user setting was unrelated to this design:
its value was git syntax, which jj mode cannot use. It was deleted
separately, in PR #481, before jj workspaces existed.

## Detailed design (built)

Every jj command and template below was run against jj 0.46.0 in scratch
repositories while designing, and re-checked on the 0.47.1 pin (section
"Verified jj 0.47.1 behaviour"). Code references are relative to
`sculptor/sculptor/` for the backend and `sculptor/frontend/src/` for the
frontend, at main commit `aebfc73d`, where the design started. The code
follows this design except where section D15 says otherwise.

### D1. Workspace and data model

| Change | Detail |
|---|---|
| `WorkspaceInitializationStrategy.JJ_WORKSPACE` | New value in `database/workspace_enums.py`. The column is a plain string, so no migration. "Is this a jj workspace" is never stored separately: it is this strategy, which is creation-only (`WORKSPACE_CREATION_ONLY_FIELDS`), so jj-ness is sticky by construction. |
| `Workspace` fields in jj mode | No new columns. `source_branch` is the base revision symbol; `target_branch` is the target bookmark symbol (`main@origin`, or a local `main`); `requested_branch_name` is the bookmark Sculptor sets after the first turn; `source_git_hash` is the base commit id. The jj workspace name is the workspace id. |
| `Project.use_jj_for_new_workspaces: bool = False` | One migration (`Integer NOT NULL server_default "0"` on `project` and `project_latest`). Added to `ProjectFieldUpdate`. Set to true by the colocate endpoint on success. Cleared when the backend finds the colocation gone. |
| Colocation | Derived from disk, never stored: `<repo>/.jj/repo` is a directory, `<repo>/.git` exists, and `jj git root` resolves to `<repo>/.git`. |
| "Creates jj workspaces" | `use_jj_for_new_workspaces and jj_available and is_colocated`, computed per request. |
| `UserConfig` | `jj_snapshot_max_new_file_size_mib = 10` (decision 9); optional `jj_commit_prompt`, `jj_pr_creation_prompt` and jj CI-babysitter prompts that fall back to the git prompts when unset (decision 15). `DependencyPaths.jj = "MANAGED"` (D7). |
| `DiffArtifact.uncommitted_diff_base: str = ""` | jj sets the commit id of `@-`; git leaves it empty and the frontend keeps `HEAD`. |

Streamed and REST models (`web/data_types.py`):

| Model | Purpose |
|---|---|
| `WorkspaceJjStateInfo` (stream key `workspace_jj_state_by_workspace_id`) | Working-copy change id (full and shortest prefix), description first line, `is_working_copy_empty`, `bookmarks` (local bookmarks on the workspace's stack, nearest `@` first), `primary_bookmark`, `unbookmarked_revision_count`, `requested_bookmark`, `has_conflict`, `is_divergent`, `is_working_copy_stale`. Never sent for git workspaces; `workspace_branch_by_workspace_id` is never sent for jj ones. |
| `WorkspaceTargetBranchesInfo` | Reused. jj values are bookmark symbols (`main@origin`, `main`). |
| `PrStatusInfo` | Unchanged; computed for the primary bookmark. |
| `RevisionInfo`, `RevisionHistoryResponse` | `GET /api/v1/workspaces/{id}/revisions` (409 for git workspaces). Change id, commit id, description, author, timestamp, parent commit ids, files with stats, `is_empty`, `has_conflict`, `is_divergent`, `is_working_copy`, `bookmarks`; plus `fork_point`. Per-revision diffs reuse `/commit-diff` with a commit id. |
| `ProjectJjState` (stream key `project_jj_state_by_project_id`) | `colocation: ABSENT \| INITIALIZING \| COLOCATED \| FAILED`, `colocation_error`, `use_jj_for_new_workspaces`, `preflight {blockers, warnings}`. Re-derived on project activation and on request. |
| `JjReadiness` in `DependenciesStatus.jj_readiness` | As merged in PR #498: a tagged union keyed on `blocker`: `JjAvailable(blocker=None, identity)`, `JjNotInstalled`, `JjNotRunnable(error)`, `JjUnsupportedVersion(path, version)`, `JjNoIdentity(suggested_identity)`. There is no `detail` field; each variant carries data and the UI composes the wording (an unsupported version reads "needs <min> or a newer compatible version", because 1.x is rejected too). JJ_AVAILABLE is "blocker is None" in Python and `jjReadiness.blocker === null` in the frontend (`isJjAvailableAtom`). The generated TypeScript exports no `JjBlocker`; derive it as `NonNullable<JjReadiness["blocker"]>`. A backend gate that raises `JjUnavailableError` composes its message from the variant's data the same way. |

Endpoints: `GET /projects/{id}/jj`, `POST /projects/{id}/jj/colocate` (202,
409 while running, 412 when jj is unavailable), `PUT
/projects/{id}/use_jj_for_new_workspaces` (409 when not colocated), `GET
/projects/{id}/jj/bookmarks`, `GET /workspaces/{id}/revisions`, `POST
/workspaces/{id}/jj/update-stale`, `POST /dependencies/install?tool=JJ`,
`POST /dependencies/jj/identity`. `POST /workspaces` accepts `JJ_WORKSPACE`
and returns 412 when jj is unavailable, 400 when the repo does not create jj
workspaces, 409 on a bookmark collision.

### D1a. Creation funnel invariants

Decided 2026-11-05 with cleanup ticket P7. These hold for git and jj alike.

- `POST /api/v1/workspaces` is the only way to create a checkout. Its
  `initialization_strategy` is the single discriminator (git in-place, clone,
  worktree; jj workspace). One validator checks every request
  (`_validate_workspace_creation_request`, landed with P5), and one
  `WorkspaceVcs.create_checkout` per VCS implements it.
- `POST /api/v1/workspaces/{id}/agents` is the only way to create an agent.
  The tasks route keeps working for callers that pass `workspace_id`; its
  implicit-workspace form, which defaulted to an in-place workspace and never
  worked for worktrees, was removed by P7 (SCU-1863, PR #503). Turning the
  tasks route into a thin alias of the agents endpoint, or retiring it, is a
  nice-to-have follow-up once the public-API posture is confirmed.
- Clients compose the two endpoints; `sculpt run` already does. No endpoint
  creates a workspace without passing the validator.

### D2. The VCS seam

New package `services/workspace_service/vcs/`:

| Module | Contents |
|---|---|
| `interfaces.py` | `WorkspaceVcs` and `TurnDiffTracker` (ABCs) |
| `data_types.py` | FrozenModels: `CheckoutSpec`, `CheckoutLocation`, `GitHeadIdentity`, `JjHeadIdentity`, `JjRevisionRecord`, `RevisionHistory`, `RevisionDiff`, `PullRequestRefs`, `AgentVcsEnvironment` |
| `git_workspace_vcs.py` | `GitWorkspaceVcs`: existing code moved unchanged from the workspace service, the worktree strategy and the PR poller |
| `jj_workspace_vcs.py` | `JjWorkspaceVcs`, plus jj-only operations: colocation, bookmark list, update-stale, batched scan for the poller, first-turn bookmark |
| `jj_cli.py` | runner, typed errors (`JjUnavailableError`, `JjWorkingCopyStaleError`, `JjCommandFailure`), pure revset and template builders, JSON-line parsers |
| `turn_diff_tracker.py` | `make_turn_diff_tracker(environment)` and `JjTurnDiffTracker` |

The service selects the implementation with `match` on the strategy
(IN_PLACE, CLONE, WORKTREE give git; JJ_WORKSPACE gives jj; `assert_never`).
Agents hold only an `AgentExecutionEnvironment` and select through the
factory, which resolves jj with `get_tool_binary_path(Dependency.JJ)`.

`WorkspaceVcs` methods, each with a git and a jj implementation:

| Method | git (moves from) | jj | Replaces |
|---|---|---|---|
| `create_checkout` | worktree add / clone | `jj workspace add` (D3) | `local_environment.py:206-246` |
| `verify_checkout` | no-op | `<code>/.jj/repo` exists; re-apply workspace config | environment resume |
| `remove_checkout` | worktree remove | `jj workspace forget` (D3) | workspace delete |
| `resolve_default_target` | origin HEAD, then main/master | `trunk()` | `default_implementation.py:306-412` |
| `list_target_candidates` | remote and local branches | `jj bookmark list --all-remotes` | `web/app.py:3575-3605`, poller |
| `validate_new_ref_name` | `check-ref-format` | `check-ref-format` plus bookmark-existence revset | `web/app.py:866-875` |
| `resolve_base_commit_id` | `rev-parse` | `jj log -r <base> -T commit_id` | `default_implementation.py:432-433` |
| `default_setup_command` | `git fetch origin` | `jj git fetch --remote origin` | `api.py:35-50` |
| `read_identity` | current branch | single-workspace form of the poller query | cold-cache REST paths |
| `compute_diff_artifact` | `git diff` paths | D2 recipe below | `default_implementation.py:895-1063` |
| `get_revision_history` | merge-base plus three `git log` calls | one `jj log` with a JSON template | `default_implementation.py:1396-1626` |
| `get_revision_diff` | `diff-tree` | `jj diff -r <commit_id> --git` | `web/app.py:1304-1333` |
| `list_files` | `ls-files` | snapshot, then `jj file list -T 'json(path)'` | `web/app.py:1612-1653` |
| `read_file_at_revision` | `git show` | `jj file show -r <commit_id> 'root-file:"<path>"'` | `web/app.py:1699-1725` |
| `discard_file_changes` | checkout plus clean | `jj restore 'root-file:"<path>"'` | `web/app.py:1336-1366` |
| `get_pull_request_refs` | current branch plus origin URL | D5 | `pr_polling_service.py:864-903` |
| `agent_environment` | empty | `jj-bin` on PATH, `GH_REPO` (D6) | agent and terminal launch sites |
| `compute_change_fingerprint` | `status --porcelain` plus HEAD | snapshotting `jj log -r @ -T commit_id` | `diff_refresh.py:61-91` |

Runner rules for every Sculptor jj call: the resolved absolute binary,
`--no-pager --color=never -R <dir>`, cwd `<dir>`, machine output (`-T
'json(...)'` or `--git`), a required snapshot-policy argument with no default
(`IGNORE_WORKING_COPY` or `SNAPSHOT`), paths taken only from root-relative
template or `--git` output, revset literals built as `exact:` patterns, commit
ids validated as hex, a 30 s timeout. The pattern for a request that reads
several things: snapshot once, read the working-copy commit id, then make every
follow-up read `--ignore-working-copy` pinned to that id. Policies:

| Caller | Policy |
|---|---|
| poller, PR polling, bookmark list, file show, revision diff, colocation checks | `IGNORE_WORKING_COPY` |
| diff refresh, file list, revision history, discard, turn baseline and end, terminal fingerprint, first-turn bookmark | `SNAPSHOT` once, then pinned reads |
| `workspace add`, `git init --colocate`, `restore`, `update-stale` | must snapshot (`add` refuses `--ignore-working-copy`) |

Diff recipe: snapshot and read the working-copy commit `W` and its parents;
the uncommitted diff is `jj diff -r <W> --git` (jj has no untracked files, so
the untracked-files pipeline goes away); with a target `T`, the merge base is
`latest(fork_point(<T> | <W>))` and the target diff is `jj diff --from <M>
--to <W> --git`. Snapshot warnings ("Refused to snapshot some files") are
parsed into `file_errors`.

Git tripwire (decision 4): the shared git runners raise
`GitCommandInJjWorkspaceError` when the working directory has `.jj` and no
`.git`.

Per-turn diff tracking: `TurnDiffTracker` with `rebaseline`,
`compute_diff_for_tool`, `get_changed_file_paths`, `to_repo_relative_path`.
The existing `DiffTracker` implements it unchanged for git. The jj tracker
baselines on the working-copy commit id, reads old file content with `jj file
show`, reuses `create_unified_diff` (which needs no repo), and lists changed
paths with `jj diff --from <B> --to <W> --name-only`.

### D2a. The seam as merged, and what jj changes

The seam landed with these shapes (main at `c62b1ce5`), which differ from the
table above in ways the jj tickets rely on:

- Repository-scoped methods take the user's repository path; checkout-scoped
  methods take a `CheckoutLocation` (repository path and checkout path), not a
  bare working directory. The runner is `GitCli`, built from a binary resolver
  callable; errors are the `VcsCommandError` family; the tripwire is
  `GitCommandInJjWorkspaceError`, deliberately outside that family.
- A checkout is created lazily, in the task runner when a workspace's first
  agent starts, not by `POST /workspaces`, which only stores the row.
- Changes jj needed, made in cleanup round two and the jj tickets:
  `CheckoutSpec` and `CheckoutLocation` gained a `checkout_name` (the
  workspace id), because jj names its workspaces and the checkout path is a
  random directory; `read_identity` and `get_revision_history` return a
  per-VCS union instead of git-only types; `get_pull_request_refs` and
  `remove_checkout` take the workspace's target, which jj needs to find the
  workspace's own stack; `DiffArtifact` gained `uncommitted_diff_base`.
- One function in the `vcs` package selects the implementation for a
  workspace kind, and one builds the runners, so jj is added in one place.

### D3. jj workspace lifecycle

**Create.** Validated in `create_workspace_v2`: jj available (else 412), the
repo creates jj workspaces (else 400 or 409), the bookmark name is required,
contains no `@`, passes `git check-ref-format --branch` in the colocated main
repo, and no local or remote bookmark of that name exists (else 409). The
default target is the remote bookmark on `trunk()` (`main@origin`), falling
back to local `main` then `master`; the base defaults to the target. Then, with
cwd at the main repo:

```
jj -R <repo> --no-pager --color=never workspace add --no-colocate \
   --name <workspace_id> -r '<base revset>' --sparse-patterns full <environment_id>/code
```

Base revset from a symbol: `name@remote` gives `remote_bookmarks(exact:"name",
exact:"remote")`; `name` gives `bookmarks(exact:"name")`; a commit id is used
verbatim. `origin/main` does not resolve in jj. The parent directory must
exist. The call snapshots the user's main working copy, which is normal jj
behaviour. If a workspace of that name already exists (a lost environment), it
is forgotten first with a warning. After creation: write the workspace-level
jj config (D6), copy `.sculptor/.env` as worktree mode does, and run the setup
command (default `jj git fetch --remote origin 2>/dev/null || true`) with jj
on PATH. Git-style validation of the request happens through one validator
shared by every creation entry point (cleanup ticket P5).

**Resume.** jj workspaces are durable; `verify_checkout` checks
`<code>/.jj/repo`, re-applies the workspace config idempotently, and raises
`EnvironmentNotFoundError` otherwise, which takes the existing re-create path.

**Delete.** Read the workspace config path first (only if
`<code>/.jj/workspace-config-id` exists, because `jj config path` creates the
directory as a side effect), resolve the bookmarks to delete (below), run `jj
-R <repo> --ignore-working-copy workspace forget <workspace_id>` (idempotent;
snapshots nothing; works when the directory is already gone), forget those
bookmarks, delete that config directory, then remove the environment
directory. An empty undescribed `@` is abandoned; anything else stays as a
visible head, recoverable from `jj log`.

Bookmark deletion (decision 14) applies the existing
`workspace_branch_deletion_policy`, unchanged, to the workspace's own
bookmarks: the local bookmarks on `fork_point(T | @)..@`, excluding the target
and any bookmark that also sits on another live workspace's stack. `never`
keeps them. `delete_if_safe` (the default) deletes a bookmark only when it is
safe: its commit is an ancestor of the target bookmark, or it tracks a remote
bookmark that points at the same commit (fully pushed). Unsafe bookmarks are
kept and logged, as `git branch -d` refuses unmerged branches. `always`
deletes them all. Deletion uses `jj bookmark forget --include-remotes
<names>`, never `jj bookmark delete`: forget drops the local bookmark and its
remote-tracking entry without scheduling a remote deletion, so no later push
by the user can delete a remote branch as a side effect, and if the branch
still exists on the remote the next fetch lists it again as an untracked
remote bookmark. Forgetting a bookmark never abandons commits; under `always`,
unmerged work stays visible as an anonymous head until the user abandons it.

**Orphans at startup.** For each colocated project, `jj workspace list -T
'name ++ "\t" ++ root ++ "\n"'`; forget names that parse as a Sculptor
workspace id and whose root is missing on disk or soft-deleted in this
database. Never forget a workspace whose root exists, so a second Sculptor
instance on the same repo is safe.

**Stale working copies.** Detection is reactive: a snapshotting call fails
with "The working copy is stale", raising `JjWorkingCopyStaleError`; the
workspace is marked stale and the poller re-emits with
`is_working_copy_stale`. Reads with `--ignore-working-copy` keep working. The
UI shows a banner with an "Update working copy" action that calls `POST
/workspaces/{id}/jj/update-stale`; it is never automatic, because
`update-stale` with unsnapshotted edits produced a divergent change and a
conflicted bookmark in a scratch repository (decision 13). Agents see jj's
own error and the mode prompt tells them what to do.

**Concurrency.** Sculptor reads use `--ignore-working-copy` (no lock, no
operation). jj's working-copy lock serializes Sculptor snapshots against agent
commands (a snapshot every 50 ms during 48 agent operations gave no errors and
no divergence). The default base is a remote bookmark, which is immutable, so
agents cannot rewrite the user's stack without `--ignore-immutable`. A bookmark
created in a jj workspace becomes a git branch in the main checkout only after
a mutating jj command there or `jj git export`, so bookmark collision checks
and target lists use jj, never git.

**Colocation init** (`POST /projects/{id}/jj/colocate`). The repo is the
project path, already resolved to the main repo. Pre-flight, also returned by
`GET /projects/{id}/jj`:

| Check | Severity |
|---|---|
| jj unavailable | blocker |
| `.jj` present but not colocated with this `.git` | blocker |
| submodules (`.gitmodules` or `git submodule status`) | blocker (decision 2) |
| LFS (`filter=lfs` in a tracked `.gitattributes`) | blocker (decision 2) |
| git operation in progress (merge, rebase, cherry-pick, revert) | blocker |
| hooks (`core.hooksPath`, `.git/hooks`, `.husky/`, `.pre-commit-config.yaml`) | warning: hooks do not run in jj workspaces |
| sparse checkout | warning |
| dirty tree | info: the changes become jj's working-copy commit |

The server sets `INITIALIZING` on the stream, runs `jj git init --colocate
<repo>` on a background thread with a 10-minute timeout, verifies `jj git
root` equals `<repo>/.git`, then sets `COLOCATED` and writes
`use_jj_for_new_workspaces = true` itself, so the result survives a closed
window. It tracks no bookmark: with `main@origin` left untracked, as init
leaves it, an agent's `jj git fetch` moves only `main@origin`, and the user's
local `main` and checked-out git branch stay where they are (verified on
0.47.1). Targets and bases are remote bookmarks, which need no tracking. Failure sets `FAILED` with the error text. The user's git HEAD stays on
its branch. There is no de-colocation endpoint.

### D4. The jj poller

A new `JjWorkspacePoller` beside the branch poller, same 3-second loop, same
forced recompute every 20 cycles. The branch poller filters out jj workspaces.
Per cycle: group live jj workspaces by repo store (read `<code>/.jj/repo`,
which holds a relative path to the main store); stat
`<store>/op_heads/heads`, whose file names change on every jj operation, so an
idle repo costs zero forks; for a changed repo run at most two commands,
however many workspaces it has:

1. One `jj log --ignore-working-copy` over
   `::(present("<ws1>"@) | present("<ws2>"@) | <T1> | <T2>) & mutable()` with
   a JSON-line template (change id, shortest prefix, commit id, parents,
   working copies, local and remote bookmarks, description first line, empty,
   conflict, divergent).
2. `jj bookmark list --all-remotes -T 'json(self) ++ "\n"'` for target
   candidates (drop the `git` remote; skip conflicted bookmarks).

A pure, unit-tested projection derives each workspace's stack (ancestors of
its `@` minus ancestors of its target, within the result), then
`WorkspaceJjStateInfo` and the primary bookmark (D5). Publishing is
value-deduplicated; the state carries no commit ids, so snapshots alone do not
re-emit. A changed working-copy change id triggers a diff refresh; a changed
primary bookmark notifies the PR poller. The cached state backs REST responses
and the bookmark reminders.

### D5. Pull requests in jj mode

Head selection is a pure function shared by the poller and PR polling. With 0
bookmarks on the stack there are no candidates and `pr_state` is `none` with
no `gh` calls. With 1, use it. With many: nearest revision to `@` first; on
the same revision, the requested name, then names with a tracked remote, then
alphabetical. A candidate equal to the target name is dropped. The batched
round tries candidates in order; the per-workspace fallback queries the first
only, so `gh` call counts match git mode. The base is the target bookmark's
bare name. `GH_REPO` is `HOST/OWNER/REPO` parsed from the `origin` entry of
`jj --ignore-working-copy git remote list`; a non-GitHub origin gives `none`
as in git mode. `gh` runs with cwd at the checkout (no `.git`) and `GH_REPO`
in its environment, and the GraphQL queries pass owner and name explicitly
instead of relying on placeholder resolution.

### D6. Agent environment, pre-activation and bookmark hooks

**PATH.** `<internal>/jj-bin/jj` is a symlink to the resolved binary (managed
or custom), maintained like `sculpt-bin`, re-linked atomically when the target
changes and removed when jj is unresolvable. It is prepended at the four
launch sites: chat agents, terminal agents, workspace terminals, and the
setup-command subprocess. Sculptor's own calls use the absolute path.

Decision 20 (2026-11-23) revised this paragraph in two ways:

- jj-bin is prepended in every workspace. It was prepended only in jj
  workspaces.
- It is put first again after a login profile has run. Workspace terminals
  did not re-apply it.

**Environment.** `GH_REPO` as in D5 (never forced over a user's own value in
terminals). `JJ_EDITOR=false` for chat agents only, so an editor-invoking jj
command fails fast instead of hanging. `GIT_DIR` and `GIT_WORK_TREE` are never
set. `GIT_CEILING_DIRECTORIES` is set to the environment directory, so a `git`
typed inside a jj workspace fails instead of finding an enclosing repository;
when Sculptor runs from source, workspaces live inside its own git checkout.

**jj configuration.** Sculptor's per-workspace settings go into jj 0.46's
workspace-level config (`jj -R <code> --ignore-working-copy config set
--workspace ...`), which every jj process in that workspace reads, including a
human's shell, and which never touches the user's own checkout. `JJ_CONFIG` is
rejected: it replaces the user's config files and ranks below repo and
workspace config. `--config` flags are used only on Sculptor's own calls.
Settings written: `snapshot.max-new-file-size` from the Sculptor setting
(decision 9), at create, at resume, and whenever the setting changes; the value also
appears in the mode prompt. Identity is a precondition (D7), not an override.

**Mode prompt.** `LocalEnvironment.get_system_prompt()` is an exhaustive
match; jj workspaces get a jj mode prompt instead of the worktree prompt. It
states: the directory has `.jj` and no `.git`, so every `git` command fails;
use `jj` for all version control; the working copy is the commit `@` and every
jj command snapshots into it; the repo is shared with the user's checkout and
other workspaces, so never rewrite revisions outside your own stack and never
run `jj undo`, `jj op restore` or `jj workspace forget`; always pass `-m`;
name your work with a bookmark and move it onto your latest described change
before pushing; push only with explicit permission (`jj git push -b <name>`);
`gh` works because `GH_REPO` is set, so pass `--head <bookmark>`; files larger
than the configured limit are not snapshotted, tell the user rather than
changing jj's configuration; on "The working copy is stale", run `jj
workspace update-stale`, check `jj st`, and report it. It also says the
`jujutsu` skill is required and must be loaded if its instructions are not in
context.

**Pre-activation** (decision 16). Three layers: the standing rules above in the
system prompt (survive compaction and `/clear`); a first-message system
reminder, reusing the existing skill-invocation reminder, that tells the agent
to invoke `sculptor-jj:jujutsu` with the Skill tool before anything else; and
the bookmark reminders below. For pi, the first prompt is prefixed with
`/skill:jujutsu` through the existing skill-rewrite path, with a first-turn
marker file in the agent state directory cleared on context clear. Terminal
agents get only the plugin directory (decision 6).

**Bookmarks** (decisions 3 and 10). After each turn until a bookmark exists,
the workspace service runs `attempt_initial_bookmark`: snapshot; skip if any
local bookmark is on `fork_point(T | W)..W` or the requested name already
exists; compute the newest non-empty described revision in that range
(`heads(range ~ (empty() & description(exact:"")))`), require exactly one, and
`jj --ignore-working-copy bookmark create <requested_name> -r <that>`. The
first-message reminder replaces the auto-rename branch block and explains the
bookmark that Sculptor will create. An ongoing nudge, sent at most once per
state (keyed on bookmark change id and newest-described change id, stored in
the agent state directory), fires when described work sits above the single
bookmark or when there is described work and no bookmark; with several
bookmarks nothing is sent, because that is deliberate. The branch-rename hint
returns nothing for jj workspaces, so it never runs git there.

### D7. Managed dependency, JJ_AVAILABLE and pin tooling

`JjManagedTool` follows pi:

| Topic | Choice |
|---|---|
| Version constant | import-free `services/jj_version.py` with `JJ_PINNED_VERSION = "0.46.0"` |
| Pin table | `JJ_PIN`, shaped like `PI_PIN`, sha256 per platform baked in by `just bump-jj`; asset names derived from the version |
| Platforms | `darwin-arm64`, `darwin-x64`, `linux-x64`, `linux-arm64` (static musl builds), mapped to the upstream target triples |
| Version policy (decision 18) | `min = pin = 0.46.0`, `max = 0.999.999`, recommended = pin. Any later 0.x passes, so a Homebrew jj chosen as Custom keeps working; a bump raises the floor |
| `binary_subpath` | `jj` (the tarball holds `./jj`, `./LICENSE`, `./README.md`) |
| Startup | never installs when missing; refreshes an existing managed copy that fell out of range |
| MANAGED with no download | `NOT_INSTALLED`, with the download offered; never a `jj` found on PATH. Decision 20 (2026-11-23) revised this; it fell back to a `jj` on PATH and reported `source=EXTERNAL`, like pi |
| Version parsing | own parser: `^jj (\d+\.\d+\.\d+)(?:-\S+)?$`, because the shared parser keeps the `-<hash>` suffix and `packaging.Version` rejects it |
| Probe output | every managed tool reads both stdout and stderr; `DependencyCheckResult.probe_error` carries stderr so a broken jj config reads as "not runnable" with the real message, not "not installed" |
| Install flow | reused as is (`install_managed` to `_download_verify_stage` to atomic rename) |

Places that must name the new tool: the `Dependency` enum, `DependencyPaths.jj`,
an exhaustive `_configured_binary_value(config, tool)` replacing the
`else: continue` in `_auto_install_if_needed` (which would otherwise silently
skip jj), a `resolve_binary_path` case, a shared optional-tool status builder
used by pi and jj, `DependenciesStatus.jj` and `jj_readiness`, test ids in
`constants.py`, the frontend `useManagedDependency` tool table (before this
work, a third tool would silently have read pi's status), fixtures that
build a full `DependenciesStatus`, the registry assertion in
`managed_tools_test.py`. The
`tool=CLAUDE` defaults on `_get_managed_version` and `is_version_in_range` are
removed so a forgotten argument cannot check jj against Claude's range.

**JJ_AVAILABLE** is computed in one backend place,
`DependencyManagementService.get_jj_readiness()`, and never persisted (as built,
D15: the service keeps the last computed value in memory for display, and
every gate recomputes it). The first
failing check wins: `NOT_INSTALLED` (no resolved path), `NOT_RUNNABLE` (`jj
--version` fails; detail is the first stderr line), `UNSUPPORTED_VERSION`
(does not parse or is out of range), `NO_IDENTITY` (`user.name` or
`user.email` empty in `jj --ignore-working-copy config list user`, probed with
the same environment agents get, so `JJ_USER`/`JJ_EMAIL` count) (decision 8). It
reaches the frontend through the dependencies status stream; the frontend atom
fails closed while status is unknown, because what it gates writes to the
user's repo. The settings page and the repository configuration screen fetch
status on mount and offer a "Re-check" button, since identity or PATH changes
made outside Sculptor send no event. Server-side gates: colocation init,
turning (b) on, creating a jj workspace, and creating or resuming a jj
environment (a structured `JjUnavailableError` shown in the agent panel).
Existing jj workspaces get a banner when it turns false; nothing destructive
happens.

**Identity** (decision 8). When jj has no identity, the Jujutsu settings page shows
a form prefilled from `git config --global user.name` and `user.email`;
submitting runs `jj config set --user` for both and pushes fresh status.
Sculptor does not inject `JJ_USER`/`JJ_EMAIL` silently, because that would
diverge from the user's own jj in the same repo. Without an identity,
colocation init writes an unpushable, authorless working-copy change into the
user's checkout, which is why identity gates it.

**Pin tooling.** `just install-jj` (dev and CI; verifies sha256; the
already-installed check parses `jj 0.46.0-<hash>` correctly), `just
compute-jj-pin <version>`, `just bump-jj <version>` (hashes the four tarballs,
cross-checks against the GitHub release API's per-asset digest since jj
publishes no SHA256SUMS, rewrites the version and digests with exact-count
edits and a stale-residue check). The pi scripts were generalized first in a
pi-only preparatory PR (`scripts/managed_pin.py` with a per-tool spec table;
T1, PR #482) rather than copied. A non-gating freshness warning in CI; no
daily bump bot, because each bump raises the floor for system-jj users.

**Settings bug fixed first** (cleanup ticket P6). `PUT /config` with a partial
`dependencyPaths` is shallow-merged, so saving one tool's path resets every
other tool's path (reproduced). `merge_config` merges sub-model fields one
level deep; map-typed fields keep replace semantics.

### D8. Vendored skill

The upstream skill is vendored as its own plugin and loaded for every agent
(decision 16):

```
sculptor/sculptor-jj/
├── .claude-plugin/plugin.json      name "sculptor-jj"
├── UPSTREAM.toml                   provenance, written by `just update-jj-skill`
└── skills/jujutsu/
    ├── SKILL.md                    byte-identical to upstream jujutsu/SKILL.md
    └── LICENSE                     byte-identical to upstream LICENSE (MIT)
```

The skill id is `sculptor-jj:jujutsu` for Claude and `jujutsu` for pi.
`get_plugin_dirs()` returns the four bundled plugins with `sculptor-jj` last,
because the test fake reads only the first plugin directory. `UPSTREAM.toml`
records the repository, requested ref, resolved commit, fetch date, license
and per-file sha256; a unit test checks the digests and that the frontmatter
name is `jujutsu`. `just update-jj-skill ref="main"` resolves the ref to a
commit through the GitHub API, mirrors the upstream `jujutsu/` directory plus
the root `LICENSE` at that commit, fails if the name or the license changed,
replaces the directory atomically, rewrites `UPSTREAM.toml`, and prints the
upstream compare URL. The vendored file is never edited locally.

Terminal agents get the plugin through the bundled registration, which lists
it as a fourth plain `--plugin-dir "$SCULPT_PLUGINS_DIR/sculptor-jj"`;
`SCULPT_PLUGINS_DIR` is exported for every terminal agent. The sidecar build
(`--add-data`) and the Linux backend image (`COPY`) include the directory, and
a test checks both. Pre-activation for chat agents (D6) is unchanged: the
first-message reminder invokes `sculptor-jj:jujutsu`.

### D9. Repository configuration controls

Placement: a self-contained `RepoJjControls` rendered last inside the expanded
repo row, plus a `jj` badge in the row header when the repo creates jj
workspaces. Stores, one writer each: `projectJjStateAtomFamily` written only
by the stream; `useJjForNewWorkspaces` on the project row, written only by the
project stream; `isJjAvailableAtom` derived from the dependencies status.

Control (a): clicking the off switch opens a confirmation dialog that fetches
the pre-flight; blockers disable confirm, warnings are listed; the body says
what will run and that git keeps working. Confirm posts the colocate request;
nothing is written ahead of the server. The rendered state is a pure function
of stream state, mutation state and availability: `UNAVAILABLE` (disabled,
tooltip from the brief, link to the Jujutsu page), `INITIALIZING` (disabled,
spinner, "Initializing jujutsu colocation"), `ON_LOCKED` (checked, disabled,
tooltip from the brief), `FAILED` (off, error text, retry), `OFF`. An HTTP
error shows a toast; nothing needs rolling back. The 10 s settle timeout
resets a mutation whose `INITIALIZING` frame never arrives.

Control (b): a mutation in `common/state/mutations/` with no store write; the
switch renders the requested value while pending; the PUT resolves only after
the frame carrying the updated project, so success needs no write and failure
leaves the store untouched. Disabled with the brief's tooltip when jj is
unavailable, else with "Initialize the jujutsu colocation first" when not
colocated. Description: "New workspaces in this repository are jj workspaces,
with no git inside. Existing workspaces keep their kind."

The controls appear only on the Repositories page. Read-only indicators
elsewhere: the repo-row badge, a `jj workspace` chip in the create dialog that
links to repo settings, the workspace header badge, and the Jujutsu page's list
of jj repos with Configure links.

### D10. UI surfaces in jj mode

A component learns the kind through a pure helper on the streamed workspace
(`initializationStrategy === "JJ_WORKSPACE"`). Adding the enum value breaks the
two exhaustive label maps at compile time, which forces both to handle jj.
Rule: different data shape gives a sibling component behind a thin switch
(identity pill, revision list); same shape with different words gives one
component with a `vcs` prop; same shape and words means the backend dispatches
and the frontend is unchanged (diff text, file tree, file content, discard, PR
status).

| Surface | jj mode |
|---|---|
| Header identity pill | `JjIdentityPill` (decision 11): primary bookmark; `+N` chip when more bookmarks; `↑k` amber marker when `k` described revisions sit above the bookmark (header only); with 0 bookmarks the requested name ghosted (dashed, muted), or else the change id and description; a `conflict` badge; a hover card listing bookmarks, change id, commit id, description, flags and target. Click copies the bookmark, or the change id when there is none |
| Mode badge | always `jj`, tooltip "jj workspace — no git inside. Agents use jj here." |
| Target selector | bookmark symbols (`main@origin`), tooltip "Target bookmark"; remote-name helpers replace the `origin/` literals; no fallback to the git-syntax global default |
| Revisions panel | tab "Revisions"; rows for `fork_point(target \| @)..@` including `@` (muted when empty); description first line or "(no description set)"; change id with unique prefix bold; stats, time, commit id; chips for bookmarks, working copy, empty, conflict, divergent; footer "fork point (main@origin · <id>)"; selection keyed by change id, diffs fetched by commit id. The panel id stays `commits` because persisted layouts key on it |
| Changes panel | scopes "All" and "Working copy" (the diff of `@` against its parent); discard runs `jj restore` and the copy says the content is recoverable from the operation log |
| Diff viewers | the uncommitted base comes from the artifact (`@-`), the target base from the fork point; no `HEAD` literal |
| PR button and dropdown | unchanged states; status keyed on the primary bookmark; the create prompt names the bookmark and base; with 0 bookmarks it asks the agent to create the requested bookmark first |
| Commit button | same label; sends the jj commit prompt, or the git commit prompt when the jj one is unset, plus "advance the bookmark" (decision 15) |
| Create dialog | when the repo creates jj workspaces, the Worktree option becomes `jj workspace` and is selected (decision 12); Clone and In-place remain git under their flags; source picker lists bookmarks; the name field reads "Bookmark name (required)" and validates against bookmarks; when jj is unavailable, Create is disabled with a callout linking to the Jujutsu page |
| Chat intro | "jj workspace on <source> from <repo> at <time>" and a line that the workspace has no git |
| Rows, peek, mobile, palette, extension hooks | one identity-label hook (cleanup ticket F1) returns text, copy text and icon for both kinds; the extension `WorkspaceView.branch` holds the primary bookmark or null, with additive `vcs` and `bookmarks` fields |

Copy changes follow from the table: Commits to Revisions, branch to bookmark,
Uncommitted to Working copy, and jj-worded commit, PR and CI-babysitter
prompt defaults.

### D11. Settings page: Jujutsu

Registered in the Project group after Git, built from the pi page template.
Rows: availability callout (available with version and source; or the
blocker with its detail and the action that fixes it: install, set a path,
set identity); binary source (Managed or Custom); status and detected version
against the minimum; managed installation (install, progress, retry, up to
date); binary path (Custom); author identity (read-only when present; the
one-click form from D7 when missing); maximum new file size in MiB, default
10 (decision 9); optional jj commit and PR prompts with a one-click suggested
wording, falling back to the git prompts when unset (decision 15);
repositories using jj with Configure links;
links to the jj documentation and the Sculptor help page. Controls (a) and
(b) are not on this page. A "Re-check" button refreshes status.

### D12. Test strategy

| Item | Choice |
|---|---|
| Pin | `install-jj` in the justfile (mirrors `install-pi`, verifies sha256, called by `install` and by the backend unit and integration test recipes); a `Install jj` step in the checks workflow; an `ARG JJ_VERSION` layer in `.devcontainer/Dockerfile`, which backs every offload lane; a unit test asserts the Dockerfile and the pin agree |
| Finding the binary | a resolver (`<venv>/bin/jj`, then PATH, first binary at or above the pin), never bare PATH, because a developer machine can have an older jj earlier on PATH. Production resolves jj through `resolve_binary_path` (D7) and runs it by absolute path |
| Absent or too old | fail with the `just install-jj` hint, never skip; a skip would turn the suite silently green |
| Harness | `dependency_paths.jj` is pinned to an unresolvable value in the test user config so JJ_AVAILABLE is off unless a test opts in |
| Fixtures (`testing/jj_repos.py`, registered in the top-level conftest) | `jj_binary` (session), `jj_isolated_env` (`JJ_CONFIG` empty file, `JJ_USER`, `JJ_EMAIL`, isolated git config), `jj_colocated_repo` (bare remote, `jj git init --colocate`, `jj bookmark track main@origin`), `jj_workspace` (raw CLI, as an oracle independent of the implementation), `make_github_looking_origin` (`pushInsteadOf` to a bare repo), `make_workspace_stale` (`jj op restore` in the main repo) |
| Managed-install tests | offline, as for pi: pre-stage a binary under the managed versions directory; stub scripts for not installed, installed and too old; install failure via route interception; the existing download guard covers jj |
| Unit coverage (real jj, no mocks) | version parser and readiness blockers; colocation detect and init (idempotent, HEAD unchanged, tracks the remote bookmark, pre-flight mutates nothing); workspace create (no `.git`, parent is the base, name used, collision raises cleanly, concurrent creates succeed); no-git guard; revisions; diffs; file at revision with validation; read-only queries add no operation; bookmarks 0/1/many; poll state key; push and fetch (identity and description errors); target change; discard; snapshot-size sync surfaces refused files; stale recovery; forget semantics; error mapping |
| Integration (Playwright, per-test instance because the shared one wipes `.jj`) | colocation init control; colocation detected from disk; controls disabled without jj; use-jj toggle and stickiness; create jj workspace and see a file under Revisions; header identity; Revisions panel; target bookmark change; discard; PR button keyed on the bookmark (fake `gh` fed from a nodes file, since it cannot read the head from `.git`); stale recovery; delete; settings page offline; jj on the agent's PATH with jj stripped from the backend PATH; skill pre-activation via a fake-agent system-prompt report. The fake agents need no jj awareness: their `bash` command runs jj |
| jj in jj | jj shells out to `git` for fetch and push, so git stays a required dependency in jj mode |

### D13. Preparatory cleanup tickets

Prerequisites, partitioned by files so they can run in parallel. Filed in
Linear on 2026-11-03 under the tracking issue SCU-1847, with blocking
relations for the waves:

Status: every ticket in this table is done. Waves 1 and 2 merged by
2026-11-13: T0 #484, T1 #482, S1 #486, P1 #505, P2 #500, P3 #507, P4 #508,
P5 #489, P6 #488, P7 #503, F1 #493, F2 #491, F3 #490, F4 #485, F5 #492.
Feature slices A (SCU-1866, #502) and B (SCU-1867, #498) merged with them.
The seam lives at `services/workspace_service/vcs/` with the D2 interface,
built from a binary resolver (PR #499). Z1, the survey gate, has no pull
request; it closed once round two's R1 and R2 merged (below). The dead
default-target-branch setting was removed separately (PR #481).

| ID | Ticket | Title | Owns | After | Size |
|---|---|---|---|---|---|
| T0 | SCU-1848 | Pin jj 0.46.0 in CI and offload; add `install-jj` and jj test fixtures | justfile, checks workflow, devcontainer Dockerfile, `services/jj_version.py`, `testing/jj_repos.py`, top-level conftest, testing docs | none | M |
| T1 | SCU-1849 | Generalize the pi pin scripts into a per-tool spec table (pi-only, no behaviour change) | `scripts/*pin*.py` and tests, justfile targets, the pi bump workflow | none | S |
| S1 | SCU-1850 | Introduce the VCS seam with a git implementation and the git tripwire | new `services/workspace_service/vcs/` only | design agreed | L |
| P1 | SCU-1851 | Move workspace-service git onto the seam (diffs, history, files, file at ref, discard; delete the dead diff base ref; stop resuming environments to find a working directory) | workspace service default implementation and api, their tests | S1 | L |
| P2 | SCU-1852 | Move the branch poller onto the seam; report instead of skipping a checkout with no `.git` | branch poller, git ref scanning | S1 | M |
| P3 | SCU-1853 | Move PR polling onto the seam; fix `strip_remote_prefix`; route `gh` through the seam | PR polling service, PR status, CLI status utils | S1 | M |
| P4 | SCU-1854 | Move agent-runtime git onto the seam (turn diff tracker, branch-rename hint, terminal diff refresh); delete the agents-to-tasks import | those modules | S1 | M |
| P5 | SCU-1855 | One validator for every workspace-creation entry point | `web/app.py`, `web/data_types.py`, their tests | none | S |
| P6 | SCU-1856 | Deep-merge nested settings on `PUT /config` | user config service | none | S |
| P7 | SCU-1863 | Remove implicit workspace creation from the start-task route (its worktree case has never worked and nothing calls the path) | `web/app.py` start-task route, `web/data_types.py`, their tests | P5 | S |
| F1 | SCU-1857 | Derive a workspace's identity label and target from one source (13 frontend files; drop the source-branch fallback and the `origin/` literals) | header, selector, peek, hooks, menu, mobile, rows, PR button, user config atom | none | L |
| F2 | SCU-1858 | Put per-mode workspace-creation rules in one module | create form, name field, preview hook, sidebar create, create hook | none | M |
| F3 | SCU-1859 | Save repo config through a state-ownership mutation | repos section, repo row, new mutations file | none | S |
| F4 | SCU-1860 | Keep `isGithubOrigin` when refreshing the current branch | `useRepoInfo` | none | XS |
| F5 | SCU-1861 | Send sidebar Commit and Create PR actions to the clicked workspace, not the viewed one | palette git actions, workspace actions | none | S |
| Z1 | SCU-1862 | Survey gate: no workspace-scoped git outside the seam, including swallowed-error sites | git command and error modules (deletions) | P1 to P4 | S |

Waves: T0, T1, S1, P5, P6, F1 to F5 in parallel; then P1 to P4 in parallel,
plus P7 once P5 had landed; then Z1. Feature work was gated on T0, S1 and Z1;
the others landed before the feature PRs that touch their surfaces.

Nice to have, not blocking, and outside this work: reliable worktree teardown
(remove without `--force` fails silently and nothing prunes; the
stale-environment cleanup never runs), drop the pygit2 runtime dependency,
delete git-repo-service dead code, delete unused foundation git helpers,
remove the unread `AgentTaskInputsV2.git_hash`, drop unused `sync_artifacts`
parameters, rename the diff trigger, move app.py's main-repo git helpers onto
the seam and remove unreachable excepts, remove legacy clone mode (decision
17), fix the import direction between interfaces, services and web, record
the real worktree base, one PR status-dot mapping, one mode-label table,
route the remaining non-workspace git and gh calls through the seam, turn the
tasks route into a thin alias of the agents endpoint or retire it (D1a). Two
items first listed here are done: the default-target-branch setting was
deleted (PR #481), and every diff's base commit now comes from the backend
(tickets D2 SCU-1874 and E2 SCU-1882).

#### Validation survey (2026-11-16) and cleanup round two

The gate was run as five independent read-only surveys of main at `c62b1ce5`.

- Ticket acceptance: 27 of 29 backend criteria and 12 of 13 frontend criteria
  are met; none is unmet. The partial ones are covered by round two.
- Exit criterion 1, no workspace-scoped git outside the seam: **not met**.
  The default setup command is a raw `git fetch origin 2>/dev/null || true`
  shell string run in the checkout, and checkout creation still bypasses the
  seam (`create_checkout`, `verify_checkout`, `validate_new_ref_name` and
  `default_setup_command` have no production caller).
- Exit criterion 2, no swallowed git failures on workspace paths: **not
  met**. Of 33 handlers that degrade on a git failure, the ones that matter
  for jj are the turn diff tracker, which catches every exception and reports
  no changes, and the PR poller, where one misdispatched workspace aborts the
  whole batched round. Eleven branches on the workspace kind are not
  exhaustive; the worst gives an unknown kind the user's own repository as
  the agent's working directory.
- One regression, unrelated to jj, was found and fixed separately
  (SCU-1868, PR #515): moving discard behind the seam made it run `git
  checkout --end-of-options HEAD -- <path>`, which git before 2.43.1 rejects.
  The fix restores `git checkout HEAD -- <path>`; the seam's other commands
  pass on git 2.34.1, 2.39.5 and 2.43.0.

Round two, filed under SCU-1847, all merged:

| ID | Ticket | Title | PR |
|---|---|---|---|
| R1 | SCU-1869 | Create and verify checkouts through the VCS seam; a stable checkout name; setup default and name validation through the seam | #513 |
| R2 | SCU-1870 | One VCS selection point, exhaustive kind branches, a tripwire no handler swallows | #516 |
| R3 | SCU-1871 | Make the stream the only writer of project and dependency state | #512 |
| R4 | SCU-1872 | One builder and one route for Commit and Create PR prompts | #517 |

Z1 (SCU-1862) was re-run on round two, below.

#### Validation survey, round two (2026-11-16)

Z1 was re-run as three independent read-only surveys of one tree that
combined R1 to R4 and D1 before they merged (`just check` and the seam's
tests passed on it). Each surveyor was asked for evidence per criterion and
for a strict answer to one question: would a workspace of a new kind, added
as one enum member plus the edits the type checker demands, run git in its
checkout or get a silently wrong result?

| Survey | Verdict | Blocks jj work |
|---|---|---|
| Exit criterion 1, no workspace-scoped git outside the seam | Partial | Nothing |
| Exit criterion 2, no swallowed git failures on workspace paths | Partial | Nothing |
| Frontend (R3, R4, and the first survey's thirteen hazards) | Partial | Nothing |

What holds:

- Every way to reach git in a checkout passes one of four gates: the
  selection function, the turn-diff-tracker factory, one of fifteen
  exhaustive `match` sites on the workspace kind, or the runner's tripwire.
  No comparison on the kind is left in production Python, and no parameter
  on the create and resume chain defaults the kind.
- `create_checkout`, `verify_checkout`, `validate_new_ref_name` and
  `default_setup_command` have production callers, and
  `local_environment.py` starts no git.
- The two handlers that decided round one are fixed and tested: the turn
  diff tracker re-raises the tripwire, and PR polling skips one workspace
  and keeps its round going. No handler gives a jj workspace a silent wrong
  result.
- R3 and R4 meet their acceptance criteria.

What is partial, and where it goes:

| Finding | Disposition |
|---|---|
| Clone creation runs twelve raw git commands outside the runner | By design while clone mode exists (decision 17) |
| The default setup command is a shell string run by a generic runner | By design: each VCS supplies its own string |
| The branch poller reads `.git` directly for its stat fast path | By design, under an exhaustive `match` |
| Three more handlers in the Claude tool-result path catch the tripwire | R2 follow-up (SCU-1870) |
| Both pollers log the tripwire below ERROR, so a test does not fail on it | R2 follow-up |
| The tripwire fires for a directory that no longer exists under a jj-only ancestor | R2 follow-up |
| The registration check does not resolve symlinks; `create-initial-commit` and `sculptor <path>` have no check | R2 follow-up |
| PR polling isolates only two exception types per workspace; its once-per-workspace log resets on every row update | D6 (SCU-1880) |
| A deletion while the stream is disconnected leaves the row until reload (new with R3); no store is reconciled against the reconnect snapshot | R7 (SCU-1889), open |
| The Commit button reads its workspace from a desktop-only layout atom | R5 (SCU-1887), fixed in PR #514 |
| Eight frontend hazards from round one were still open | Owned by D3, E1, E2 and E3; the unowned sub-items were added to E2 and E3 |
| Setup re-run ignores the workspace kind; discard accepts a pathspec that names more than one file; a clone's source branch can be read as a git option | R6 (SCU-1888), git hardening, not jj; open |

Facts the surveys established, which later tickets relied on:

- `resolve_base_commit_id` is called with the literal `HEAD` when a git
  request names no source branch. jj must never be handed it: a jj
  workspace's base defaults to its target (ticket D4, SCU-1878).
- The seam's agent environment then had one consumer, PR polling. Agents and
  terminals were launched without it (ticket D5, SCU-1879, changed that).
- Two removal paths delete a checkout directory without calling
  `remove_checkout` (environment destroy and stale-environment cleanup), so
  a jj workspace can outlive its directory in the repository; the startup
  orphan sweep covers it (ticket D4).
- jj failures are all in the `VcsCommandError` family, including a stale
  working copy, and several callers degrade quietly on that family (ticket
  D6, SCU-1880).
- Every open window polled the health endpoint every three seconds, and each
  poll recomputed the dependency status with one subprocess per tool, two of
  them jj (fixed by X1, SCU-1890).

The gate's purpose was met and feature work proceeded.

Re-check (2026-11-16). The R2 follow-up closed its five items in six commits,
and a fresh read-only surveyor confirmed all five on that branch's tip: the
three handlers on the Claude tool-result path re-raise the tripwire and none
of the other 121 broad handlers hides it; both pollers log it at ERROR, which
fails a test; it no longer fires for a directory that does not exist; the
registration check resolves symlinks; and `create-initial-commit` and
`sculptor <path>` refuse a jj workspace through one shared function. Two
small left-overs moved into feature tickets, and both are fixed: the branch
poller's log-once set was shared by its tripwire and ordinary-failure arms
(ticket D6), and the agent task handlers logged a tripwire at medium
priority, below what the test suite's ERROR guard sees (ticket D4). One
consequence became its own ticket, J1 (SCU-1891): `just backend` passes `.`
as the project, so the dev backend refused to start from a jj-only checkout
of this repository; a path inside a jj workspace should resolve to its
colocated main repository, as a git worktree resolves to its main
repository. Z1 closed once R1 and R2 merged (PRs #513 and #516).

### D14. Feature tickets and stack

Filed under SCU-1865, and all merged (pull requests in D15). Each ticket is
one reviewable increment, built on the tickets it depends on, and every
increment was inert until a repository opted in and jj workspaces became
creatable (ticket D4).

| ID | Ticket | Title | Depends on |
|---|---|---|---|
| D1 | SCU-1873 | jj command runner and repository queries (new files in the seam) | none |
| D2 | SCU-1874 | `JjWorkspaceVcs`, `JjTurnDiffTracker`, seam types widened | R1, R2, D1 |
| D3 | SCU-1875 | The jj workspace kind and its wire contract; not yet creatable. Also the jj runner on `VcsRunners`, the pure "creates jj workspaces" predicate with the one helper that gathers its facts, and the router module `web/workspace_jj_routes.py` | D2, R3, R4 |
| C1 | SCU-1876 | Colocation detection, pre-flight and init; repository jj state; the bookmark list for the create dialog; all in `web/project_jj_routes.py` | D3 |
| C2 | SCU-1877 | Repository jj controls in Settings | C1, R3 |
| D4 | SCU-1878 | Creatable jj workspaces: create, resume, delete, orphans, data routes, `sculpt --strategy jj` | D3 |
| D5 | SCU-1879 | jj environment and mode prompt for agents and terminals | D3 |
| D6 | SCU-1880 | jj workspace poller; pull requests keyed on bookmarks; stale working copies (mark, publish, recover on request) | D3 |
| E1 | SCU-1881 | jj identity and target on every workspace surface | D3 |
| E2 | SCU-1882 | Revisions, working-copy changes and diffs | D4, D6 |
| E3 | SCU-1883 | Creating jj workspaces from the UI; jj prompt wording | D4, C1, R4 |
| F1 | SCU-1884 | Skill pre-activation and bookmark upkeep | D5, D6 |
| J1 | SCU-1891 | Register the main repository when given a path inside its jj workspace | D3 |
| D7 | SCU-1892 | Keep an older jj on the user's PATH from shadowing Sculptor's jj | D5, X1 |
| D8 | SCU-1895 | jj readiness requires a git that jj accepts | D7 |
| G2 | SCU-1893 | Help docs and the product spec for jj mode | all |
| G3 | SCU-1894 | An old-git CI job; dev tooling from a jj workspace | D5 |
| G4 | SCU-1896 | Polish from the exploratory pass | all |
| X1 | SCU-1890 | Serve dependency status and jj readiness from a cache | D5 |
| G1 | SCU-1885 | End-to-end browser tests and an exploratory pass in the running app | all |

Waves: R1 to R4 and D1 in parallel; then D2; then D3; then C1, D4, D5, D6,
E1 and J1 in parallel; then C2, E2, E3, F1 and X1; then D7; then G1.

How the stack was built. Tickets were built in parallel. A ticket whose
dependencies had not merged was built on a local base that combined them,
and when a branch below changed, the base was rebuilt and the branches above
were rebased onto it. Each ticket was then rebased onto main and merged in
dependency order, on 2026-11-18 and 2026-11-19. Two tickets started before
their last dependency finished, to shorten the critical path: D2 began on R1
and D1 while R2 was finishing, with its edits to existing callers ordered
last; D3 ran in two parts, the wire contract first (no dependency on D2) and
the workspace kind with its arms after D2. Sibling tickets in a wave were
given disjoint files and fixed insertion points in the few shared ones
(routes go in new router modules, not `web/app.py`), so their branches
combined without conflicts. Stale-working-copy handling moved from D4 to D6,
which publishes the state, and the bookmark list moved from D4 to C1, which
owns the repository routes.

### D15. As built, and where it differs from the design above

Every ticket is merged into main. Each was rebased onto main and merged in
dependency order on 2026-11-18 and 2026-11-19 (D14).

| Ticket | PR | What it delivered |
|---|---|---|
| D1 SCU-1873 | #518 | jj runner, revset builders, repository queries |
| D2 SCU-1874 | #520 | `JjWorkspaceVcs`, `JjTurnDiffTracker`, the pure stack projection, seam types widened |
| D3 SCU-1875 | #522 | `JJ_WORKSPACE` kind with an arm at every exhaustive `match`, wire types, stream keys, the "creates jj workspaces" helper |
| D4 SCU-1878 | #524 | create, resume, delete, startup orphan sweep, readiness gate, `sculpt --strategy jj` |
| D5 SCU-1879 | #531 | `jj-bin` on PATH, `GH_REPO`, git ceiling, `JJ_EDITOR=false` for chat agents, the full mode prompt |
| D6 SCU-1880 | #527 | jj poller, workspace jj state on the stream, PR lookup on bookmarks, stale working copies |
| C1 SCU-1876 | #525 | repository jj state service, pre-flight, colocation, bookmark list; the setup-command defaults, served from `web/workspace_setup_command_routes.py` |
| C2 SCU-1877 | #523 | the two repository switches, confirmation dialog, badge, Re-check |
| E1 SCU-1881 | #528 | bookmark pill, identity labels, target selector, extension view |
| J1 SCU-1891 | #526 | a path inside a jj workspace registers its colocated main repository |
| E2 SCU-1882 | #530 | Revisions panel, "Working copy" scope, diff bases from the backend, stale banner, banner for files jj left out, the working copy's commit id in the header hover card |
| E3 SCU-1883 | #534 | create dialog and sidebar quick-create for jj, jj wording of the Commit and Create PR messages, the jj prompt settings, the agent panel's jj-unavailable block |
| F1 SCU-1884 | #535 | first-message skill reminder (Claude), `/skill:jujutsu` prefix (pi), the requested bookmark created after a turn, once-per-state reminders, the CI babysitter's jj wording |
| X1 SCU-1890 | #533 | the dependency service keeps the last computed status; the health route starts no process; gates probe jj afresh |
| D7 SCU-1892 | #536 | terminal agents run Sculptor's jj; readiness reports the jj the user's login shell runs |
| D8 SCU-1895 | #537 | readiness requires a git that jj accepts (2.42.0 for the pinned jj) |
| G1 SCU-1885 | #539 | ten browser tests for the remaining journeys, making 22 jj browser tests in all; an exploratory pass with a real agent |
| G2 SCU-1893 | #521 | `docs/help/jujutsu.md`, product spec section 7.14, requirements and scenarios |
| G3 SCU-1894 | #532 | a CI job on the oldest supported git; `just check` and the test server work from a jj workspace |
| G4 SCU-1896 | #538 | small wording and layout findings from the exploratory pass: the delete dialog says what happens to bookmarks, the bookmark field is labelled, an activated panel tab scrolls into view |

Where the code differs from sections D1 to D12, and why:

- **The `jj-bin` link is maintained at one gate, not at each launch site
  (D6).** Every launch for a jj workspace (chat agent, terminal agent,
  workspace terminal, setup command, setup re-run) passes
  `prepare_jj_for_launch`, which checks readiness and then links the jj it
  accepted. `agent_environment` only describes the environment: it probes
  nothing and writes nothing. An earlier form linked inside
  `agent_environment`, which PR polling calls on every poll, so one slow
  readiness probe in a poller could remove the link under running agents.
  Nothing removes the link now; it is only replaced.
- **A login profile can reorder PATH after Sculptor sets it (D6).** macOS
  `path_helper` moves `/etc/paths.d` entries (Homebrew) to the front, and a
  cargo profile prepends `~/.cargo/bin`. A newer jj winning is harmless; one
  below the pin is not, because it cannot read the repository. The setup
  command and terminal agents re-apply the VCS PATH prefixes after the
  profile has run; what every launch form runs is listed below.
- **Readiness is checked before every jj launch and on the write routes
  (D3, D7).** Environment create and resume, setup re-run and update-stale
  all call `require_jj_available` and answer with one shared sentence
  (`services/jj_availability.py`); the creation validator and the repository
  routes use the same sentence for their 412. `JjUnavailableError` carries
  only that sentence, not the readiness variant; the agent panel recognizes
  it by its type and links to the Jujutsu page. Each check runs jj afresh;
  displays read a cached value instead (below).
- **The repository jj routes answer every refusal one way (D1).**
  `web/project_jj_routes.py` maps each refusal of the repository jj service
  through `_refusals_as_http_errors()`: 412 when jj is unavailable, and 409
  when the repository is not colocated, the pre-flight finds a blocker, a
  colocation is already running, or jj cannot read the repository, which
  answers "Cannot read the repository: <error>". So turning the switch on
  can also answer 412, and colocating can answer 409 for a blocker.
- **The poller's revset is per workspace, not `& mutable()` (D4).** It
  reads `(::W ~ ::T) | W` for each workspace, flagging each revision with the
  targets it reaches; this is the same stack `read_identity` uses
  (`vcs/jj_workspace_scan.py`). In a repository with no remote everything is
  mutable, and the design's revset would read the whole history after every
  operation. Only a workspace whose target names no commit falls back to its
  mutable ancestors.
- **PR lookup takes its base from the seam (D5).** `PullRequestRefs` gained
  `base_ref_name`, so `main@origin` maps to `main` in one place, and the
  GraphQL query names the owner and repository instead of leaving `gh` to
  find them.
- **Orphan sweep rule (D3).** A jj workspace is forgotten only when its name
  is a Sculptor workspace id, no live workspace in this database owns it,
  and its directory is gone. The design's "missing on disk or soft-deleted"
  could forget a workspace whose directory still exists.
- **A jj workspace's base is never the git name `HEAD`, and the workspace
  service checks it, not the validator (D3).** With no source it starts from
  its target. `create_workspace` raises `WorkspaceBaseNotFoundError`, answered
  with 400, for a base that is not a bookmark symbol or a full commit id,
  such as git's `origin/main`. The validator runs first and does not check
  the base, so a request with both a bad base and a bad bookmark name gets
  the name's error.
- **Colocating changes what `git status` shows (D3, D9).** Contents, branch
  and HEAD are untouched, but untracked files then show as added, because jj
  records them and git reads that as intent-to-add. The confirmation dialog
  says so. A `.jj` left by an interrupted init blocks the next attempt until
  the user removes it; Sculptor never deletes one.
- **The streamed jj states carry less than D1 lists (D1).**
  `WorkspaceJjStateInfo` has no `requested_bookmark`: the requested name is
  already on the workspace row. `ProjectJjState` has no pre-flight, which
  `GET /projects/{id}/jj` returns, and carries the derived
  `creates_jj_workspaces` instead of `use_jj_for_new_workspaces`, which the
  frontend reads from the project row.
- **The header hover card reads its commit id from the revisions (D10).**
  The streamed state carries no commit id, so that a snapshot alone re-emits
  nothing; the card fetches the revisions when it opens and shows the
  working copy's commit id.
- **Both VCSs name the uncommitted diff's base (D1, D10).** git sets
  `uncommitted_diff_base` to HEAD's commit id rather than leaving it empty,
  and the frontend reads every diff's before-image at the commit the
  artifact names, with no `HEAD` fallback. An empty base, as for a working
  copy with two parents, shows the diff without a before-image.
- **JJ_AVAILABLE is derived and never persisted; displays read a cached
  value (D7).** The dependency service keeps the last computed status in
  memory and recomputes it on installs, settings changes, an explicit
  re-check and a 60-second timer. The health route, polled every three
  seconds by every window, reads it and starts no process. Anything that lets
  jj act on a repository (every launch in a jj workspace, update-stale,
  colocation, turning the switch on, listing bookmarks, creating a workspace,
  resolving `sculptor <path>`) calls `probe_jj_readiness()`, which always
  runs jj, so a stale "available" cannot let a write through.
- **Decision 20 is not built yet (2026-11-23).** As built:
  - A Managed jj with no download falls back to a `jj` on PATH.
  - jj-bin is on PATH only in jj workspaces.
  - A workspace terminal the user opens runs whatever the profile puts first,
    and an out-of-range jj there is the `SHADOWED` blocker described below.

  Each is to be brought in line with decision 20.
- **Readiness has seven outcomes, not five (D7).** Beyond not installed, not
  runnable, unsupported version and no identity: `SHADOWED`, when the jj the
  user's login shell runs is out of range, because the repository is shared
  with it and a jj that old cannot read what Sculptor's writes; and
  `UNSUPPORTED_GIT`, when the git jj would run for fetch and push is older
  than jj accepts. `SHADOWED` is reported only when every other check
  passes. The login-shell probe runs the user's whole profile, so it runs at
  the first status, on a re-check and when Sculptor's jj moves, never on the
  timer; the shell writes its PATH to a file, because a profile can print to
  stdout. An in-range jj in the login shell is recorded and shown on the
  Jujutsu page, and blocks nothing. The git check uses the PATH agents get;
  the setup command and workspace terminals run the login profile, which can
  put another git first.
- **Which jj each launch form runs (D6), observed, not assumed.** Claude and
  pi chat agents run Sculptor's jj whatever the login profile does (Claude's
  shell snapshot restores its own PATH; pi runs `bash -c` with no startup
  file). The setup command and terminal agents re-apply the VCS PATH prefixes
  after the profile has run. A workspace terminal the user opens runs
  whatever the profile puts first; that is what `SHADOWED` reports. Extra
  terminal tabs opened after an agent has started pass no gate: they reuse the
  `jj-bin` link made at that start.
- **The poller rests only when jj cannot read (D4).** One rule in
  `services/jj_availability.py`, `can_jj_read`, says whether Sculptor's jj
  can still read a repository; a missing identity, a shadowed jj and an old
  git do not stop reading, so workspace state keeps refreshing under those.
  The poller runs no readiness check itself: it reads the readiness the
  dependency service last published.
- **Revisions are served while the working copy is stale (D3).** The history
  read falls back to the revisions as last recorded, without snapshotting, so
  the panel still lists them under the banner.
- **Files jj refuses to snapshot get their own banner (decision 9).** They
  are in no diff, so the Changes panel lists them separately, from the diff
  artifact's `file_errors`, with a link to the size limit's setting. Before,
  a file over the limit was silently absent from the panel.
- **The Commit and Create PR inputs are gathered in the action atoms (D10).**
  Every entry point (Changes panel, header, palette, sidebar menus, mobile)
  sends the same message and is enabled by the same rule.
- **The bookmark text is its own first-message reminder (D6).** It is not
  hung on the auto-rename reminder, which is off by default; an agent that
  never learned the requested name could create its own bookmark and stop
  Sculptor from creating the requested one. The turn-end bookmark attempt
  cannot fail an agent's run.
- **Sculptor run from source inside a jj workspace (not in the design).**
  Its own repository root is found by a `.git` or a `.jj` directory, so it
  keeps its own `.dev_sculptor`; a path inside a jj workspace given to
  `sculptor <path>` or to Add Repository registers the colocated main
  repository; `init-git` and `create-initial-commit` still refuse there.
- **The jj code is split by concern, not into D2's two jj modules (D2).**
  In `services/workspace_service/vcs/`: `jj_cli.py` (the runner),
  `jj_revsets.py` (revset and fileset builders), `jj_repo_queries.py`
  (repository reads and writes), `jj_data_types.py`, `jj_workspace_vcs.py`,
  `jj_workspace_scan.py` (the poller's two-command read),
  `jj_stack_projection.py` (the pure stack projection),
  `jj_turn_diff_tracker.py`, `workspace_vcs_selection.py` (the one selection
  point) and `vcs_runners.py`. There is no `JjCommandFailure`: jj failures are
  the seam's `VcsCommandError` family, with `JjWorkingCopyStaleError` in
  `vcs/errors.py`. `JjUnavailableError` lives in `services/jj_availability.py`.
- **The pin lives in one import-free module (D7, D12).**
  `services/jj_version.py` holds `JJ_PINNED_VERSION` (0.47.1), the sha256 per
  target triple and `JJ_MINIMUM_GIT_VERSION`. `JJ_PIN` in
  `services/managed_tools.py` is assembled from it, and `just install-jj`
  reads it. `.devcontainer/Dockerfile` keeps its own copy, which
  `jj_version_test.py` holds equal.
- **Tests opt in to Sculptor finding jj (D12).** The test user config
  leaves jj unresolvable, so JJ_AVAILABLE is off by default. A unit test
  that needs Sculptor to find jj uses the shared fixture
  `jj_resolved_to_the_pinned_binary` (`sculptor/sculptor/conftest.py`),
  which points `dependency_paths.jj` at the pinned binary and builds on
  `jj_isolated_env`, so jj's config and identity are the test's own. A
  browser test points its own Sculptor instance at the pinned binary
  (`use_jj_binary` in `testing/jj_sculptor_instance.py`).

## Verified jj 0.47.1 behaviour

Probed on 2026-11-16 with the pinned jj 0.47.1 against colocated main repos
with a bare remote, in an isolated configuration. Everything recorded for 0.46
still holds except where a bullet says otherwise.

Workspaces and reads:

- `jj workspace add --no-colocate --name <name> -r <revset> --sparse-patterns
  full <dir>` creates a directory holding `.jj` and the files, with no `.git`.
  Git inside it fails with "not a git repository". The new working-copy change
  is a child of the requested revision. `<dir>/.jj/repo` is a file holding a
  relative path to the main store. `--name` is required in practice (the
  default is the directory basename), the parent directory must exist, and the
  command refuses `--ignore-working-copy`. It snapshots the user's main working
  copy, which is normal jj behaviour; the user's git branch stays checked out.
- `remote_bookmarks(exact:"main", exact:"origin")` is the base and target
  revset. Git-style `origin/main` does not resolve.
- Reads with `--ignore-working-copy` add no operation and do not see
  unsnapshotted files. A plain command snapshots; a snapshot that finds no
  change writes no operation. The file names under
  `<store>/op_heads/heads` change on every new operation.
- `json()` templates serialize what the poller and the revision list need:
  `json(self)` gives `change_id`, `commit_id`, `parents`, `description`,
  `author` and `committer` (timestamps carry a numeric offset such as
  `+13:00`); `working_copies.map(|w| w.name())`, `local_bookmarks`,
  `remote_bookmarks`, `empty`, `conflict`, `divergent`,
  `change_id.shortest(8)`, `self.diff().files()` (path, status) and
  `self.diff().stat().files()` (lines added and removed) all work.
- `jj file list -T 'json(path)'`, `jj file show -r <commit> 'root-file:"<path>"'`
  and `jj restore 'root-file:"<path>"'` work with spaces and parentheses in
  paths. Restore reverts modified files and deletes added ones.
- New files over 1 MiB are refused with a warning and exit 0, and stay
  untracked. `jj --ignore-working-copy config set --workspace
  snapshot.max-new-file-size <n>` creates no operation, applies only to that
  workspace, and stores the value under the user's jj config directory in
  `jj/workspaces/<id>/config.toml`; the id is written to
  `<dir>/.jj/workspace-config-id`. `jj workspace forget` leaves that directory
  behind.

Bookmarks, push and fetch (changed in 0.47):

- A new bookmark pushes with no extra flag. Push refuses a commit with no
  description and a commit with no author or committer.
- **A push or fetch inside a jj workspace no longer updates Git refs in the
  user's checkout.** jj's own view updates at once: the workspace sees
  `feat@origin` after a push and the new `main@origin` after a fetch. The
  user's `.git` gains `refs/heads/<bookmark>` and `refs/remotes/origin/*` only
  when a jj command next runs in their colocated checkout (any command without
  `--ignore-working-copy`), or when `jj git export` is run in the workspace.
  Sculptor reads jj, never git refs, in jj mode, so nothing in Sculptor
  depends on the export; Sculptor does not run it.
- With `main@origin` untracked, which is how `jj git init --colocate` leaves
  an existing repository, a fetch in a workspace moves only `main@origin`. The
  user's local `main` and their checked-out git branch stay put, and `trunk()`
  follows `main@origin`. With `main` tracked, the same fetch fast-forwards the
  local `main` bookmark, and the next jj command in the user's checkout
  exports it and leaves their git HEAD detached at the old commit. Colocation
  init therefore does not track any bookmark.
- `jj bookmark list --all-remotes -T 'json(self)'` prints one object per
  line: `{name, target: [...]}` for local bookmarks and `{name, remote,
  target, tracking_target?}` for remote ones, including a synthetic `git`
  remote that must be dropped. A conflicted bookmark has more than one target
  and, from 0.47, `null` entries for absent sides.
- `jj bookmark advance <name> --to <rev>` moves a bookmark forward.
  `jj bookmark forget --include-remotes <name>` drops the local bookmark and
  its remote-tracking entries, leaves the remote branch in place, schedules no
  remote deletion, and keeps the commits visible.

Workspace lifecycle:

- `jj workspace list -T 'name ++ "\t" ++ root ++ "\n"'` lists every workspace
  with its absolute root, including roots deleted from disk.
- `jj --ignore-working-copy workspace forget <name>`, run from the main
  repository, abandons an empty undescribed working-copy change and keeps a
  described one. Edits that were never snapshotted are lost with the
  directory. An unknown name prints "Nothing changed." and exits 0, and the
  command works when the directory is already gone.
- `jj op restore` in the main repository makes a workspace stale. A
  snapshotting command then fails with "The working copy is stale"; reads with
  `--ignore-working-copy` keep working. `jj workspace update-stale` recovers,
  and it deleted a file from disk whose addition existed only in the undone
  operations, which is why recovery stays a manual action.
- `present("<workspace>"@)` tolerates a missing workspace in a revset, the
  trunk commit behind `main@origin` is immutable, and `JJ_EDITOR=false` makes
  an editor-invoking command fail at once.

## Process

1. Commit the rough draft. (Done.)
2. Research and produce the detailed design. (Done.)
3. Work through the decisions needed; commit the aligned design. (Done.)
4. Pre-cleaning: file the preparatory cleanup as Linear tickets (D13), run
   them in parallel, merge to main; then rebase and validate by survey,
   repeating until clean. (Done. Round one merged by 2026-11-13. The survey
   of 2026-11-16 found gaps, which round two closed: R1 to R5 merged, and
   the re-run survey found nothing that blocked the feature work.)
5. Feature development, with subagents, in gated increments tracked under
   SCU-1865. (Done. A (SCU-1866) and B (SCU-1867) merged first; the rest is
   the ticket stack in D14, merged on 2026-11-18 and 2026-11-19. Before
   merging, each ticket had a simplification pass and a comment-trimming
   pass.)

## Open questions

- Should the repository-level jj controls appear on surfaces other than the
  repository configuration screen? Decided: no. The two switches are only on
  the Repositories page; other surfaces show read-only indicators (D9).
- Should the tasks route become a thin alias of the agents endpoint, or be
  retired? Open, until the public-API posture is confirmed (D1a).
- Should pull request status cover bookmarks other than the primary one? v1
  shows the primary bookmark's only (decision 11).
- Four cleanup follow-ups from round two are filed and open: SCU-1888 (R6:
  harden setup re-run, discard and a clone's source branch; git, not jj),
  SCU-1889 (R7: reconcile project and workspace stores with the stream's
  reconnect snapshot), SCU-1897 (R8: one method that resolves a workspace's
  setup command) and SCU-1898 (R9: one type for a workspace's checkout name,
  with its kind passed once). Smaller nice-to-haves are listed after the
  table in D13.
