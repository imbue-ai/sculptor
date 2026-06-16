# New Workspace Modal — Inline-on-empty-Home — Review

Scope: this review covers the single commit added this session —
`50e824186a [SCU-1494] Render the new-workspace form inline on an empty Home`
(`git diff HEAD~1..HEAD`). The earlier 7 commits on
`bryden/scu-1494-rewrite-new-workspace-modal` (the modal rewrite itself) are
prior, separately-reviewed work and are out of scope here.

Note on the spec: `agent_docs/new-workspace-modal/spec.md` is the original
SCU-752 spec and is now partly historical (see `agent_docs/CLAUDE.md`). The
SCU-1494 change **intentionally supersedes** the spec's "First-load behavior"
(auto-open the modal on top of HomePage) with "render the form inline on an
empty Home; no auto-open." Requirements below are therefore assessed against
the approved SCU-1494 plan + two follow-up requests, with the superseded spec
section flagged.

## Summary

- The implementation meets the stated goal and the approved plan. It is
  well-tested (a unit test for the prefill decision + an inline-create
  integration test) and green on `just format` / `just check` /
  `just test-unit` and the directly-affected integration suites.
- No CRITICAL or HIGH findings. Two things worth addressing/calling out before
  merge: (1) `useNewWorkspaceModal` subscribes to the whole `workspacesArrayAtom`
  when it only needs emptiness, widening re-renders (MEDIUM, perf); (2) the
  removal of the backend first-agent greeting changes behavior for CLI/API
  agent-creation paths (intentional — call it out in the PR body).
- Nothing blocks the change.

## Requirements Coverage

| Requirement (SCU-1494 plan / follow-ups) | Status | Evidence |
|------------------------------------------|--------|----------|
| Zero workspaces → render the new-workspace form inline, centered, replacing the empty state | Covered | `RecentWorkspaces.tsx:174-184`, `RecentWorkspaces.module.scss:25-51` |
| Drop the search bar in that state | Covered | empty branch returns before the search bar (`RecentWorkspaces.tsx`) |
| Delete the `EmptyState` component | Covered | `EmptyState.tsx` / `.module.scss` deleted |
| `"home"` entry source hides close-X and "Keep open" toggle | Covered | `NewWorkspaceForm.tsx:592-608, 770-783`; union update `atoms.ts:14` |
| Editable, optional, one-shot, integration-gated prefill | Covered | `homePromptPrefill.ts` (`shouldPrefillHomePrompt`), effect at `NewWorkspaceForm.tsx:143-151` |
| Prefill uses the fuller `/sculptor:help …` sentence | Covered | `homePromptPrefill.ts:11-12` |
| Remove backend first-agent auto-injection (all paths) | Covered | `app.py:1695-1733` removed; obsolete tests deleted in `app_basic_test.py` |
| Off-Home / has-workspaces → modal opens normally | Covered | `hooks.ts:40-58` (`isHomeRoute && empty` gate only) |
| Hide topbar "+" only on empty Home | Covered | `WorkspaceTabs.tsx:61-66, 472-495` |
| Entry points at zero workspaces focus the inline prompt | Covered | `homePromptFocusRequestAtom` (`atoms.ts:70`), focus effect `NewWorkspaceForm.tsx:126-134` |
| Remove `firstLoad` auto-open; simplify Router fallback | Covered | `HomePage.tsx` effect removed; `Router.tsx:53-54` → `/home` |
| Fix red "required" flash during initial auto-fill | Covered | `NewWorkspaceForm.tsx:546-553` (`isAwaitingAutoFillBranch`) |
| (Superseded) spec "auto-open modal on first load" | Superseded | intentional — replaced by the inline form |

## User Scenarios

- **First-time user lands with no workspaces.** Delivered and superseding the
  spec: instead of an auto-opened modal, the empty Home renders the form inline
  with the help prefill. Covered by `test_inline_new_workspace_form_shown_and_creates_for_new_user`
  and `test_restart_with_no_mru_lands_on_home`.
- **Power user creates from anywhere (off Home / with workspaces).** The modal
  still opens via topbar "+", palette, and keybinding. Covered by
  `test_cmd_t_opens_new_workspace_modal`, `test_workspace_form_draft_persists_after_navigation`,
  multi-repo, and tab-enhancement suites.
