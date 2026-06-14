# Responsive / Mobile Sculptor — Spec

## Overview

Sculptor's Workspace view is a desktop multi-panel docking layout that is unusable on a
phone. This work makes Sculptor usable in a narrow, single column. The deliverable is a
**spike that reproduces [`mocks.html`](mocks.html) in the real app**: a chat-first
single-column shell that **reuses the real chat, review-all, and terminal components**
mounted outside the docking layout, wrapped in new mobile chrome (header, drawer, changes
pill, agent pager) and a mobile-only "sand" theme. The spike's job is to prove the reuse
strategy holds before any polished chrome is built; the desktop experience is left
untouched.

[`mocks.html`](mocks.html) is the source of truth for the design. [`mocks.context.md`](mocks.context.md)
records the decisions and the full design history behind it.

## Baseline — what this branch already provides

This work is stacked on **`bryden/remote-repo-design`**, which already lands two pieces the
mobile UI would otherwise have to build. The spec **reuses** them rather than re-implementing:

- **`origin/main` is the global default source branch.** `AddWorkspacePage` no longer has a
  source-branch picker; `createWorkspaceV2` is called with a `sourceBranch` computed as
  `origin/main` → `origin/master` → the repo's current branch. The mobile landing (L1–L4)
  **inherits** this default and shares the same creation path — it does **not** re-implement
  "always origin/main" itself.
- **iOS safe-area insets are handled in CSS via `env(safe-area-inset-*)`**, not JS:
  `index.html` sets `viewport-fit=cover` + the `apple-mobile-web-app-*` meta, `PageLayout`
  pads the app shell by `env(safe-area-inset-bottom)` (with `box-sizing: border-box` so it
  stays exactly `--app-height` tall), and `TopBar.module.scss` pads by
  `env(safe-area-inset-top)`. These resolve to `0` off iOS, so they are no-ops on
  Electron/desktop. The mobile shell **reuses this CSS pattern** (see S5/H4); insets are
  **not** wired off `useLayoutMode.platform`.

## Goals

- Build `MobileWorkspaceShell` — a single-column, chat-first Workspace view that matches the mock.
- **Reuse the real chat, review-all, and terminal** unchanged, mounted outside `DockingLayout`.
- Add a `useLayoutMode` hook and a **single branch point** in `WorkspacePage` that swaps the shell in.
- Apply the **mobile-only "sand" theme** as a scoped token override so reused components re-theme with zero code changes.
- Reflow the simple pages (Home, Settings, TopBar) in place.
- **Prove the spike first**: the reused components render correctly outside the docking layout, without re-render storms.

## User Scenarios

All scenarios are exactly the flows in `mocks.html` (the **Flows** tab). They assume a
narrow viewport (a phone, or a narrow Electron/desktop window during development).

1. **Land and create a workspace (default screen).** Opening Sculptor lands on a minimal
   **new-workspace** screen: a "Name your workspace" hero, a single name field (focused),
   a subtle `repo · origin/main` meta line, and a full-width **Create workspace** button.
   No recents, no shortcut chrome. Naming and tapping Create starts an agent and drops the
   user into the chat.

2. **Monitor an in-progress agent (home / chat).** The chat fills the screen. A compact
   header shows the workspace name with an `agent · repo` subtitle and a live status dot.
   The user reads the streaming chat — user bubbles, assistant markdown, collapsible
   status/tool lines, tool cards, the "Working…" indicator — and replies through the input
   pinned at the bottom. Agent pager dots sit just under the input.

3. **Switch workspaces via the drawer (Flow A).** Tapping ☰ (top-left) slides a left
   drawer over the chat (dimmed backdrop). Workspaces are **grouped by repo**, collapsible,
   with per-repo counts and status dots; the current one is highlighted. A full-width
   **New workspace** button is pinned at the bottom. Selecting a workspace switches to it.

4. **Review changes (Flow B).** A small **changes pill** under the header summarizes
   `+X −Y · N files`. Tapping it expands a floating list of changed files (status badge,
   name, path, per-file counts) **overlaying the chat** (the input stays put). **Review all
   changes** pushes a full-screen **combined unified diff** (per-file sticky headers, a
   "viewed" check, "Show next lines"). Back returns to chat.

