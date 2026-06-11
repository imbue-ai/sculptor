# New Workspace Modal — Mock Context

## Description
The current `NewWorkspaceModal` (the modal that opens from Cmd+K → "New
workspace", from the topbar `+` button, and on first launch via the home
auto-open) looks bad. We want to explore 6 visually distinct redesigns
of the same modal before committing to a direction.

The modal must let the user:
- Optionally name the workspace
- Pick a repository (project)
- Pick a source branch
- Pick an environment / initialization mode (Worktree / Clone / In-place)
- Optionally override the auto-generated branch name (worktree/clone only)
- Optionally type an initial prompt for the agent's first message
- Submit with Cmd+Enter or a "Create workspace" button
- See the breadcrumb back to the command palette when entered via Cmd+K

Today, all of those controls are crammed into one screen with the prompt
textarea fighting the toolbar selectors for visual weight. The redesign
exploration is purely visual — the field set and submission contract
stay the same.

## Decisions
- **Direction: G · Linear title-first compose.** Modal reads as a Linear
  "new issue" — title input rendered as a heading, plain-text description
  below, property chips ("repo · from main · Worktree · branch name") in
  a wrap row, thin footer with a primary button on the right.
- White surface, rounded 10px, drop-shadow only (no card border).
- Workspace name = the title; first-task prompt = the description.
- Linear violet (#5E6AD2) is the primary accent; branch values render in
  monospace in violet.
- Cmd+Enter still submits; Esc backs out (returns to palette when
  entered via Cmd+K).

## Rejected Alternatives
(TBD — filled in as the user rules out variants or tweaks)

## Rejected Alternatives
- **A · Refined minimal, B · Classic labeled form, C · Prompt-first hero,
  D · Two-column, E · Stepper / wizard, F · Sectioned cards** — user
  responded "None — keep exploring." All six stayed inside the same
  form-modal pattern. Kept in `mocks.html` for historical record under
  the "Rejected" tab group.

## Tweaks Log
- Requested: initial generation, 6 distinct visual approaches
  Changed: created `mocks.html` with 6 tabbed variants A-F (form-modal
  family). All rejected.
- Requested: 6 new mockups — 3 like Linear's "create new ticket" and
  3 like Raycast.
  Changed: added 6 new variants and marked A-F rejected in the tabs:
    - G · Linear · Title-first compose (canonical Linear new-issue look)
    - H · Linear · Properties table (title + description + property rows)
    - I · Linear · Inline switcher prefix ("New workspace in [repo] from [branch]")
    - J · Raycast · Form view (labeled rows + bottom action bar)
    - K · Raycast · Search-anchored detail (search bar + result + detail panel)
    - L · Raycast · Compact list-form (each property is a row, prompt at bottom)
  Default active tab set to G.
- Requested: pick one. User chose **G · Linear title-first**.
  Changed: recorded G as the chosen direction in Decisions.
- Requested: wrap up — happy with G as-is, no further tweaks.
  Changed: closed out the mock session. `mocks.html` keeps all 12
  variants (G–L active, A–F demoted to rejected); G is the default tab.
