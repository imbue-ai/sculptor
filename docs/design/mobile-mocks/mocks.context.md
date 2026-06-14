# Sculptor Mobile / Responsive — Mock Context

## Description

Interactive HTML mocks for making Sculptor responsive / mobile-friendly. The
goal is to iterate on the **visual design** before any production React is
written (a sibling agent owns the implementation spec).

Pre-decided constraints these mocks target (not up for relitigation here):

- **Trigger:** viewport width only — "mobile" is just a narrow window
  (≈390px). No phone-browser / remote plumbing.
- **Breakpoint:** mobile = width < 768px (Radix `sm`); desktop = ≥ 768px.
- **Mobile feature set ("monitor + chat"):** list workspaces/agents, read the
  chat stream, send prompts, approve/reject pending actions, glance at the
  diff/changes. **Deferred on mobile:** terminal, the multi-panel docking
  layout, side-by-side diff.
- **Strategy (hybrid):** shared responsive primitives + CSS reflow for the
  simple pages, plus a **distinct single-column shell** for the dense
  Workspace view (do not squeeze the desktop docking layout onto mobile).

Visual language is matched to the real app: dark theme, Radix gray scale
(`#111113`→`#eeeef0`), indigo/blue accent (`#3d63dd`), Inter for UI / JetBrains
Mono for code, compact spacing.

## What's mocked

**Headline (exploration — 3 variants of the mobile Workspace shell):**

- **Variant A — Bottom tab bar.** Native iOS/Android pattern. Fixed bottom tab
  bar (Chat · Changes); compact top context bar with back + agent switcher;
  chat input pinned above the tab bar; agent switcher as a bottom sheet.
- **Variant B — Header segmented control.** No bottom bar. View switch lives in
  the header as a Radix `SegmentedControl` (Chat / Changes), reusing an
  existing app primitive; agent switcher is a dropdown off the title; the chat
  input owns the full bottom edge (maximizes vertical content).
- **Variant C — Left drawer + push navigation.** App-shell model: a hamburger
  opens a left drawer listing all workspaces & agents (mirrors the desktop
  sidebar); Changes is reached by pushing a full-screen view (stack
  navigation) from a header pill rather than a persistent tab; a pending action
  surfaces as a sticky banner above the input.

Each variant shows the full arc: chat stream (user msg, assistant markdown,
tool-call result, inline pending approve/reject), the Changes file list, and a
full-screen unified diff.

**Reflowed simple pages (confirmation):** Home (recent workspaces), Settings
(left-nav → top dropdown + full-width content), Add-Workspace form, and the
TopBar (workspace tabs collapse into a menu/drawer).

## Decisions

Settled constraints the mocks adhere to (pre-decided going in, not re-litigated):

- Single-column **distinct shell** for the Workspace view on mobile; desktop
  docking layout is not squeezed onto mobile.
- One view at a time: **Chat** (default) and **Changes/Diff**.
- Chat stream renders, inline, all of: user message, assistant markdown,
  tool-call result, and a pending **approve/reject** prompt.
- Changes = file list → tapping a file opens a **full-screen unified diff**
  (side-by-side deferred).
- Compact top context bar with a back affordance + an **agent switcher**.
- Deferred on mobile: terminal, multi-panel docking, side-by-side diff.
- Visual language matched to the real app (dark Radix gray + indigo accent,
  Inter / JetBrains Mono, compact spacing).

**Still open (not yet chosen):** which of the three shell variants (A bottom
tabs / B header segmented / C drawer + push) becomes the primary direction, and
whether to blend elements across them. Session was paused before a direction
was locked — all three remain live in `index.html` for a later pass.

### Round 2 direction (sand theme + Claude-mobile vibe)

New direction the user chose after round 1, driven by reference screenshots in
`agent_docs/responsive-mobile-ui/claude_and_github_mobile_screenshots/`:

- **Aesthetic:** match the **Claude mobile** vibe — warm paper surfaces, serif
  body text, quiet gray collapsible tool/status lines, a coral/red "working"
  asterisk, soft rounded user bubbles, a large floating rounded input with a
  `</> Code` pill + circular send, inline `Diff +3` / `View PR` action chips.
  Diff / review language borrows from **GitHub mobile**.