5. **Open the terminal (Flow C).** The ⋮ menu (top-right) is an anchored dropdown —
   Open terminal · Review all changes · View pull request · Rename agent · Workspace
   settings. **Open terminal** pushes a full-screen terminal (light header, dark body).
   Back returns to chat.

6. **Switch and create agents (Agents flow).** The **pager dots under the input** switch
   between the workspace's agents (tap a dot or swipe); the header subtitle and chat update.
   A **dashed "new agent" dot** sits at the end of the dots; swiping past the last agent /
   tapping it lands on a fresh empty chat to compose the new agent's first prompt.

7. **Empty states.** A workspace with no workspaces shows a friendly **empty drawer**
   ("No workspaces yet" + New workspace). A fresh agent shows the existing **chat intro**
   (`AlphaChatIntro`: "Branched off origin/main…", "This is agent X in workspace Y", "All
   agents in this workspace share the same code…", "Type `/sculptor:help`…") with the
   "Enter a prompt…" placeholder and no changes pill.

## Requirements

Re-derived from `mocks.html`. Grouped by surface.

### Foundation

- **F1.** A `useLayoutMode` hook is the single source of truth for "mobile vs desktop"
  (detection trigger resolved in [Implementation Approach](#detection-trigger-resolved)).
  The width boundary is **768px** (Radix's `sm`), aligned so CSS responsive props
  (`{ initial, sm }`) and the JS branch agree on the same number. It re-renders consumers
  **only when the mode flips**, never on every resize — the codebase is render-count sensitive.
- **F2.** `WorkspacePage` has exactly **one branch point**: when the mode is mobile, render
  `MobileWorkspaceShell`; otherwise render the existing `DockingLayout` path unchanged.
- **F3.** The **desktop experience is unchanged** — no behavior, layout, or render-count
  regressions — and the mobile shell **must not write to or corrupt desktop panel-layout
  persistence** (zone size/visibility atoms), so desktop preferences survive a mobile session.
- **F4.** Crossing 768px live (dragging the window) **switches layouts immediately**. Durable
  state (active workspace/agent, sent messages, desktop panel preferences) **survives a round
  trip**; transient state (unsent draft, scroll position) **may** reset.

### Mobile Workspace shell

- **S1.** `MobileWorkspaceShell` is a **single column, chat-first** layout. There is **no
  bottom tab bar**. Top → bottom: OS status bar region · workspace header · optional changes
  pill · chat stream (fills) · chat input · agent pager.
- **S2.** The shell **replaces the global desktop `TopBar`** within the Workspace view; its
  own header carries navigation. Because `PageLayout` renders `TopBar` above the routed
  `<Outlet>` unconditionally today, "replace" means `PageLayout` must **suppress `TopBar`**
  for the mobile Workspace view (see Open Q8); the mobile header is then the only top chrome.
- **S3.** Secondary surfaces (drawer, review-all, terminal) open **over** the chat
  (drawer/overlays) or **as anchored dropdowns** (⋮, `+`), never as docked panels.
- **S4.** The shell must work down to a **~390px design floor** (the mock devices are ~380px)
  with **no horizontal overflow** of the shell chrome (header, changes pill, input, dots).
- **S5.** **Touch ergonomics:** interactive targets (header actions, agent dots, pill,
  input controls, ⋮/`+` menu items, file rows) meet a touch-friendly hit area (~44px), and
  the shell respects **safe-area insets** (notch / home indicator) by **reusing the existing
  CSS `env(safe-area-inset-*)` pattern** (see Baseline): the mobile header takes over the
  **top** inset (replacing `TopBar`'s `env(safe-area-inset-top)`), and the shell sits inside
  `PageLayout`'s existing **bottom** inset. Insets are CSS-driven and auto-zero off iOS — they
  are **not** keyed off `useLayoutMode.platform`.

### Header / context bar (new)

- **H1.** Left: ☰ (`square-menu`) opens the workspace drawer.
- **H2.** Center: title = workspace name; subtitle = `agent · repo` with a small status dot.
- **H3.** Right: ⋮ (`circle-ellipsis`) opens the jump dropdown.
- **H4.** A border separates the header from the content; the header background matches the
  status-bar region (uniform, no seam). The header carries the `env(safe-area-inset-top)`
  padding (taking over from the now-suppressed `TopBar`; see S2/Open Q8) so its background
  fills behind the notch / status bar.

### Workspace drawer (new)

- **D1.** Left drawer, slides in over the chat with a **dimmed backdrop**; tapping the
  backdrop closes it.
- **D2.** Header: "Sculptor" wordmark + user avatar. Nav rows: Home, Workspaces.
- **D3.** Workspaces are **grouped by repo**, each group **collapsible** (chevron) with a
  count; rows show a status dot (running / idle / unread / done), workspace name, branch.
- **D4.** The current workspace is highlighted.
- **D5.** A full-width **New workspace** button is pinned at the bottom.
- **D6.** Empty state: "No workspaces yet" + the New workspace button.

### Changes pill + list (new)

- **C1.** A small pill under the header shows `git-compare` · "Changes" · `+X −Y · N files`
  · chevron. It is **shown only when there are changes** (absent on a fresh agent).
- **C2.** Tapping it expands **downward into a floating list overlaying the chat** — the
  chat and input stay in place. Each file row: status badge (M/A/D), filename, path,
  per-file `+/−`.
- **C3.** The expanded list has a **Review all changes** button → opens the review-all overlay.

### Review-all overlay (reused component)

- **R1.** Full-screen overlay, pushed in from the right. Header: back
  (`circle-chevron-left`) · "Review all changes" · `+X −Y · N files` · an overflow/settings action.
- **R2.** Body is the **combined diff**: per-file sticky header (status, filename, `+/−`, a
  "viewed" check), diff lines, "Show next lines" expander.
- **R3.** **Unified only** — no side-by-side on mobile.
- **R4.** Single-file diff is secondary to review-all (review-all is the primary way to view changes).
- **R5.** Back returns to the chat.

### Terminal overlay (reused component)

- **T1.** Reached from the ⋮ dropdown ("Open terminal"). Full-screen overlay; back returns to chat.
- **T2.** Header is light ("Terminal" · `repo · branch` · overflow); the terminal body is
  dark. Mono, no wrap.

### ⋮ jump dropdown & `+` context menu (new, Radix)

- **M1.** The ⋮ menu is a **standard Radix dropdown anchored under the icon with no dim
  backdrop** (a transparent click-catcher dismisses it). Items: Open terminal · Review all
  changes (N files) · View pull request (#NN) · — · Rename agent · Workspace settings.
- **M2.** The chat input `+` opens its own anchored dropdown (also no dim): Mention · Skills
  & commands · Attach files · Add image.

### Chat (reused component, unchanged)

- **CH1.** The real chat interface (`ChatPanelContent` / `AlphaChatInterface`, including
  **tool-call rendering**) renders inside the shell with **no look or behavior changes**:
  timestamp dividers, user bubbles, assistant markdown (prose / lists / code blocks),
  collapsible status & tool lines, tool cards with output, the "Working…" indicator.
- **CH2.** A fresh agent renders the existing **`AlphaChatIntro`** + the real "Enter a
  prompt…" placeholder.

### Chat input (new component, shared logic)

- **I1.** A new rounded floating input. Placeholder is "Reply to `<agent>`…" (or "Enter a
  prompt…" on a fresh agent).
- **I2.** It **shares the desktop input's submit/draft logic** — `usePromptDraft(taskID)`,
  the send / interrupt-and-send path, and the per-task model / fast-mode / effort atoms — and
  is purely a new presentation over that logic.
- **I3.** Bottom-left `+` (`circle-plus`) opens the `+` context menu (M2). **Model & effort
  live behind the `+`** rather than as always-visible toolbar selectors.
- **I4.** Right side: **send** (`arrow-up`, idle/active states) when not running; **stop**
  (square) when the agent is busy — mirroring the real input's send/interrupt behavior.

### Agent pager (new)

- **A1.** Centered pager **dots under the input**, one per agent (active dot elongated /
  accent), plus a **dashed outline "new agent" dot** at the end.
- **A2.** Tapping a dot (or swiping the chat) switches the active agent; the header subtitle
  and chat update.
- **A3.** Tapping the dashed dot / swiping past the last agent lands on the **new-agent
  compose destination** — a fresh empty chat (same as the empty-agent state, CH2).

### New-workspace / landing page (new component)

- **L1.** The **new-workspace screen is the default landing**. Minimal header
  (☰ · "Sculptor" · settings).
- **L2.** Hero "Name your workspace"; **one real input** — the workspace name (focused).
- **L3.** Branch is **always `origin/main`** — **inherited from the existing global default**
  (see Baseline), not re-implemented here. Repo and branch are shown as a subtle, tappable
  meta line (tapping switches repo via the existing `RepoSelector`). No recents, no
  keyboard-shortcut hint.
- **L4.** A full-width **Create workspace** button creates the workspace and starts an agent.

### Reflow in place (CSS / `isMobile`)

- **P1.** **Home** reflows to a single narrow column.
- **P2.** **Settings** keeps its existing `.mobileNav` dropdown pattern (today a container
  query at 825px → top dropdown + full-width content).
- **P3.** **TopBar** (where it is still shown, e.g. Home/Settings) **collapses the workspace
  tabs into a menu**.

### Theme

- **TH1.** A warm **"sand" light theme** — `bg #FAE8CA`, `accent #F50D00`, supporting
  surface/ink/diff tokens — with **Inter** (UI) + **JetBrains Mono** (code) and real
  **Lucide** icons.
- **TH2.** Applied **mobile-only** via a **scoped design-token override on the shell root**,
  so the reused chat / review-all / terminal re-theme with **no code changes**. Desktop is untouched.

## Implementation Approach

### Component strategy (the agreed hybrid)

The shell is mostly new chrome wrapping **reused, unchanged** content components. The hybrid
is deliberate: **reuse the heavy content leaves** (chat, review-all, terminal) to avoid
forking complex code, build **new chrome** only where there is no desktop twin, and use
**`isMobile`/CSS** for the simple pages that are mostly the same — so nothing is duplicated
and desktop is untouched. The split (proposed component names in parentheses):

| Piece | Strategy |
| --- | --- |
| Chat interface — `ChatPanelContent` / `AlphaChatInterface` (incl. tool-call rendering) | **Reuse unchanged** (mount the real component) |
| Review-all combined diff — `CombinedDiffView` | **Reuse unchanged** (unified) |
| Terminal | **Reuse unchanged** |
| Empty-agent intro — `AlphaChatIntro` | **Reuse unchanged** |
| Mobile chat input (`MobileChatInput`) | **New component**, shares submit/draft logic with `ChatInput` |
| New-workspace page (`MobileNewWorkspace`) | **New component**, shares `AddWorkspacePage`'s create-workspace submit core (`createWorkspaceV2` + `createWorkspaceAgent` + `navigateToAgent`; already defaults `origin/main`) |
| Mobile shell tree (`MobileWorkspaceShell`) | **New** (no desktop twin) |
| Header / context bar (`MobileWorkspaceHeader`) | **New** |
| Workspace drawer (`WorkspaceDrawer`) | **New** |
| Changes pill + changes list (`ChangesPill`) | **New** |
| Agent pager (`AgentPager`, dots + dashed new-agent) | **New** |
| ⋮ jump dropdown / `+` context menu | **New** (reuse Radix `DropdownMenu`) |
| Home, Settings, TopBar | **`isMobile` / CSS reflow in place** |
| `useLayoutMode` hook + `WorkspacePage` branch | **Foundation** |

Key real-component facts that make this viable (from a codebase pass):

- `DockingLayout` provides **no React context** — panels read Jotai atoms directly. So
  mounting chat/diff/terminal **outside** it is not blocked by a missing provider; the open
  question is sizing and scroll containers, not context.
- `ChatPanelContent` is a thin content wrapper with **no layout dependencies**.
- `AlphaChatInterface` sizes itself via **flex** and drives a virtualizer off a
  `scrollContainerRef`; it needs a proper flex parent (`min-height: 0`) and measures the
  intro with a `ResizeObserver`. The mobile shell must give it that parent.
- `CombinedDiffView` powers "review all"; it is gated behind `isReviewAllEnabledAtom` today
  and inherits unified/split from `fileBrowserDiffViewTypeAtom` (mobile forces unified).
  Its diff body is rendered by **Pierre (shadow DOM)** — re-theming and narrow-column
  behavior need verification.
- `ChatInput` owns send/draft logic **internally** (not a standalone hook): `usePromptDraft`,
  a `sendMessage`/interrupt path, and `modelAtomFamily` / `fastModeAtomFamily` /
  `effortAtomFamily`. The mobile input shares this by **extracting the submit/draft core**
  into something both inputs call, rather than duplicating it.
- `AddWorkspacePage` already creates a workspace via `createWorkspaceV2` (with `sourceBranch`
  defaulting to `origin/main`; see Baseline) + `createWorkspaceAgent` + `navigateToAgent`, and
  drives the name field through `useDraftTabName(draftId)`. `MobileNewWorkspace` should
  **share this submit core** rather than duplicate it — the same reuse posture as the mobile
  chat input. The mobile landing drops the new-branch-name field and the gated harness/mode
  selectors, keeping only the workspace-name input and a tappable `repo · origin/main` meta line.

### Theme: scoped token override

The mock expresses the sand palette with custom names (`--bg`, `--surface`, `--accent`,
`--ink`). The real reused components consume **Radix tokens** (`--gray-*`, `--accent-*`,
`--color-background`, `--color-panel`, …) plus app semantic tokens. So the mobile-only
override must **remap the Radix/app token names the real components actually read**, scoped
to the `MobileWorkspaceShell` root class — not introduce a parallel set of custom variables.
`ThemeProvider` today only toggles a binary Radix `appearance` (light/dark); the sand theme
is a **third, scoped variant** applied by class on the shell root, leaving the global theme
untouched. Confirming this remap actually re-themes the reused components (especially Pierre)
is part of the spike.

### <a id="detection-trigger-resolved"></a>Detection trigger (resolved): hybrid in `useLayoutMode`

**Question raised:** can we detect **iOS/Android** instead of measuring pixels?

**Recommendation: a hybrid trigger.** Pure platform detection is wrong on its own here —
there is **no phone delivery yet**, so the mobile UI is exercised by a **narrow
Electron/desktop window**, where platform detection would never fire and the shell would be
undevelopable and untestable. Pure pixel-measurement is also insufficient — it cannot tell a
real phone from a small window, and we want true-platform signals to drive native
conventions (safe-area insets, back gesture, system font).

So `useLayoutMode` treats the view as **mobile when EITHER** the viewport is narrow **OR**
the platform is a real touch phone, **and separately exposes the platform** so platform-only
conventions can key off it:

```ts
// mode flips on the width media query OR a (static) phone-platform signal.
type LayoutMode = "mobile" | "desktop";
interface LayoutState {
  mode: LayoutMode;                 // mobile = narrow OR real phone
  isMobile: boolean;                // convenience === (mode === "mobile")
  platform: "ios" | "android" | "other";
  isTouch: boolean;
}

// width trigger — dev-testable in a narrow Electron/desktop window:
const NARROW = "(max-width: 767px)"; // < 768px === Radix `sm`

// phone-platform trigger — static, computed once:
function detectPhonePlatform() {
  const uaData = (navigator as any).userAgentData;
  if (uaData?.mobile) return uaData.platform?.toLowerCase().includes("android") ? "android" : "ios-or-other";
  const ua = navigator.userAgent;
  if (/Android/i.test(ua)) return "android";
  if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
  // iPadOS reports as desktop Safari ("MacIntel") — disambiguate via touch points:
  if (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) return "ios";
  if (window.matchMedia("(pointer: coarse)").matches) return "touch"; // last-resort touch signal
  return "none";
}
```

- **Width** (`matchMedia("(max-width: 767px)")`) keeps the shell developable on the desktop.
- **Platform** (`navigator.userAgentData?.mobile`; UA `/Android/` and `/iPhone|iPad|iPod/`;
  `MacIntel` + `maxTouchPoints > 1` for **iPadOS-reporting-as-Mac**; `pointer: coarse` as a
  fallback) catches a real phone regardless of width/orientation, and drives platform
  conventions (safe-area insets, back gesture, system font).
- **Render discipline (F1):** subscribe to the width query via the `MediaQueryList`
  **`change` event** (not `resize`), and update a shared store **only when the boolean
  flips**. Platform is computed once at startup. Consumers read via `useSyncExternalStore`
  so they re-render only on a true mode flip. Verify with the **`measure-react-renders`** skill.

### Spike first (the riskiest assumption)

Before building any chrome, prove the reused content renders correctly **mounted outside
`DockingLayout`**:

1. Add `useLayoutMode` + the `WorkspacePage` branch behind it.
2. Stand up a **bare** `MobileWorkspaceShell` (no header/drawer/pill) that mounts the real
   **chat**, then **review-all**, then **terminal** in a plain single-column flex layout.
3. In a narrow Electron/desktop window, confirm each:
   - renders without errors, **sizes correctly** (chat virtualizer + `scrollContainerRef`
     get a valid flex parent), scrolls, and streams;
   - review-all renders the combined **unified** diff in a narrow column (Pierre behaves);
   - terminal renders full-screen.
4. Confirm **no re-render storms** — mode flips once, and mounting outside the docking layout
   doesn't thrash (`measure-react-renders` vs. `origin/main` baseline).
5. Confirm the **scoped sand override** re-themes the reused components.

If any of panel-sizing, scroll containers, Pierre re-theming, or render counts break, that
reshapes the plan **before** chrome is built — which is the whole point of spiking first.

### Build order (after the spike)

1. Foundation: `useLayoutMode` + `WorkspacePage` branch + scoped sand theme on the shell root.
2. Shell skeleton mounting the reused chat (the spike, hardened).
3. Header / context bar; workspace drawer.
4. Changes pill + list → reused review-all overlay; ⋮ dropdown → reused terminal overlay.
5. Mobile chat input (shared submit/draft) + `+` context menu.
6. Agent pager (dots + dashed new-agent) + new-agent compose destination.
7. New-workspace landing page.
8. Reflow Home, Settings, TopBar in place.

## Non-Goals

- **Permissions / approve-reject UI.** Not a product concern for this work — do not design or
  build mobile permission UI. (The reused chat renders whatever it renders; the leftover
  "approve/reject" card in the mock's *Chat components* gallery is **not** part of the agreed
  direction.)
- **Phone delivery / remote access.** No native app, no server/remote plumbing. The mobile UI
  is exercised through a narrow Electron/desktop window.
- **Desktop changes.** Not refactoring or restyling the desktop docking layout (beyond the
  one `WorkspacePage` branch and the in-place reflows).
- **Side-by-side diff on mobile** (unified only).
- **Bottom tab bar**, multi-panel docking, and drag-to-reorder panels on mobile.
- **Re-skinning the chat itself** — chat/tool-call rendering is reused unchanged.
- **Recents / shortcut chrome** on the landing screen.

## Open Questions

1. **Swipe gestures.** The mock implies swiping to switch agents (and maybe views). Is swipe
   in scope for the spike, or **tap-first** with swipe as a follow-up? (Recommend tap-first.)
2. **Review-all gating.** `CombinedDiffView` is behind `isReviewAllEnabledAtom`. Is review-all
   **always-on** for mobile, or does it stay flag-gated?
3. **Sand token remap.** Exactly which Radix/app tokens to override, and whether **Pierre**
   (shadow-DOM diff renderer) inherits the scoped override or needs its own path. (Spike confirms.)
4. **Model & effort placement.** Behind the `+` dropdown directly, or a secondary sheet off it?
5. **"View pull request".** Is the PR URL reliably available on mobile, and does it open
   in-app or in an external browser?
6. **Platform conventions in pass 1.** Safe-area insets are **already resolved** in CSS (see
   Baseline) and need no `useLayoutMode.platform` wiring. The remaining platform signals to
   weigh are **back gesture** and **system font** — wire in pass 1, or defer with the rest of
   the platform plumbing (no phone delivery yet)?
7. **On-screen keyboard.** On a real phone the keyboard resizes the viewport (`visualViewport`)
   — how should the input/stream respond? Likely deferred (no phone delivery yet), but flagged.
8. **Global TopBar on the workspace view.** `PageLayout` renders the global `TopBar` above the
   routed `<Outlet>` **unconditionally**. For the mobile shell's header to *replace* it,
   `PageLayout` needs an `isMobile` (+ Workspace-route) branch that **suppresses `TopBar`**, and
   the mobile header must then take over the `env(safe-area-inset-top)` padding `TopBar` carries
   today (H4). Confirm this is the chosen mechanism. (TopBar reflow per P3 still applies to
   Home/Settings, where `TopBar` stays.)
9. **Routing / back model.** How the drawer and full-screen review-all/terminal overlays map
   onto the hash router, and how their "back" affordance (and the device back gesture) behaves
   — does back close the overlay, or navigate?
