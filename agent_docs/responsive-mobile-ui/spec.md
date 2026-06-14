# Responsive & Mobile-Friendly Sculptor

## Mocks

The agreed visual direction lives in a single interactive mock alongside this
spec at [`mocks.html`](mocks.html) (Foundations, Chat components, and end-to-end
Flows). [`mocks.context.md`](mocks.context.md) records the design decisions and
the iteration log. The sections below are updated to match it.

## Overview

_(Rough first pass — to be sharpened in Q&A.)_

Sculptor's frontend is currently desktop-first with effectively no responsive
design: a single `@media (width <= 800px)` rule, no breakpoint hook, no
breakpoint tokens, no touch handling, and Radix's responsive props unused. The
main Workspace view is a dense 5-zone docking layout (resizable side panels,
center chat + side-by-side diff, bottom terminal, file tree) with hard
minimum widths that cannot reflow gracefully onto a narrow viewport.

This work makes Sculptor adapt to narrow viewports. The immediate, testable
trigger is **viewport width only** — no remote-access or phone-browser plumbing
— so it is fully exercised by resizing the window. But the strategic goal is to
**lay the foundation for a real phone experience later**: window-resize is the
proxy, and design decisions (single-column shell, breakpoint primitives,
touch-friendliness) should be made with phones in mind even though phone
delivery/serving is out of scope for now. The design floor is **~390px** (a
typical phone width) — it must work well there, not just in the band just under
the breakpoint.