- **Light theme palette (user-specified):** background/gray `#F5D6A0` (warm
  sand), accent `#F50D00` (vivid red).
- **Workspaces drawer:** keep simple for now.
- **Workspace page is the focus.** Ideas to explore (each gets variants):
  - Easy way to create a new agent in a workspace — ideally via **swipe**
    left/right; swipe might also move between views (chat / changes / terminal).
  - Where to surface **agent counts** (open question — several variants).
  - Show **changes as a drawer off the top bar** — when there are changes,
    reveal a workspace-header-like summary.
  - Tapping the **agent name** could switch between agents.
  - **Review-all** panel is likely the best way to view changes.
  - Surface the **terminal** somewhere for the workspace.
  - A **⋮ (triple-dot) menu** that quickly jumps to terminal / review-all.
- **Deliverable shape:** break the UI into components and produce *many*
  variants per component, plus assembled flows.

## Rejected Alternatives

(none yet — no variant or tweak has been ruled out)

## Tweaks Log

- Initial generation: built 3 workspace-shell variants (A bottom tab bar, B
  header segmented control, C left drawer + push navigation) plus 4 reflowed
  pages (Home, Settings, Add-Workspace, TopBar) in
  `docs/design/mobile-mocks/index.html`. No tweaks requested yet.
- Round 3 (new doc, polish reset): user found the round-2 component views (esp.
  header/agents) hard to read and the polish lacking; said to work mainly from
  **assembled flows** and that only Foundations + Chat earned a component view.
  New file `docs/design/mobile-mocks/round-3-sand.html`:
  - **Real Lucide icons** via `<script src="https://unpkg.com/lucide@latest">`
    + `data-lucide` + `lucide.createIcons()` (hand-drawn SVGs looked off).
  - Pages: **Flows** (primary), **Foundations**, **Chat components**.
  - **Drawer:** D1 only.
  - **Header:** based on H2 but agents switch via **pager dots** under the
    header (no dropdown); ☰ opens the workspaces drawer; **⋮** is the jump menu
    (terminal / review-all / PR / new agent / rename / settings).
  - **Changes:** a small chip under the header that **expands down** to the full
    file list, with a **Review all** button → review-all (RV1); back returns to
    chat.
  - **Terminal:** T1 full-screen, reached from the **⋮** menu.
  - **Flows:** assume an in-progress chat; interactive Home frame + step-by-step
    sequences for (A) open drawer, (B) view changes → review-all, (C) open
    terminal, plus pager-dot agent switching.
  Round 2 retained for its component variants; round 1 retained too.
- Round 3.1 (polish pass on round-3-sand.html): header background now matches the
  status-bar/notch region (uniform, no seam); removed the border above the agent
  pager dots; chat input bottom-left is now a single **circle-plus** that opens
  the context menu (dropped the `</> Code` pill, paperclip, mic); drawer
  workspaces are **grouped by repo and collapsible** (replaced "Recent"), with a
  **full-width** New-workspace button; removed the slightly-red selected-row tint
  (now neutral `--press`); dropped the **Finish review** button; smaller header
  icons; switched to circled Lucide variants per request (**square-menu** ☰,
  **circle-ellipsis** ⋮, **circle-chevron-left** back, **circle-plus**); terminal
  lost the window "traffic-light" dots and its dark header (header stays light;
  terminal body stays dark). NOTE: user will share a Sculptor UI-update branch to
  align direction — revisit when it arrives.
- Round 3.2: moved the **agent switcher (pager dots) from the top bar to under the
  chat input**, and added a **new-agent icon** (`user-plus`) beside the dots;
  fixed the **terminal text** (mono `white-space:pre`, tighter sizing, no wrap);
  converted the **⋮ jump menu from a bottom sheet to an anchored dropdown**
  (top-right). The chat input `+` now opens its own small dropdown (Mention /
  Skills & commands / Attach / Image) as the "context menu". Header keeps the
  agent name in the subtitle; switching happens at the bottom dots.
