# New Workspace Modal — Merge-Readiness Review

Scope: the full branch `bryden/scu-1494-rewrite-new-workspace-modal` vs
`origin/main` (`git diff origin/main...HEAD`) — the SCU-752 + SCU-1494
new-workspace-modal rewrite, ending with the inline new-workspace form on an
empty Home. Tracked by **SCU-1494** ("Rewrite the new-workspace modal (mount
form only when open)").

Note on the spec: `agent_docs/new-workspace-modal/spec.md` is the original
SCU-752 spec (and `agent_docs/CLAUDE.md` flags these docs as historical). The
SCU-1494 work **intentionally supersedes** the spec's "First-load behavior"
(auto-open the modal on top of HomePage) with an **inline form on an empty
Home, no auto-open**. Requirements are assessed against the spec with that
divergence called out.

## Summary

- The branch delivers the spec: a Cmd+K-style modal replacing the `/ws/new`
  page, all fields on one screen, optional initial prompt, three entry points,
  palette swap-in-place + back-affordance, draft persistence in atoms, and the
  shell+form (form mounts only when open). SCU-1494 then supersedes first-load
  auto-open with the inline empty-Home form + editable `/sculptor:help` prefill.
- Verified green on `just check` and all four `just test-unit` suites; the
  directly-affected integration suites pass (home, add-workspace, branch
  collisions, restart-mru, onboarding, migration, worktree-create, tab
  enhancements, multi-repo).
- One finding auto-addressed: a stray commented-out assertion + ownerless TODO
  in the unrelated `test_compaction` test (scope creep from `b1a76f1645`) was
  removed. Two non-blocking items to note in the PR body (below). Nothing
  blocks the merge.

## Requirements Coverage

| Requirement (spec section) | Status | Evidence |
|---|---|---|
| Reuse Cmd+K modal frame; extract shared shell | Covered | `PaletteDialog/PaletteDialog.tsx` (shared by palette + modal) |
| Modal width tuned; inline `⌘↵` hint | Covered | `NewWorkspaceModal.module.scss`; `NewWorkspaceForm.tsx` KeyboardHint |
| All fields on one screen (name, repo, source branch, mode, branch name, prompt) | Covered | `NewWorkspaceForm.tsx` |
| Reuse `BranchNameField` / `BranchSelector` / `RepoSelector` / `useBranchNamePreview` | Covered | moved under `components/NewWorkspaceModal/` |
| `Cmd+Enter` submits from any field | Covered | `NewWorkspaceForm.tsx` `handleKeyDown` |
| Entry points: palette swap-in-place, dedicated keybinding, topbar button | Covered | `navigation.ts`, `usePageLayoutKeyboardShortcuts.ts`, `WorkspaceTabs.tsx` |
| Submit pipeline `createWorkspaceV2 → createWorkspaceAgent → navigate`; send prompt if non-empty | Covered | `NewWorkspaceForm.tsx` `handleSubmit` |
| Draft state in atoms; persists across open/close; clears on success | Covered | `atoms.ts` (`draft*Atom`, `resetDraftAtom`) |
| Mutual exclusion with command palette | Covered | `hooks.ts` (closes palette on open) |
| Back-to-palette affordance; entry-source tracking | Covered | `atoms.ts` `NewWorkspaceModalEntrySource`, `NewWorkspaceModal.tsx` Esc handling |
| Route deprecation: delete `/ws/new`, `AddWorkspacePage`, move field components | Covered | files deleted; `Router.tsx`, `NavigateUtils.ts`, `useWorkspaceTabActions.ts` updated |
| First-load behavior (auto-open modal on top of HomePage) | **Superseded** | SCU-1494: empty Home renders the form inline (`RecentWorkspaces.tsx`); no auto-open |

## User Scenarios

- **Create from anywhere / palette → modal swap / send-with-prompt / create
  without prompt:** all delivered by the modal flow; covered by
  `test_add_workspace_page.py`, `test_workspace_tab_enhancements.py`,
  `test_worktree_create_happy_path.py`, `test_create_workspace_without_prompt`.
