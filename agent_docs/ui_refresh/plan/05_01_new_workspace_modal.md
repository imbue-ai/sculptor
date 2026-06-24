# Task 5.1: New-workspace modal + form + branch-name field (copy scu-1494)

## Goal

Build the new-workspace dialog that replaces the `/ws/new` page: the modal shell, the
form (title, auto-growing prompt, breadcrumb context pills, footer), and the
branch-name pill. Styling comes from the `scu-1494` prototype; behavior from
`goals.md`.

## Stories addressed

WSC-05 (the dialog form: title, auto-grow prompt textarea, breadcrumb context pills
repo/agent-type/mode/branch, footer keep-open switch + Cmd+Enter hint + Create),
WSC-06 (branch-name field: monospace pill, sanitization, shuffle button, stable error
slot), WSC-07 (the `/ws/new` page is removed and replaced by the dialog — the route
deletion is Phase 7; the dialog is built here).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`. Per
`goals.md` → "New workspace dialog", the new-workspace **page** is removed and
replaced by the modal; the styling comes from `scu-1494`'s
`components/NewWorkspaceModal`.

**What to copy** (`design_extraction.md` → "New workspace modal & empty first-run
(scu-1494)"):
- `components/NewWorkspaceModal/NewWorkspaceModal.(tsx|module.scss)` +
  `components/PaletteDialog/PaletteDialog.(tsx|module.scss)` — the opaque
  Raycast-style dialog (720px, centered at 14%, `--shadow-xl`).
- `components/NewWorkspaceModal/NewWorkspaceForm.tsx` — borderless title (heading
  scale) + auto-growing prompt textarea, breadcrumb context row of pills (repo /
  agent type / mode / branch), footer ("keep open" switch + Cmd+Enter hint + Create).
- `components/NewWorkspaceModal/BranchNameField.(tsx|module.scss)` — monospace branch
  pill with sanitization, shuffle button, stable error slot.

**Reuse the existing form fields and creation backend:** today's `/ws/new` page
(`src/pages/add-workspace/`) already has the form inputs and the create flow. The
dialog should **reuse those field components and the create call**, only re-housing
them in the modal (`workspace_creation.md` §3 — the POM's form getters port verbatim;
the load-bearing `create_workspace()` helper keeps its signature, Task 5.4). Find the
current inputs by grepping `TASK_INPUT`, `WORKSPACE_NAME_INPUT`, `BRANCH_NAME_INPUT`,
`BRANCH_SELECTOR`, `START_TASK_BUTTON`.

**Decision B8:** WSC-05/06 surfaces (auto-grow textarea, context pills, keep-open
switch, branch shuffle) are net-new with no current testid; "keep open" keeps the
dialog open after Create for rapid multi-create (form resets, repo/agent-type
retained). The dialog's Create button uses a new id `NEW_WORKSPACE_CREATE_BUTTON`;
**keep the old `START_TASK_BUTTON` on the still-rendered `/ws/new` page** until Task 7.3
deletes that page — don't rename it out from under the old page in the Phase 5–7 window
(Decision B8).

This task depends on the existing add-workspace form/create flow. The four entry
points + modes are **Task 5.2**; the POMs + tests are **Task 5.4**; the `/ws/new`
route deletion is **Task 7.3**.

## Files to modify/create

- `sculptor/frontend/src/components/NewWorkspaceModal/NewWorkspaceModal.tsx` +
  `.module.scss` — new (copied).
- `sculptor/frontend/src/components/NewWorkspaceModal/NewWorkspaceForm.tsx` — new.
- `sculptor/frontend/src/components/NewWorkspaceModal/BranchNameField.tsx` +
  `.module.scss` — new.
- `sculptor/frontend/src/components/PaletteDialog/PaletteDialog.tsx` + `.module.scss`
  — new (if not already present).
- `sculptor/sculptor/constants.py` — add `NEW_WORKSPACE_DIALOG`, `NEW_WORKSPACE_FORM`,
  `NEW_WORKSPACE_PROMPT_TEXTAREA`, `NEW_WORKSPACE_CONTEXT_PILL`,
  `NEW_WORKSPACE_KEEP_OPEN_SWITCH`, `BRANCH_NAME_SHUFFLE_BUTTON`, and the renamed
  Create button id; reuse `TASK_INPUT`/`WORKSPACE_NAME_INPUT`/`BRANCH_NAME_INPUT`/
  `BRANCH_SELECTOR` inside the dialog. `just generate-api`.

## Implementation details

1. Copy the `NewWorkspaceModal`/`PaletteDialog` shell + `NewWorkspaceForm` +
   `BranchNameField` from `scu-1494` (`git show bryden/scu-1494-rewrite-new-workspace-modal:<path>`).
2. Re-wire the form to the **existing** create flow + field components from
   `src/pages/add-workspace/` (reuse, don't reinvent the create call).
3. WSC-05: title (borderless heading), auto-grow prompt textarea, breadcrumb pills
   (repo / agent type / mode / branch), footer (keep-open switch + Cmd+Enter hint +
   Create). Cmd+Enter creates; Cmd+I focuses the name input; arrow-key focus recovery
   (port from the page's behavior).
4. WSC-06: branch field is a monospace pill with sanitization, a shuffle button, and a
   **stable error slot** (the slot is always present so the layout doesn't jump when
   an error appears).
5. "Keep open" (Decision B8): on Create with keep-open on, reset the form (clear
   title/prompt/branch) but retain repo + agent type for the next create.
6. Do **not** copy the prototype's "do not copy" hacks (`field-sizing: content`,
   hardcoded font sizes — `design_extraction.md`).

## Testing suggestions

- WSC-05/06 e2e land in **Task 5.4** (`test_new_workspace_dialog.py` +
  `test_new_workspace_creation_modes.py`) via the `new_workspace_dialog.py` POM,
  rebuilding the form-persistence/Cmd+Enter/Cmd+I/arrow-key/create-without-prompt
  assertions from `test_add_workspace_page.py`.

## Gotchas

- Reuse the existing field components + create call — the POM form getters port
  verbatim and `create_workspace()` keeps its signature (Task 5.4).
- The branch error slot must be **stable** (always rendered) so the dialog doesn't
  jump.
- Don't copy `field-sizing: content` (Chromium-only) — use the prototype's auto-grow
  approach without the hack, or a small JS auto-resize.
- The `/ws/new` route stays until Phase 7 — building the dialog doesn't remove it
  yet.

## Verification checklist

- [ ] `NewWorkspaceModal` + `NewWorkspaceForm` + `BranchNameField` render the WSC-05
  form and WSC-06 branch pill (sanitize/shuffle/stable error slot).
- [ ] Form reuses the existing field components + create flow.
- [ ] Cmd+Enter creates; Cmd+I focuses name; keep-open resets-but-retains.
- [ ] New dialog `ElementIDs` added (existing field ids reused) + `just generate-api`;
  `just check` passes.