- **Create without a prompt.** In integration mode the prefill is gated off, so
  submit yields a waiting agent — `test_create_workspace_without_prompt` stays
  green.
- **Send an initial prompt with creation.** An untouched prefill is sent as the
  first message on create (reproducing the old greeting via a visible, editable
  field). Not asserted in integration (gated off by design); the decision logic
  is unit-tested.

## Test Coverage

- Tests added: `homePromptPrefill.test.ts` (6 cases for `shouldPrefillHomePrompt`);
  `test_inline_new_workspace_form_shown_and_creates_for_new_user`
  (inline render + create); a HOME_NEW_WORKSPACE_FORM assertion added to
  `test_restart_with_no_mru_lands_on_home`.
- Tests updated for the new surface: branch-collision (inline-form getter),
  onboarding/migration (union "create surface" beacon), restart_mru
  (firstLoad removal), plus page-object/helper updates.
- Suite status: `just check` green; `just test-unit` green (all four suites).
  Integration — batch 1 (home, add_workspace, branch_collisions, restart_mru,
  onboarding, migration): 31 passed, 1 pre-existing skip. Batch 2
  (worktree_create, workspace_tab_enhancements, multi_repo): 15 passed, 1
  pre-existing skip. One flake (`test_worktree_create_with_default_branch_name`,
  a `git worktree list` timing race unrelated to this change) passed on re-run.
- Skipped/xfail: only two pre-existing, unrelated skips (onboarding config
  timing; multi_repo duplicate-name redesign). None introduced here.

## Code Review Findings

Code-review skill: `/code-review-checklist` (configured in `.sculptor/docs.md`),
run on `HEAD~1..HEAD`. Verbatim findings:

> **Correctness** — LOW: modal form also subscribes to `homePromptFocusRequestAtom`
> via the shared focus effect (safe by invariant, documented). LOW: a
> session-persistent prefill could linger into a later modal open if a workspace
> arrives by a non-submit path. No HIGH/CRITICAL.
>
> **Consistency with goal** — Matches. LOW: per-mount prefill guard re-applies on
> remount, overwriting a persisted draft edit (accepted in the plan).
>
> **Test coverage** — No issues.
>
> **Dead code** — No issues (EmptyState, auto-open effect, `newWorkspaceModalAutoOpenedAtom`,
> `"auto"` source, backend injection, unused `CreateAgentRequest` import, two
> obsolete tests all removed; `isBranchNamePreviewLoading` still used).
>
> **Comments / Error handling / Security / Type safety / Style & ratchets /
> Public-facing text** — No issues. (`just generate-api` was run for the
> ElementId rename; typecheck/lint/ratchets green; commit message clean.)
>
> **Backwards compatibility** — MEDIUM (intentional): removing the first-agent
> injection drops the auto-greeting for CLI/API agent-creation paths too. Call
> out in the PR body.
>
> **Frontend (`use_derived_atoms`)** — MEDIUM: `useNewWorkspaceModal` reads the
> whole `workspacesArrayAtom` but only needs emptiness; widens re-renders of all
> hook consumers. Consider a derived emptiness atom.
>
> **Integration tests** — LOW `use_pom_hierarchy`: new home test mixes POM and
> raw `get_by_test_id`. LOW `no_lowered_timeouts`: the added inline-form
> visibility assertion in `test_restart_mru.py` reuses the 10s constant; a
> render-dependent wait is safer at the 30s default. LOW: `.first` is used in the
> navigate helper but not in the SPA-ready beacons — a latent strict-mode trap if
> both elements ever co-render at boot.
>
> **Git hygiene** — LOW: commit bundles the feature + the branch-name flash fix
> (thematically related).

## Overall Assessment

Ready to merge. The change is correct, tested at unit and integration level, and
clean on all configured gates. The biggest non-blocking item is the
`use_derived_atoms` re-render widening in `useNewWorkspaceModal` (a small,
optional perf refinement). The one item that must not be lost is documenting the
CLI/API greeting-removal as an intentional behavior change in the PR
description. The three LOW integration-test notes (POM mixing, the 10s timeout on
a render-dependent wait, and the `.first` asymmetry) are good follow-up polish
but do not block.
