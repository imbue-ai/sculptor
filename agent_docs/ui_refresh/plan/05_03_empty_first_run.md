# Task 5.3: Empty first-run page + disabled-navigation state

## Goal

Build the no-workspaces first-run experience: a special page rendering the
new-workspace form inline, the sidebar's repo-area states, and the disabled-
navigation behavior until the first workspace exists.

## Stories addressed

FIRST-01 (no workspaces → sidebar open + a special page rendering the new-workspace
form), FIRST-02 (sidebar repo area: "Add a repo" if no repos; "No workspaces yet"
beneath a repo with none), FIRST-03 (navigation otherwise disabled — only the form
and Settings reachable; Cmd+K and global shortcuts disabled), FIRST-04 (first-
workspace prompt defaults to the existing `/sculptor:help` prefill), FIRST-05 (after
creating the first workspace, show the full workspace page + navigate to it in the
default state).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`. Per
`goals.md` → "Empty workspace state": with no workspaces, default to the sidebar open
with a special page rendering the new-workspace form; the sidebar still renders its
repo area; navigation is otherwise disabled (only the form + Settings; Cmd+K and
global shortcuts off) to keep it simple; the first prompt defaults to
`/sculptor:help`; once created, show the full workspace page and navigate there.

**What to copy** (`design_extraction.md` → "Inline first-run"):
`pages/home/RecentWorkspaces.(tsx|module.scss)` `.inlineForm` (card-wrapped form on
empty home) + `components/NewWorkspaceModal/homePromptPrefill.ts` (the
`/sculptor:help` prefill). The inline form reuses the `NewWorkspaceForm` from Task
5.1.

**Reuse the existing onboarding-landing behavior:** today, post-onboarding/
post-signup lands on the add-workspace page (`test_onboarding`/`test_telemetry_opt_out`/
`test_migration`/`test_restart_mru` assert "lands on `/ws/new`"). Those landings now
go to this first-run page (FIRST-01).

This task depends on **Task 5.1** (`NewWorkspaceForm`), **Task 2.2** (sidebar repo
area), and **Task 4.5** (the disabled-shortcuts flag the shortcuts hook respects).

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/EmptyFirstRunPage.tsx` (+ styles) — new: the
  no-workspaces special page rendering `NewWorkspaceForm` inline (card-wrapped).
- `sculptor/frontend/src/components/NewWorkspaceModal/homePromptPrefill.ts` — copy the
  `/sculptor:help` prefill if not present.
- `sculptor/frontend/src/components/nav/WorkspaceSidebar.tsx` — modify: render the
  repo-area states ("Add a repo" / "No workspaces yet") when empty (FIRST-02), and the
  disabled-nav state (FIRST-03).
- Routing (`App.tsx`/`Router.tsx`): when there are no workspaces, render
  `EmptyFirstRunPage` (sidebar open) and disable other destinations except Settings.
- `sculptor/sculptor/constants.py` — `EMPTY_FIRST_RUN_PAGE`, `SIDEBAR_ADD_REPO_BUTTON`,
  `SIDEBAR_NO_WORKSPACES_HINT`; `just generate-api`.

## Implementation details

1. Detect the no-workspaces state (reuse the existing workspace-list data atoms) and
   render `EmptyFirstRunPage` with the sidebar open.
2. The page renders `NewWorkspaceForm` inline (card-wrapped, from Task 5.1) with the
   prompt defaulting to `/sculptor:help` (FIRST-04).
3. Sidebar repo area (FIRST-02): "Add a repo" button when no repos; "No workspaces
   yet" beneath a repo with none.
4. Disabled nav (FIRST-03): only the form + Settings are reachable; disable Cmd+K and
   global shortcuts in this state (set the flag the Task 4.5 shortcuts hook respects).
5. On first create (FIRST-05): show the full workspace page (with sidebar) and
   navigate to the new workspace in the **default state** (the SEC-01..04 default from
   Task 6.1).

## Testing suggestions

- FIRST-01..05 e2e land in **Task 5.4** (`test_empty_first_run.py`) via the
  `empty_first_run.py` POM, replacing the no-MRU/no-ws "lands on `/ws/new`"
  assertions from `test_restart_mru.py` + the post-onboarding landing assertions.
  Needs a **fresh zero-workspace instance** fixture (confirm `resources.py` doesn't
  auto-create a first workspace; add a zero-workspace variant if it does).

## Gotchas

- Sidebar stays **open** in the empty state (FIRST-01).
- Only the form + Settings are reachable; Cmd+K + shortcuts **off** (FIRST-03) — set
  the flag the shortcuts hook (Task 4.5) reads.
- The first prompt is the `/sculptor:help` prefill (FIRST-04) — reuse the existing
  prefill, don't invent text.
- Post-create lands in the **default** workspace state (Task 6.1).

## Verification checklist

- [ ] No-workspaces → `EmptyFirstRunPage` with sidebar open + inline new-workspace
  form (prompt = `/sculptor:help`).
- [ ] Sidebar repo area shows "Add a repo" / "No workspaces yet" states.
- [ ] Navigation disabled except form + Settings; Cmd+K + shortcuts off.
- [ ] First create → full workspace page + navigate to default state.
- [ ] `EMPTY_FIRST_RUN_PAGE`/`SIDEBAR_ADD_REPO_BUTTON`/`SIDEBAR_NO_WORKSPACES_HINT`
  added + `just generate-api`; `just check` passes.
