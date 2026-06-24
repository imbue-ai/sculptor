# Task 5.1: New-workspace modal + form + branch field (reuse this branch's fields; copy scu-1494 styling)

## Goal

Build the new-workspace dialog that replaces the `/ws/new` page: a modal shell + form
(title, auto-growing prompt, breadcrumb context pills, footer) + branch-name pill.
**Copy only the `scu-1494` styling/shape**; build the form **reusing this branch's
existing add-workspace field components + create flow**, per `component_hierarchy.md` →
"Workspace creation modal". The prototype's own `NewWorkspaceForm` is **not** copied —
it is coupled to APIs that diverged from this branch (`isWorkspaceListEmptyAtom` /
`AgentSettingsControls` don't exist here; `RepoSelector`/`BranchSelector` prop shapes
differ).

## Stories addressed

WSC-05 (the dialog form: title, auto-grow prompt textarea, breadcrumb context pills
repo/agent-type/mode/branch, footer keep-open switch + Cmd+Enter hint + Create),
WSC-06 (branch-name field: monospace pill, sanitization, shuffle button, stable error
slot), WSC-07 (the `/ws/new` page is removed and replaced by the dialog — the route
deletion is Phase 7; the dialog is built here).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). Per `goals.md` → "New workspace
dialog", the new-workspace **page** is removed and replaced by the modal. The design is
in `component_hierarchy.md` → "Workspace creation modal", the atoms in
`supplemental/state_atoms.md` → "Workspace creation", and the file layout +
reuse-vs-copy list in `supplemental/component_tree.md`.

**Copy for styling/shape only** (`design_extraction.md` → "New workspace modal & empty
first-run (scu-1494)"): the `PaletteDialog` shell (opaque Raycast dialog, 720px,
centered at 14%, `--shadow-xl`), the `BranchNameField` pill (monospace, shuffle, stable
error slot), and the form's visual layout (borderless title + auto-grow prompt textarea
+ breadcrumb context pills + footer). **Do not copy the prototype's `NewWorkspaceForm`
code.**

**Reuse from this branch** (data via props; no `/ws/new` coupling):
- `components/RepoSelector.tsx`, `components/BranchSelector.tsx` (+ `BranchSelectorCore`),
  and `pages/add-workspace/components/BranchNameField.tsx`'s `useBranchNamePreview` hook +
  `useRepoInfo`.
- **Extract** the agent-type picker and the worktree/clone/in-place mode picker — today
  they are inline JSX in `pages/add-workspace/AddWorkspacePage.tsx` (~lines 493–588) —
  into `AgentTypeSelect` and `ModeSelect` components.
- **Factor** the create flow out of `AddWorkspacePage.handleSubmit` into a
  `useCreateWorkspace` hook: the two-step `createWorkspaceV2` → `createWorkspaceAgent`,
  **decoupled from the draft pseudo-tab model** (`markDraftCreatingAtom` /
  `convertNewWorkspaceToTabAtom` / the `NEW_WORKSPACE_TAB_*` plumbing are not carried
  forward — the page + draft model are deleted in Phase 7).
- **Add a prompt** the current form lacks: the dialog's prompt textarea seeds the first
  agent (today's form creates the first agent with no prompt; `createWorkspaceAgent`
  already accepts `prompt`). The empty first-run prefills `/sculptor:help` (Task 5.3).

**Modal atoms** (`state_atoms.md` → "Workspace creation"): `newWorkspaceModalAtom`
(open + preset repo), `keepNewWorkspaceModalOpenAtom`, `lastWorkspaceCreationSettingsAtom`
(MRU — used by the Task 5.2 entry points). The form's field values are **local
component state** (the modal is ephemeral).

**Decision B8:** "keep open" keeps the dialog open after Create for rapid multi-create
(form resets, repo/agent-type retained). The Create button uses a new id
`NEW_WORKSPACE_CREATE_BUTTON`; **keep the old `START_TASK_BUTTON` on the still-rendered
`/ws/new` page** until Task 7.3 deletes it.

This task depends on the existing add-workspace field components + create flow (to reuse
+ extract + factor). The four entry points + the MRU direct-create are **Task 5.2**; the
empty first-run is **Task 5.3**; the POMs + tests are **Task 5.4**; the `/ws/new` route
deletion is **Task 7.3**.

## Files to modify/create

- `sculptor/frontend/src/components/newWorkspace/NewWorkspaceModal.tsx` + `.module.scss`
  — new (PaletteDialog shell, styling copied; opened via `newWorkspaceModalAtom`).
