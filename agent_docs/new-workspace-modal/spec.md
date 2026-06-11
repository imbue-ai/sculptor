# New Workspace Modal

## Overview

Today, creating a workspace happens on a dedicated page at
`/ws/new/:draftId`. We're replacing that page with a modal that uses
the same visual chrome as the new Cmd+K command palette, so workspace
creation feels like a quick action available from anywhere in the app
rather than a separate destination.

The modal contains the same form fields as today's page (workspace
name, repo, branch, init mode, branch name) plus an optional initial
prompt that, when filled, gets sent as the first message to the new
agent. The `/ws/new` route goes away entirely.

## User Scenarios

- **Power user creates a workspace from anywhere.** While working in
  an existing workspace, the user hits `Cmd+Shift+N` (or opens Cmd+K
  and picks "New workspace"). The modal opens over their current
  workspace. They fill in the fields, optionally type a first prompt,
  hit Cmd+Enter, and the current tab switches to the new
  workspace+agent.

- **First-time user lands with no workspaces.** App boots, no MRU
  workspace exists. The user sees the normal app chrome with an
  empty/welcome center pane, and the new-workspace modal pops open
  automatically on top. They create their first workspace.

- **User mid-edit closes the modal.** User starts filling in the form,
  realizes they need to check something, hits Esc. Modal closes,
  current workspace is still visible behind. User does what they need,
  reopens the modal — their inputs are still there. They finish and
  submit.

- **User sends an initial prompt with creation.** User opens the
  modal, picks repo/branch, types a first instruction in the prompt
  textarea ("refactor the auth middleware"), submits. Workspace and
  agent are created, the prompt is sent as the first message, and the
  user lands in the new agent already mid-task.

- **User creates without a prompt.** User leaves the prompt textarea
  empty. Submission creates the workspace+agent and lands the user in
  an empty agent chat — same as today's behavior.

- **User navigates from palette to modal without losing context.**
  User opens Cmd+K, types "new", and selects "New workspace". The
  same Radix Dialog stays mounted; its contents swap from the
  palette's command list to the new-workspace form. The user
  perceives a single surface that "changed pages," not two separate
  modals.

## Requirements

### Visual chrome

- Reuse the same modal frame as the Cmd+K palette: Radix Dialog,
  centered, dimmed backdrop, same border radius / shadow / animation
- Extract the shared dialog shell so both palettes can't visually
  drift over time
- Modal width tuned for the form contents (likely a touch wider than
  the palette's ~600px)
- Show an inline keybinding hint inside the modal (e.g. `⌘↵ to
  create`), mirroring how the command palette surfaces shortcut
  hints to teach the user over time

### Form contents

- All fields visible together on one screen — not a paged/wizard flow
- Fields: workspace name, repo, source branch, init mode (worktree /
  clone / in-place), branch name (with collision preview), optional
  initial prompt
- Reuse existing field components: `BranchNameField`,
  `BranchSelector`, `RepoSelector`, `useBranchNamePreview`
- `Cmd+Enter` submits from any field, matching today's page behavior

### Entry points

- Cmd+K palette: existing "New workspace" command swaps the palette
  contents *in place* with the new-workspace form (same Radix
  Dialog instance, no close/open animation), so the user feels they
  navigated within one surface
- Dedicated keybinding (proposed default `Cmd+Shift+N`) registered in
  the keybinding system at the same level as `command_palette`
- Topbar entry point: a labeled "New workspace" button on the left
  side of `TopBar`, adjacent to the home button (more discoverable
  for new users than a bare `+` icon among the right-side icons)

### Submit behavior

- Pipeline matches today's `AddWorkspacePage.handleSubmit`:
  `createWorkspaceV2` → `createWorkspaceAgent` → navigate
- `createWorkspaceAgent` resolves with the agent ready to receive
  messages — no websocket-readiness wait is needed before sending
- If the prompt textarea is non-empty, send it as the first message
  to the new agent by calling `sendWorkspaceAgentMessages` directly
  from the submit handler (the same API `useChatData.sendMessage`
  uses), before navigating
- After successful creation, navigate the current tab to the new
  workspace+agent (same as today)
- On error (e.g. branch name collision), surface via toast and keep
  the modal open with inputs intact

### State and persistence

- Draft state lives in Jotai atoms (no URL/draftId)
- Inputs persist across modal open/close within a session
- Draft state clears on successful creation
- No reset/start-over button
- `markDraftCreatingAtom` / `clearDraftCreatingAtom` (which guard
  against the WebSocket auto-adding the new workspace as a duplicate
  tab during creation) are kept; they no longer track a URL
  `draftId` and instead key on the in-flight workspace ID

### First-load behavior

- When the app loads with no MRU workspace and no other fallback
  (`getMostRecentlyUsedWorkspace` and `listRecentWorkspaces` both
  empty, no persisted draft tabs), the root loader lands on the
  existing `HomePage` (which renders `RecentWorkspaces`) instead of
  redirecting to `/ws/new`
- The new-workspace modal auto-opens on top of `HomePage` on this
  first-load path
- Auto-open fires only once per app boot via an in-memory atom; if
  the user closes it without creating, it does not re-pop on
  subsequent navigations within the same tab session

### Mutual exclusion with command palette

- Only one of the two surfaces is shown at a time
- When the user picks "New workspace" from inside Cmd+K, the
  contents of the same Radix Dialog instance swap from the palette's
  command list to the new-workspace form (no close/open animation)
- Opening the modal directly (via `Cmd+Shift+N` or the topbar
  button) while the command palette is open closes the palette
  before the modal renders; opening the palette while the modal is
  open closes the modal first

### Back-to-palette affordance

- When the user enters the modal via Cmd+K → "New workspace" (swap
  in place), render a back-arrow / breadcrumb in the modal header
  matching the palette's existing `pushPage`/`popPage` chrome
- First `Esc` (or click on the breadcrumb back arrow) returns to
  the command palette command list; second `Esc` closes the dialog
  entirely
- When the user enters the modal via the dedicated keybinding or
  the topbar button, no breadcrumb is shown and `Esc` closes the
  dialog immediately — entry source is tracked so the affordance
  only appears on the swap-in-place path

### Route deprecation

- Delete the `/ws/new/:draftId` route from `Router.tsx`
- Delete `AddWorkspacePage` and `NewWorkspaceForm`
- Update any redirects and root-loader logic that pointed at
  `/ws/new`
- Field components reused by the modal move out of
  `pages/add-workspace/` into a shared location

## Non-Goals

- **Not a paged/wizard flow.** Each form field does NOT become its
  own cmdk page with `pushPage`/`popPage`. Visual chrome only.
- **Not a primary-prompt-driven palette.** The prompt textarea is
  optional; the modal is not redesigned around it as the lead input.
- **Not a deep-linkable URL.** No `?repo=...&branch=...` query-param
  shortcuts; the route is gone.
- **No multiple concurrent drafts.** A single draft persists per
  session; multi-draft support (which `/ws/new/:draftId` allowed via
  URL) is dropped.
- **No URL preservation.** `/ws/new` and any old draft URLs do not
  redirect to anything specific — they 404 (or fall through to the
  normal not-found behavior).

## Open Questions

- **Dedicated keybinding default.** `Cmd+Shift+N` is the proposed
  default — confirm this doesn't conflict with existing browser/OS
  bindings on supported platforms.