- Round 3.3: the **new-agent affordance is now an outlined circle** at the end of
  the agent pager dots (swipe to it to create an agent) — dropped the separate
  `user-plus` icon button. Switched the typeface from the serif to **Inter**
  (Sculptor's UI font; JetBrains Mono for code), loaded via Google Fonts.
  Restored the **border under the workspace header**.
- Round 3.4: fixed an inheritance bug where uncolored phone text (e.g. the chip's
  "· 5 files") fell back to the dark host-page color and was nearly invisible on
  sand — added a base `color:var(--ink)` to `.theme-sand` and an explicit color on
  the chip stat. Made the **new-agent swipe nicer**: the trailing pager dot is now
  an outlined circle with a faint **+** (and an accent active state), and added a
  **"Start a new agent" compose destination** frame to the Agents flow (dashed +
  circle, accent-bordered prompt) so swiping past the last agent reads clearly.
- Round 3.5: reworked the bottom agent switcher per request — **dots are now
  left-aligned** with a **"＋ New agent" button on the right** (space-between),
  replacing the trailing outlined-+ dot. The New-agent button opens the compose
  destination (shown active in the Agents flow's compose frame).
- Round 3.6: reverted the switcher to **centered dots** (left-align disliked) and
  made the new-agent indicator the **dashed outline circle** from round-2's NA1
  (dropped the right-side button). NOTE: permissions/approve-reject are out of
  scope for this product — don't mock them.
- Round 3.7: added the **Landing / New-workspace screen** (the default screen;
  landing == create-workspace, per user + reference shot
  `IMG_4BE8890A65B4-1.jpeg`). The desktop version wastes most of the screen; the
  mobile redraw uses the sand theme and full width: header (☰ · Sculptor · search),
  "New workspace" hero, a full-width create card (name · branch · repo) + a
  full-width Create button, and a **Recent workspaces** list below so the default
  screen doubles as home. It's the first section in the Flows tab. Next-flow
  shortlist still open: finish→PR (#3), single-file diff (#4), create→working.
- Round 3.8: **redesigned the create/landing screen to be minimal** — the only
  real input is the **workspace name** (dropped "optional"); branch is always
  **origin/main** and repo are shown as a subtle meta line; removed the recents
  list and the keyboard-shortcut hint. Added **two empty states**: the
  **workspaces drawer with no workspaces** ("No workspaces yet" + New workspace),
  and an **agent with no messages** using Sculptor's real intro copy ("Branched
  off origin/main from sculptor…", "This is agent X in workspace Y", "All agents
  in this workspace share the same code…", "Type /sculptor:help to ask a
  question") with the actual "Enter a prompt…" placeholder.
- Round 3.9 (consistency cleanup): every flow now renders the **full Home screen**
  with the relevant overlay on top instead of a stripped teaser — Flow A (Home →
  Home+drawer), Flow B step 2 (the expanded changes now **overlay** the chat as a
  floating dropdown, input retained), Flow C (Home + ⋮ **dropdown**, input
  retained). The ⋮ menu is a **standard radix dropdown under the icon with no dim
  backdrop** (dropdowns use a transparent click-catcher; drawer/sheets keep the
  dim). The new-agent destination now matches the **empty-agent** screen. Unified
  **all phones to one size** (the empty flow had mixed 340/380).
- Round 2.1 (meta tweaks): (1) lighter background — kept the sand hue/saturation
  (HSL 38°, 81%) and raised lightness: `#F5D6A0` → `#FAE8CA`. (2) Replaced the
  hand-drawn icons with accurate **Lucide** path data (icons looked scuffed);
  added `code-xml` for the `</>` mode pill, `grip`, `file-diff`. (3) Made the
  changes drawer **rounded, capped, floating** (never full screen), opened by a
  **little changes icon** (with count badge) in the header. (4) Added a
  discoverable **bottom-sheet peek** affordance (grab handle + label + ⌃) for
  both Terminal and Changes, answering "how do people know to drag it up?"; both
  can **expand up to the top bar** (new F6 flow + Terminal T3). Swipe model and
  CH/agent-count choices left open pending user reaction.
- Round 2 (earlier): user supplied Claude/GitHub mobile reference shots, a
  sand+red light theme, and a set of workspace-page ideas (swipe to switch
  agents/views, new-agent creation, changes-as-header-drawer, agent counts,
  review-all, terminal, ⋮ menu). Built a component-variant gallery + assembled
  flows in a new file `docs/design/mobile-mocks/round-2-sand.html` (kept
  separate from round 1 because the theme is distinct; `index.html` links to
  it). Round 1 retained as historical record.