- `sculptor/frontend/src/components/newWorkspace/NewWorkspaceForm.tsx` — new (rewrite;
  reuses this branch's field components + `useCreateWorkspace`).
- `sculptor/frontend/src/components/newWorkspace/BranchNameField.tsx` + `.module.scss` —
  new (styling copied; pairs with the existing `useBranchNamePreview` hook).
- `sculptor/frontend/src/components/newWorkspace/AgentTypeSelect.tsx` + `ModeSelect.tsx`
  — new (extracted from `AddWorkspacePage`'s inline pickers).
- `sculptor/frontend/src/components/newWorkspace/newWorkspaceAtoms.ts` — new (the modal
  atoms above).
- `sculptor/frontend/src/common/state/hooks/useCreateWorkspace.ts` — new (factored
  create flow; no draft-tab coupling).
- `sculptor/frontend/src/components/PaletteDialog/PaletteDialog.tsx` + `.module.scss` —
  new (if not already present; styling copied).
- `sculptor/sculptor/constants.py` — add `NEW_WORKSPACE_DIALOG`, `NEW_WORKSPACE_FORM`,
  `NEW_WORKSPACE_PROMPT_TEXTAREA`, `NEW_WORKSPACE_CONTEXT_PILL`,
  `NEW_WORKSPACE_KEEP_OPEN_SWITCH`, `BRANCH_NAME_SHUFFLE_BUTTON`,
  `NEW_WORKSPACE_CREATE_BUTTON`; reuse `WORKSPACE_NAME_INPUT` / `BRANCH_NAME_INPUT` /
  `BRANCH_SELECTOR` / `PROJECT_SELECTOR` / agent-type + mode ids inside the dialog.
  `just generate-api`.

## Implementation details

1. Build `NewWorkspaceModal` (PaletteDialog shell) opened/closed via
   `newWorkspaceModalAtom`; copy the shell styling from `scu-1494`.
2. Build `NewWorkspaceForm` reusing `RepoSelector`, `BranchSelector`, the existing
   `BranchNameField` + `useBranchNamePreview`, and the extracted `AgentTypeSelect` /
   `ModeSelect`. Field values are local state, seeded from
   `lastWorkspaceCreationSettingsAtom` (and the preset repo when opened from a repo
   group's "+").
3. WSC-05: borderless title, auto-grow prompt textarea, breadcrumb pills
   (repo / agent type / mode / branch), footer (keep-open switch + Cmd+Enter hint +
   Create). Cmd+Enter creates; preserve the page's name-focus + arrow-key focus
   behavior.
4. WSC-06: branch field is a monospace pill with sanitization, a shuffle button, and a
   **stable error slot** (always rendered so the layout doesn't jump).
5. Factor `useCreateWorkspace` from `AddWorkspacePage.handleSubmit` (`createWorkspaceV2`
   → `createWorkspaceAgent` **with the prompt**); on success navigate to the new agent
   and write `lastWorkspaceCreationSettingsAtom`. Do not depend on the draft pseudo-tab.
6. "Keep open" (Decision B8): on Create with keep-open on, reset title/prompt/branch but
   retain repo + agent type.
7. Do **not** copy the prototype's "do not copy" hacks (`field-sizing: content`,
   hardcoded font sizes — `design_extraction.md`).

## Testing suggestions

- WSC-05/06 e2e land in **Task 5.4** (`test_new_workspace_dialog.py` +
  `test_new_workspace_creation_modes.py`) via the `new_workspace_dialog.py` POM,
  rebuilding the form-persistence / Cmd+Enter / focus / create assertions from
  `test_add_workspace_page.py` (now including a prompt).

## Gotchas

- **Do not copy the prototype's `NewWorkspaceForm`** — it's coupled to diverged APIs;
  rebuild the form around this branch's components.
- The create flow must be **decoupled from the draft pseudo-tab model** (deleted in
  Phase 7) — factor it into `useCreateWorkspace`.
- The branch error slot must be **stable** (always rendered) so the dialog doesn't jump.
- Don't copy `field-sizing: content` (Chromium-only) — auto-resize without the hack.
- The `/ws/new` route stays until Phase 7 — building the dialog doesn't remove it yet;
  keep `START_TASK_BUTTON` on the old page.

## Verification checklist

- [ ] `NewWorkspaceModal` + `NewWorkspaceForm` + `BranchNameField` render the WSC-05
  form (incl. the prompt textarea) and the WSC-06 branch pill.
- [ ] Form **reuses** this branch's `RepoSelector`/`BranchSelector`/`BranchNameField` +
  the extracted `AgentTypeSelect`/`ModeSelect`; the prototype form is not copied.
- [ ] `useCreateWorkspace` creates workspace + first agent (with prompt), decoupled from
  the draft pseudo-tab; MRU written.
- [ ] Cmd+Enter creates; keep-open resets-but-retains (Decision B8).
- [ ] New dialog `ElementIDs` added (existing field ids reused) + `just generate-api`;
  `just check` passes.