- **First-time user with no workspaces:** superseding the spec, the empty Home
  renders the form inline with the editable help prefill; covered by
  `test_home_page.py::test_inline_new_workspace_form_shown_and_creates_for_new_user`
  and `test_restart_mru.py::test_restart_with_no_mru_lands_on_home` (routing).
- **Mid-edit close + reopen keeps inputs:** draft atoms persist within a
  session; covered by `test_workspace_form_draft_persists_after_navigation`.
  (Cross-restart persistence is explicitly out of scope — `test_restarts.py`
  carries a justified skip noting drafts aren't serialized across restarts.)

## Test Coverage

- Tests added/updated: the whole integration suite was migrated off `/ws/new`
  to the modal flow; new `homePromptPrefill.test.ts` (unit) and
  `useHomeToggle.test.tsx`; `test_home_toggle_safety.py`; the SCU-1494 inline
  form + restart routing tests. `test_home_page_tab.py` deleted (pseudo-tab gone).
- Suite status: `just check` ✅ (typecheck, lint, ratchets, file-hygiene);
  `just test-unit` ✅ (backend, frontend, imbue-core, sculpt); affected
  integration suites ✅.
- Skips/xfails: all pre-existing or justified — `test_restarts.py`
  (drafts not serialized across restarts), `test_multi_repo.py:313`
  (duplicate-name redesign), `test_onboarding.py:316` (onboarding config
  timing), `test_regression_workspace_mode_persistence.py` (mode persistence
  not yet implemented). No new unjustified skips.

## Code Review Findings

Applied the configured `/code-review-checklist` categories (plus
`docs/review/react.md`, `sculptor.md`, `integration-tests.md`) to the full
branch diff.

- **RESOLVED — Dead code / ownerless TODO (LOW):** `test_task_page_chatting.py`
  `test_compaction` carried a commented-out `assert` and a `# TODO: This fails
  since there's a bug with our context` (added in `b1a76f1645`, unrelated to the
  modal; `origin/main` had no assertion there). Removed — `test_compaction` now
  matches `origin/main`.
- **Note — scope creep (LOW, surfaced not auto-removed):** the branch also
  commits design mocks for two *other* features —
  `agent_docs/generated-workspace-title/` and
  `agent_docs/new-workspace-branch-name/` (~94KB `mocks.html` each). Harmless
  docs, but unrelated to this PR. Left in place because they're intentional
  artifacts I didn't author; consider dropping them from the PR.
- **Note — intentional behavior change:** removing the backend first-agent
  `/sculptor:help` injection drops the auto-greeting for **all** agent-creation
  paths, including CLI/API (which have no frontend prefill). Deliberate — call
  it out in the PR body.
- **SCU-1494 delta findings** (from the prior pass) were all resolved:
  `use_derived_atoms` re-render widening → `isWorkspaceListEmptyAtom`
  (`3a789c885d`); test-polish (POM getters, fragile restart assertion removed,
  beacon `.first` investigated and correctly NOT applied) → `f57ca7a583`.
- All reviewed source files (the modal components, `PaletteDialog`,
  `CommandPalette`/`WorkspaceTabs` refactors, `useHomeToggle`, `AgentSettingsControls`,
  `RepoSelector`, `useWorkspaceTabActions`, `PageLayout`, `NavigateUtils`,
  `useSyncActiveTabFromRoute`, `app.py`) are correct, well-commented, and free of
  effect/atom/error-handling issues per the rules. No CRITICAL/HIGH/MEDIUM
  findings remain.

## Overall Assessment

Ready to merge. The implementation meets the spec (with the deliberate
inline-Home supersession), is well-tested at unit and integration level, and is
clean on all configured gates. No blocking issues. Two things for the PR
description: (1) the intentional CLI/API greeting removal, and (2) the two
unrelated `agent_docs` feature mocks that ride along — drop them if you want a
tighter diff.