Below the breakpoint (mobile = width < 768px, Radix's `sm`), Sculptor reflows
and, for the dense Workspace view, renders a **distinct single-column shell**
rather than a squeezed desktop layout.

**Primary task on mobile: monitor and nudge a running agent** — read the live
chat stream and send a prompt. This is the one flow that must feel good. Viewing
changes (review-all), the terminal, and switching workspaces/agents are
secondary and may be more utilitarian.

Strategy (settled from the mocks, hybrid):
- **Shared foundation:** a 768px breakpoint + a `useLayoutMode` hook
  (`mobile | desktop`, `matchMedia`-backed, re-rendering only on crossing)
  exposed via context, plus breakpoint tokens. Components branch off this, not
  ad-hoc `window.innerWidth`.
- **Simple pages reflow via CSS / `isMobile` in place:** Home, Settings,
  Add-Workspace, TopBar (Radix responsive props + module rules). Settings
  already has a `.mobileNav` dropdown.
- **Workspace view branches to a new tree:** below the breakpoint
  `WorkspacePage` renders a new single-column `MobileWorkspaceShell` (new chrome)
  instead of the desktop `DockingLayout`. The shell **mounts the existing chat,
  review-all, and terminal components unchanged** and only adds mobile chrome
  around them.
- **The shell is _chat-first_, not a tab bar:** Chat fills the screen; Changes is
  a header **changes pill → review-all**; the terminal and other jumps live in a
  **⋮ dropdown**; agents switch via **pager dots under the input**; workspaces
  via a **left drawer**. (The round-1 bottom tab bar was dropped.)
- **Theme:** the warm "sand" light theme is applied **on mobile only**, via a
  scoped design-token override on the shell root, so reused components re-theme
  with no code changes; desktop is untouched.

Mobile feature set is **"monitor + chat"**: list/switch workspaces & agents, read
the chat stream, send prompts, view changes (review-all) and the terminal,
create a workspace/agent. (Approve/reject permission prompts are **not** part of
this product and are not mocked.) Multi-panel docking and side-by-side diff are
deferred.

## User Scenarios

### Monitor and nudge a running agent (primary)
User opens Sculptor in a narrow window (eventually, a phone). They land on a
workspace with a running agent and see the single-column mobile shell, not the
docking layout (REQ-WS-1). The chat fills the screen and streams live
(REQ-WS-2, REQ-CHAT-1). They type a follow-up in the input pinned at the bottom
and send it (REQ-CHAT-2, REQ-CHAT-5); model/effort and attach/skills sit behind
the input's **`+` menu** (REQ-CHAT-3).

### Glance at the changes
When the agent has changes, a **changes pill** appears under the top bar
(REQ-DIFF-1). The user taps it, sees the changed files, and opens **review-all** —
a unified combined diff, full-screen (REQ-DIFF-2, REQ-DIFF-4); a long code line
scrolls horizontally (REQ-DIFF-3). Back returns to the chat.

### Switch agents / workspaces / open the terminal
The user switches agents with the **pager dots under the input**, or swipes to
the dashed dot to create a new agent (REQ-WS-3, REQ-NAV-2). The **drawer** (opened
from the top bar) lists workspaces grouped by repo, to switch or create one
(REQ-NAV-1). The **⋮ menu** jumps to the terminal or review-all (REQ-TERM-1). At
this width the desktop TopBar's workspace tabs collapse into a compact menu
(REQ-NAV-3).

### Resize across the breakpoint
User drags the window from wide to narrow; the layout switches immediately from
the docking layout to the mobile shell (REQ-RESIZE-1). An unsent draft or scroll
position may reset (REQ-RESIZE-2), but the active agent and sent history are
intact (REQ-RESIZE-3). Dragging back to wide restores the desktop docking layout
with the user's previous panel preferences (REQ-LEGACY-1, REQ-LEGACY-2).

### Settings and workspace creation on a narrow window
User opens Settings; the section nav becomes a top dropdown/drawer and content
is full-width; changing a setting saves exactly as on desktop (REQ-PAGES-2).
User opens Add-Workspace; the form, dropdowns, and buttons all fit and are
reachable, and they create a workspace (REQ-PAGES-3).

### Edge cases
- **No changes yet:** the changes pill is absent (no broken list).
- **No workspaces yet:** the workspace drawer shows an empty state with a "New
  workspace" action.
- **Fresh agent, no messages:** the chat shows the existing intro
  (`AlphaChatIntro`) and an "Enter a prompt…" input (REQ-CHAT-4).
- **Agent idle (not running):** the input is still usable to start the next
  prompt.
- **Very long message / wide content:** content wraps; only diffs and code may
  scroll horizontally (REQ-DIFF-3).

## Requirements

### Foundation (REQ-FOUND)
- **REQ-FOUND-1 (MUST):** A breakpoint at **768px** (Radix `sm`) defines the
  boundary: width < 768px = "mobile", width ≥ 768px = "desktop".
- **REQ-FOUND-2 (MUST):** A single shared mechanism (a `useLayoutMode` /
  `useMediaQuery` hook backed by `matchMedia`, exposed via a provider/context)
  reports the current layout mode; components branch off it rather than ad-hoc
  `window.innerWidth` checks.
- **REQ-FOUND-3 (MUST):** The mechanism MUST re-render consumers only when the
  breakpoint is crossed, not on every resize event (the codebase is
  render-count sensitive).
- **REQ-FOUND-4 (SHOULD):** Breakpoint values SHOULD be design tokens that align
  with Radix responsive props, so CSS reflow (`{ initial, sm }`) and JS
  branching agree.

### Breakpoint crossing (REQ-RESIZE)
- **REQ-RESIZE-1 (MUST):** Crossing 768px live MUST switch between desktop and
  mobile layouts immediately.
- **REQ-RESIZE-2 (MAY):** Crossing MAY reset transient UI state (chat scroll
  position, unsent draft); preserving it is not required.
- **REQ-RESIZE-3 (MUST):** Crossing MUST NOT lose durable state — active
  workspace/agent, sent messages, and desktop panel-layout preferences MUST
  survive a round trip across the breakpoint.

### Mobile Workspace shell (REQ-WS)
- **REQ-WS-1 (MUST):** Below the breakpoint the Workspace view MUST render a
  single-column mobile shell and MUST NOT mount the desktop `DockingLayout`, its
  sidebars, resize handles, or the bottom/terminal zone.
- **REQ-WS-2 (MUST):** The shell MUST be **chat-first**: the chat fills the
  screen by default (no bottom tab bar). Changes are reached via a **changes
  pill** in/under the top bar that opens the changes list → **review-all**; the
  **terminal** and other workspace jumps live in a **⋮ dropdown**.
- **REQ-WS-3 (MUST):** A compact top context bar MUST show the current
  workspace/agent identity, switch agents (**pager dots under the input**, with a
  dashed "new agent" dot), and open the **workspace drawer** to switch
  workspaces.
- **REQ-WS-4 (MUST):** The shell MUST reuse the existing **chat interface**
  (`ChatPanelContent` / `AlphaChatInterface`, including tool-call rendering)
  unchanged, and reuse the existing **review-all** and **terminal** components,
  rather than reimplementing them.
- **REQ-WS-5 (MUST):** The shell MUST work well down to a **390px** viewport
  with no horizontal overflow of the shell chrome (top bar, changes pill, input,
  agent dots).
- **REQ-WS-6 (MUST):** The warm "sand" theme MUST be scoped to the mobile shell
  (via a design-token override on its root); it MUST NOT alter desktop styling.

### Chat (REQ-CHAT)
- **REQ-CHAT-1 (MUST):** The chat stream MUST be the **existing chat interface,
  reused unchanged** — same message/markdown/tool-call rendering and live
  streaming as desktop. Its appearance changes only by inheriting the scoped
  mobile theme tokens; no structural or tool-call changes.
- **REQ-CHAT-2 (MUST):** A chat input MUST be pinned at the bottom of the chat
  with the text field and send/stop action always visible.
- **REQ-CHAT-3 (MUST):** Mobile MAY use a **new mobile chat-input component**
  (sharing the underlying submit/draft logic). Its bottom-left is a single **`+`
  context menu** (mention / skills & commands / attach / image); secondary
  controls (model, effort, fast-mode) live there rather than on the input row.
- **REQ-CHAT-4 (MUST):** A fresh agent with no messages MUST show the existing
  chat intro (`AlphaChatIntro`) and the "Enter a prompt…" input — reused, not
  reimplemented.
- **REQ-CHAT-5 (SHOULD):** Sending a prompt, interrupting/cancelling a running
  agent, and a jump-to-bottom affordance SHOULD all be available on mobile.

### Changes / Diff (REQ-DIFF)
- **REQ-DIFF-1 (MUST):** A **changes pill** under the top bar MUST appear when the
  agent has changes (file count + ±stats) and open a changes list of changed
  files (a rounded drawer or bottom sheet that can expand to the top bar).
- **REQ-DIFF-2 (MUST):** The primary diff view MUST be **review-all** (the
  combined diff), reusing the existing review-all component; a single file MAY be
  opened to its own diff.
- **REQ-DIFF-3 (MUST):** Diffs on mobile MUST render as a unified (single-column)
  view; side-by-side is out. Wide code lines MAY scroll horizontally.
- **REQ-DIFF-4 (SHOULD):** Review-all / file diff SHOULD open full-screen, and
  back returns to the chat, reusing the existing diff-open state.

### Terminal (REQ-TERM)
- **REQ-TERM-1 (MUST):** The terminal MUST be reachable on mobile from the **⋮
  dropdown**, opening full-screen and **reusing the existing terminal component**
  (mobile shows a light header over the unchanged terminal body). Back returns to
  the chat.

### Navigation (REQ-NAV)
- **REQ-NAV-1 (MUST):** On mobile the user MUST be able to browse workspaces (in
  the **drawer**, grouped by repo, collapsible) and open one. When there are no
  workspaces, the drawer MUST show an empty state with a New-workspace action.
- **REQ-NAV-2 (MUST):** On mobile the user MUST be able to switch between agents
  within a workspace.
- **REQ-NAV-3 (MUST):** The desktop TopBar workspace tabs (which overflow at
  narrow widths) MUST collapse into a compact control (menu/drawer) below the
  breakpoint.

### Simple-page reflow (REQ-PAGES)
- **REQ-PAGES-1 (MUST):** Home / recent-workspaces MUST reflow to a
  single-column, full-width list with no horizontal overflow; row metadata wraps
  or truncates gracefully.
- **REQ-PAGES-2 (MUST):** Settings MUST adapt its two-column layout so the
  section nav is reachable (top dropdown/drawer) and content is full-width.
- **REQ-PAGES-3 (MUST):** The **new-workspace screen is the default landing**. On
  mobile it MUST be a minimal, full-width form whose only real input is the
  **workspace name** (no "optional" label); the source branch is fixed to
  **origin/main** and the repo selector are shown subtly; no recents or
  shortcut chrome. It MUST be usable at narrow widths and create a workspace.
- **REQ-PAGES-4 (SHOULD):** These pages SHOULD reflow via CSS (Radix responsive
  props + module rules) rather than separate mobile component trees.

### Touch ergonomics (REQ-TOUCH)
- **REQ-TOUCH-1 (MUST):** Interactive targets in the mobile shell (agent dots,
  changes pill, input controls, ⋮ / ＋ menus, file rows, top-bar actions) MUST
  meet a touch-friendly minimum hit area (~44px).
- **REQ-TOUCH-2 (SHOULD):** Tap-friendly spacing SHOULD prevent adjacent targets
  from being easily mis-tapped.
- **REQ-TOUCH-3 (MAY):** Touch gestures (swipe between agents/views, long-press
  menus) MAY be added but are not required in this pass.

### Desktop preservation (REQ-LEGACY)
- **REQ-LEGACY-1 (MUST):** Desktop behavior at ≥768px (docking layout, panels,
  resize, terminal, side-by-side diff) MUST remain unchanged.
- **REQ-LEGACY-2 (MUST):** The mobile shell MUST NOT write to or corrupt desktop
  panel-layout persistence (zone visibility/size atoms); desktop preferences
  persist across mobile sessions.

## Implementation Approach

### Strategy: copy vs. `isMobile` branch vs. new tree

Three patterns, chosen per component by how much the mobile form diverges:

- **A — `isMobile` branch inside the existing component.** One source of truth;
  no duplication; desktop + mobile stay in sync. But it clutters the component
  with branches and risks regressing desktop. Best when the two forms are
  *mostly the same* with small differences (simple pages, TopBar).
- **B — Copy/fork into a `Mobile*` component.** Total freedom to diverge, zero
  risk to desktop — but duplication drifts (fixes/features must be applied
  twice). Best avoided unless a true desktop twin must diverge hard; for genuinely
  new UI there's nothing to fork, so this collapses into (C).
- **C — New mobile tree that mounts the existing leaf components unchanged.** A
  new chrome tree (`MobileWorkspaceShell` + header/drawer/pill) that *imports and
  renders* the heavy content components (chat, review-all, terminal) as-is. Reuses
  the complex parts with zero duplication and isolates the new chrome; desktop is
  untouched. The one risk to de-risk: those leaves must render correctly **outside
  the docking layout**.

**Recommendation (hybrid):** **new tree for chrome that has no desktop twin;
reuse (mount) the heavy content components unchanged; a new component only where
the mobile form is structurally different; `isMobile`/CSS for simple pages that
are mostly the same.** This directly satisfies "reuse the chat interface."

### Per-piece plan

| Piece | Approach | Notes |
|---|---|---|
| Chat stream + tool calls | **Reuse as-is** | Mount `ChatPanelContent` / `AlphaChatInterface`. No code/look/tool-call changes; re-themes via scoped tokens. |
| Review-all (combined diff) | **Reuse as-is** | Mount the existing review-all; opens full-screen. |
| Terminal | **Reuse as-is** | Mount existing terminal; new light header chrome around it. |
| Empty agent (no messages) | **Reuse as-is** | The existing `AlphaChatIntro` + "Enter a prompt…" input. |
| Chat input | **New component** | `MobileChatInput`, sharing submit/draft logic; bottom-left `+` context menu; model/effort/etc. behind it. |
| New-workspace page | **New component** | `MobileNewWorkspace` — minimal, name-only (branch always `origin/main`, repo subtle). Default landing screen. |
| Mobile shell | **New tree** | `MobileWorkspaceShell` — single column, mounts the reused leaves. |
| Top context bar / header | **New component** | `MobileWorkspaceHeader` — back/drawer, workspace+agent identity, ⋮. |
| Workspace drawer | **New component** | `WorkspaceDrawer` (D1) — repos grouped & collapsible; empty state when none. |
| Changes pill + changes list | **New component** | `ChangesPill` → rounded drawer / bottom sheet → review-all. |
| Agent pager | **New component** | `AgentPager` — dots under the input + dashed "new agent" dot, reading existing task/agent atoms. |
| ⋮ jump menu / `+` context menu | **New (reuse Radix)** | Radix `DropdownMenu`; wire to existing actions (terminal, review-all, PR, mention/skills/files). No dim backdrop. |
| Home / recent list | **`isMobile` / CSS** | Reflow in place; reuse `RecentWorkspaces`. |
| Settings | **CSS reflow** | Already has `.mobileNav`; full-width content. |
| TopBar (desktop) | **`isMobile`** | Collapse workspace tabs into a menu below the breakpoint. |
| Foundation | **New** | `useLayoutMode` hook + provider + breakpoint tokens. |
| Branch point | **Edit** | `WorkspacePage`: if mobile, render `MobileWorkspaceShell` instead of `DockingLayout`. |

### Theme (mobile-only)

Apply the sand theme by **scoping a design-token override** (Radix gray/accent +
the semantic tokens) to the mobile shell's root element. Because the reused
components read those CSS variables, they re-theme automatically with **no code
changes**, and desktop (outside the scope) is unaffected. Inter / JetBrains Mono
already match Sculptor's fonts.

### Spike (first proof-of-concept)

De-risk the riskiest assumption first — that the existing chat (and
review-all/terminal) render correctly **mounted outside the docking layout**,
the layout branch doesn't regress desktop, and it doesn't trigger re-render
storms (the codebase is render-count sensitive):

1. Add `useLayoutMode` (matchMedia @768px, re-render only on crossing).
2. In `WorkspacePage`, when mobile render a bare `MobileWorkspaceShell`.
3. `MobileWorkspaceShell` = a static top bar + the mounted `ChatPanelContent` +
   a placeholder input.
4. Verify: chat streams/scrolls with no docking-layout dependency; desktop
   unchanged; crossing 768px both ways is clean; render counts stay sane.

Then layer chrome incrementally: header → changes pill → review-all → ⋮ →
terminal → drawer → agent pager → `MobileChatInput` → scoped theme.

### Things not to forget

- Overlay primitives (drawer / sheet / dropdown) — reuse Radix.
- Empty states: empty workspace drawer (new) and empty agent (reuse intro).
- Routing / back behavior: the drawer and full-screen review-all/terminal must
  map onto the hash router (and a sensible back affordance).
- Touch targets (~44px) and safe-area insets (notch / home indicator) for later
  real-phone delivery.
- Default screen: the new-workspace landing.
- Keyboard handling (input above the on-screen keyboard) — later polish.

## Non-Goals

- **Remote-access / phone-browser plumbing.** Networking, auth, tunneling, or
  serving the frontend to a device other than the machine running it is out of
  scope. The phone-experience goal is served by the *layout foundation*, not by
  delivery.
- **A native mobile app.** No iOS/Android packaging.
- **Approve/reject permission prompts.** Not part of this product; not mocked or
  built on mobile.
- **Multi-panel docking on mobile.** The desktop `DockingLayout` (sidebars,
  resizable zones, drag-and-drop) is not rendered below the breakpoint.
- **Side-by-side diff on mobile.** Mobile shows unified diff only.
- **Desktop redesign / re-theme.** Desktop behavior and styling at ≥768px must
  remain unchanged; the sand theme is mobile-only.
- **Swipe gestures (this pass).** Agent/view switching is via the pager dots and
  controls; physical swipe is a later enhancement.

## Open Questions

- **Mobile nav shape.** *(Resolved by the mocks.)* Chat-first shell; agents via
  pager dots; changes via a header pill → review-all; terminal/jumps via ⋮;
  workspaces via a left drawer; new-workspace as the default landing.
- **Changes surface.** Rounded drawer vs. bottom sheet (expandable to the top
  bar) for the changes list — both are mocked; pick during build.
- **Mobile chat input reuse.** How much of the desktop `ChatInput` submit/draft
  logic the new `MobileChatInput` can share vs. reimplement (a hook extraction?).
- **Outside-the-dock rendering.** Confirm in the spike that `ChatPanelContent` /
  review-all / terminal have no hard dependency on `DockingLayout` (panel
  context, sizing, scroll containers).
- **Theme scoping mechanism.** Exact place to apply the mobile token override
  (a wrapper element/class vs. the Radix `Theme` props) so it covers the reused
  components without leaking to desktop.
- **Routing/back model.** How drawer + full-screen review-all/terminal map onto
  the hash router, and back-affordance behavior.
- **Delivery sequencing.** Suggested phasing (foundation → shell + reused chat →
  changes/review-all → terminal → drawer/header/pill → mobile input → theme →
  simple-page reflow → touch/polish) is for the plan phase, not the spec.
