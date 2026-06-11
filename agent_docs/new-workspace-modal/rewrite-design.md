# New Workspace Modal — Rewrite Design

Status: proposed. Supersedes the mechanical port in PR #48. Visuals and
user-facing behavior are **preserved exactly**; only the implementation and
tests are rethought for today's codebase.

## Goal

Keep the Linear/Raycast-style "New workspace" modal (shared chrome with the
Cmd+K palette) and every behavior it has today, but remove the seams a review
of PR #48 found: an always-mounted form whose effects run while closed (which
breaks the MRU repo default), a handful of dead atoms / impure state updaters /
eslint-disabled effects, and a batch of test-quality regressions.

## Approach: refactor in place, restructure the seams

I recommend **refactoring in place** rather than reverting the frontend to
`main` and re-porting. The reference already carries a lot of value that a
revert would throw away and risk re-breaking: the hard-won SCSS Radix fixes,
the submit-race fix (commit `20505d4666`), the correct submit-gate semantics,
git ref-format validation + input sanitization, and the debounced
preview/collision hooks. The defects are localized; the end state reads like
today's architecture once the component seams, the project/MRU seeding, and the
tests are restructured. (Revert-and-rebuild remains an option if you'd prefer a
cleaner git story — call it out and I'll switch.)

## Architecture: what mounts when (the central change)

Today `PageLayout` mounts `<NewWorkspaceModal />` permanently. All form hooks —
lazy project load, "auto-select newly added projects", branch-name preview,
agent-settings reset — live at the **top level** of that always-mounted
component, so they run on every app render regardless of `isOpen`. That is the
root cause of defect 1.

New structure — split into a thin always-mounted shell + an inner form that
only mounts while open:

- **`<NewWorkspaceModal />`** (always mounted in `PageLayout`): reads
  `newWorkspaceModalOpenAtom` / `entrySource`, renders `<PaletteDialog open=…>`
  and the open/close/escape glue. Renders the modal's `<Toast />` driven by a
  toast atom (see below). It holds **no form state and no fetching effects**.
  The inner form is passed as `PaletteDialog` children, which Radix only mounts
  when the dialog is open.
- **`<NewWorkspaceForm />`** (new component, mounts only when open): owns every
  field hook — project list, MRU seeding, branch-name preview/collision,
  agent-settings local state, submit. Because it mounts fresh on each open and
  unmounts on close:
  - Form effects never run while the modal is closed → **defect 1 fixed**: the
    boot-time WebSocket projects push happens while the form is unmounted, so it
    can't make every project look "new".
  - Agent-settings overrides initialize from current defaults via `useState`
    initializers at mount — **no reset effect, no `eslint-disable` (defect 8)**.
  - Draft fields stay in atoms (below), so they survive the unmount and restore
    on reopen.

Add-repo flow is unaffected: `AddRepoDialog` is a nested child dialog inside
`RepoSelector` and does not close the parent modal, so the form stays mounted
across an add-repo and the auto-select effect still fires for the WS-pushed new
project.

## State model (atoms)

Drafts persist across open/close, reset on successful create — unchanged set,
minus dead code:

- Keep: `draftWorkspaceNameAtom`, `draftSelectedProjectIdAtom`,
  `draftUserSelectedBranchAtom`, `draftInitializationModeAtom`,
  `draftBranchNameOverrideAtom`, `draftInitialPromptAtom`, `resetDraftAtom`,
  `newWorkspaceModalOpenAtom`, `newWorkspaceModalEntrySourceAtom`,
  `newWorkspaceModalAutoOpenedAtom`.
- **Add** `newWorkspaceToastAtom` (modal-scoped toast content). The form sets
  it; the always-mounted shell renders it, so a toast set right before
  close/navigate (e.g. "initial message failed") survives the form unmount.
  This replaces the reference's "keep Toast at a stable position outside the
  `isOpen` gate" trick, which only worked because the whole component was
  always mounted.
- **Remove dead atoms** (defect 5): `activeTabAtom` and the deprecated
  `openWorkspaceTabIdsAtom` alias in `state/atoms/workspaces.ts` (zero
  consumers — confirmed by grep).

`useNewWorkspaceModal` keeps `{ isOpen, open, close, toggle }` but `toggle` is
rewritten so the state updater is **pure** (defect 9): compute the next open
state and perform the entry-source / palette-close writes outside the updater.

## Project / MRU seeding (defect 1, the positive design)

- Read the project list from the **WS-pushed atom** via `useProjects()` instead
  of fetching `getActiveProjects` and mirroring into the atom (aligns with
  `use_ws_hooks_for_pushed_data` / `no_bespoke_fetch_caching`).
- Seed the default repo once per open, only when the user has no persisted
  choice: in a mount effect, `setSelectedProjectId(prev => prev ?? mru ?? first)`
  where `mru` comes from a single `getMostRecentlyUsedProject` HTTP read (it is
  genuinely not WS-pushed). The `prev ??` guard preserves the user's last choice
  across opens.
- "Auto-select newly added projects" stays, but now seeds `prevProjectIdsRef`
  from the open-time project snapshot (form mounts on open), so only projects
  added via `AddRepoDialog` *while open* are auto-selected — never the boot push.

## Branch name field & preview (preserve behavior)

`BranchNameField`, `useBranchNamePreview`, `branchNameValidation`,
`sanitizeBranchName`, the shuffle button, debounced preview (250 ms) + debounced
collision (300 ms), and the inline error/required slot are kept essentially
as-is. Submit-gate semantics from commit `20505d4666` are preserved verbatim:

- `isBranchNameMissing` — always gates submit on a non-empty worktree branch.
- `isBranchNameRequired` — visual red border/"required" caption, **suppressed
  while the preview is loading**.
- Submit stays disabled while the preview fetch is in flight
  (`isBranchNamePreviewLoading`) so a click can't land on an empty/stale name.

## Smaller corrections

- **Defect 10 (aria-disabled):** the Home button's `useHomeToggle` no-op on
  `/home` with no visible tabs is reflected via `aria-disabled` on the button
  bound to the same `!hasVisibleTab` gate (keeps the handler early-return as
  defense-in-depth). Fix the `useMemo` comment in `useHomeToggle` to state the
  real reason the callback is stable (memo on the boolean keeps identity stable
  across tab WS updates so the keybinding effect doesn't re-register).
- Keep the `isLoadProjectsInFlightRef` rationale only if the load effect
  remains; with `useProjects()` the heavy guard mostly goes away (one-shot MRU
  read with a request-id ref is enough).

## Entry points & palette composition (behavior unchanged)

Preserve all current entry points and the exact source values:
- `WorkspaceTabs` "+" add button → `open("topbar")`.
- `HomePage` first-load auto-open (`?firstLoad=true`, once per boot via
  `newWorkspaceModalAutoOpenedAtom`) → `open("auto")`.
- `new_workspace` keybinding (`usePageLayoutKeyboardShortcuts`) → `"keybinding"`.
- Cmd+K palette row "New workspace" (chevron-marked) → `openNewWorkspaceFromPalette` → `"palette"`.

Palette/modal mutual exclusion, the swap-in-place feel, the back-arrow
breadcrumb, and Esc/ArrowLeft-at-0 "pop back to palette" (palette entry only)
are all kept. `PaletteDialog` stays the shared frame (inline, no Portal, so dark
tokens apply) and keeps its pathname-change auto-close.

## Test plan (restore quality)

Consolidate on a proper modal POM and fix the specific regressions:

1. **Rename/retarget the modal POM.** `pages/add_workspace_page.py`'s
   `PlaywrightAddWorkspacePage` already wraps the modal elements correctly
   (`select_mode` handles open→click→wait-hidden). Update its docstring (drop
   "/ws/new"), add a `NEW_WORKSPACE_MODAL` accessor, and **migrate the
   raw-`get_by_test_id` tests onto it**: `test_worktree_create_happy_path.py`,
   `test_worktree_deletion_policies.py`, `test_branch_name_collisions.py`,
   `test_clone_mode_branch_name.py`, `test_branch_switching_integration.py`.
2. **Defect 2 (collection failure):** delete the nonexistent
   `enable_worktree_workspaces` import + calls from the three worktree files;
   worktree is the default and needs no flag. Remove the `MODE_SELECTOR` /
   `MODE_OPTION_WORKTREE` clicks (selector is hidden in default worktree mode).
3. **Defect 3 (clone tests not testing clone):** add `enable_clone_workspaces`
   + explicit `select_mode(CLONE)` to `test_clone_mode_branch_name.py`, the
   clone case in `test_branch_name_collisions.py`, and
   `test_branch_switching_integration.py`'s mislabeled clone test.
4. **Defect 4 (stale POM):** delete `get_home_tab` / `close_home_tab` (reference
   removed `ElementIDs.HOME_TAB`), `get_add_workspace_tabs`, and the dead
   `ADD_WORKSPACE_TAB` branch in `playwright_utils.navigate_to_add_workspace_page`.
5. **Defect 6 (test quality):** restore the shared
   `elements/ask_user_question.py` POM in `test_ask_user_question.py` (drop the
   duplicated local helpers); re-examine the autouse legacy-chat-view pin
   (main ran on the default view); remove the `wait_for_timeout` sleeps in
   `test_ask_user_question.py` and `test_workspace_close_vs_delete.py`; remove
   the 3-attempt Cmd+W swallow-AssertionError loop in
   `test_workspace_tab_enhancements.py`; raise the sub-30s `expect` timeouts to
   the harness default (keep only genuine performance assertions lowered).
6. **Defect 7 (missing regression):** add a test that the create button stays
   disabled until the branch-name preview settles (the `20505d4666` race).
7. Keep the testing-infra additions that are correct (`spawn` landing on
   `/#/home`, `trigger_root_loader`, `set_local_storage_item_with_storage_event`).

## ElementIds contract

Keep the test contract stable: `NEW_WORKSPACE_MODAL`, `WORKSPACE_NAME_INPUT`,
`BRANCH_NAME_INPUT`, `START_TASK_BUTTON`, `MODE_SELECTOR`,
`MODE_OPTION_{WORKTREE,CLONE,IN_PLACE}`, `BRANCH_NAME_RESET_BUTTON`,
`BRANCH_NAME_COLLISION_ERROR`, `NEW_WORKSPACE_PROMPT_INPUT`, `TASK_STARTER`,
`PLAN_MODE_TOGGLE` all stay. `HOME_TAB` is already removed; `ADD_WORKSPACE_TAB`
is now orphaned (left in `constants.py` for stale-localStorage tolerance, no
live producer). No ElementId churn → minimal test churn; no `just generate-api`
needed unless a new id is introduced.

## Validation & commits

Per `CLAUDE.md`, run `just format && just check && just test-unit` only at
commit time (incl. the new `useHomeToggle` / atoms unit tests and the frontend
component tests). Integration tests run via the `run-integration-test` skill.
Sequence as atomic commits: (a) atoms + hooks cleanup, (b) form split +
project/MRU seeding, (c) home-toggle aria + comment, (d) POM + test fixes,
(e) new submit-race regression test.

## Risks / things to verify during implementation

- Nested `AddRepoDialog` over `PaletteDialog` focus/stacking stays correct after
  the form split (verify add-repo-from-modal still auto-selects).
- Radix mounts/unmounts `PaletteDialog` children on open/close as assumed (no
  `forceMount`); confirm the open autofocus-to-title still lands.
- The toast-atom move keeps the "toast survives close+navigate" guarantee.
