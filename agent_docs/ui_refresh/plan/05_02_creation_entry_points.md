# Task 5.2: Workspace-creation entry points + modes + source-branch + MRU

## Goal

Wire the four workspace-creation entry points and the dialog's creation-mode,
source-branch, and project/repo behavior on top of the modal from Task 5.1.

## Stories addressed

WSC-01 (sidebar new-workspace button → direct create reusing last settings + auto
branch; falls back to the dialog if auto-gen is off/unavailable), WSC-02 (Cmd/Meta+T
→ dialog — handler in Task 4.5; this confirms the dialog opens), WSC-03 (Cmd+K →
dialog), WSC-04 (repo `+` → dialog pre-selecting that repo with the default title),
WSC-08 (branch-name collision = inline error, no stale workspace state), WSC-09
(creation-mode/init-strategy: worktree default, clone/in-place opt-in, mode-appropriate
branch behavior), WSC-10 (create from a non-default source branch), WSC-11 (project/
repo selector registers a new repo + remembers MRU project).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`. Per
`goals.md` → "Workspace creation", there are four entry points: the sidebar
new-workspace button (**direct create**, reusing repo/source-branch/agent-type/init-
strategy + a new auto-generated branch name), the new-workspace shortcut (Cmd/Meta+T),
Cmd+K, and a repo section's `+`. All but the first open the dialog; the repo `+`
pre-selects that repo with the default title.

**Reuse the existing creation backend** (`workspace_creation.md`): today's
`/ws/new` page already drives modes (worktree/clone/in-place, the latter two
flag-gated by `enable_clone_workspaces`/`enable_in_place_workspaces`), source-branch
selection, branch-collision handling, and the project selector + MRU. The dialog
**reuses all of that** — this task connects the entry points to the dialog/direct-
create and ensures mode/source-branch/MRU/collision behavior is preserved against the
dialog surface.

**Last-used settings** for direct create (WSC-01): the MRU agent type + MRU project +
last init strategy already exist (`test_add_workspace_agent_type` / `test_multi_repo`
/ `test_restart_mru` exercised them). Reuse the MRU machinery; direct create
auto-generates a unique branch (so WSC-08 collisions are only possible when the user
types a branch in the dialog).

This task depends on **Task 5.1** (the modal), **Task 2.2** (the sidebar button + repo
`+`), and **Task 4.5** (the Cmd/Meta+T handler). The empty-first-run inline form is
**Task 5.3**.

## Files to modify/create

- `sculptor/frontend/src/components/NewWorkspaceModal/` — wire openers
  (`open_via_sidebar_button`, `open_via_shortcut`, `open_via_command_palette`,
  `open_via_repo_plus(repo)` equivalents) and the direct-create path.
- The sidebar new-workspace button (Task 2.2) + repo `+` → call direct-create / open
  the dialog pre-selecting the repo.
- Cmd+K registration → "new workspace" entry opening the dialog.
- Reuse the existing mode selector, source-branch selector, project selector, and
  collision handling from `src/pages/add-workspace/`.

## Implementation details

1. **WSC-01 direct create:** the sidebar button creates a workspace immediately,
   reusing last settings (repo, source branch, agent type, init strategy) and an
   auto-generated unique branch name. If branch auto-generation is off/unavailable,
   **open the dialog instead**.
2. **WSC-03 Cmd+K / WSC-02 Cmd/Meta+T:** open the dialog (the shortcut handler is Task
   4.5; verify it opens the dialog here).
3. **WSC-04 repo `+`:** open the dialog pre-selecting that repo with the default
   workspace title.
4. **WSC-09 modes:** worktree default; clone/in-place opt-in behind the existing
   feature flags; mode-appropriate branch-field behavior (clearing the branch works on
   the base branch; entering one creates a new branch).
5. **WSC-10 source branch:** create from a non-default source branch via the branch
   selector (reuse `select_branch`).
6. **WSC-08 collision:** typing a colliding branch name shows the inline error
   (worktree + clone) and leaves no stale workspace/worktree state.
7. **WSC-11 project selector:** register a new repo (git-init/add-repo dialogs — reuse
   the existing dialogs the harness keeps) and remember the MRU project.

## Testing suggestions

- WSC-01..04/08..11 e2e land in **Task 5.4** (`test_new_workspace_dialog.py` +
  `test_new_workspace_creation_modes.py`), migrating real bodies from
  `test_branch_name_collisions`/`test_clone_mode_branch_name`/`test_worktree_*`/
  `test_branch_switching_integration`/`test_clone_local_only_branch`/`test_multi_repo`.
  Git-state checks carry over unchanged.

## Gotchas

- Direct create reuses **last** settings + auto branch; only the dialog path lets the
  user type a branch (so collisions are a dialog-only concern — WSC-08).
- Clone/in-place stay **flag-gated** (`enable_clone_workspaces`/
  `enable_in_place_workspaces`).
- No bare "Terminal" agent type in the dialog's agent-type picker (Decision B2).
- Reuse the existing create backend + MRU; don't reimplement.
- Guard: Cmd+Enter inside the repo-path autocomplete must **not** also create the
  workspace (FIRST-06 negative case — preserved from `test_add_workspace_page`).

## Verification checklist

- [ ] All four entry points work (sidebar direct-create + fallback, Cmd/Meta+T, Cmd+K,
  repo `+` pre-select).
- [ ] Modes (worktree/clone/in-place, flag-gated), source-branch, collision, and
  project selector + MRU preserved against the dialog.
- [ ] Direct create reuses last settings + auto branch.
- [ ] `just check` passes (e2e in Task 5.4).
