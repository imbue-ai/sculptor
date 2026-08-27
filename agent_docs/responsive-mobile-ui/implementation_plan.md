# Mobile / Responsive Sculptor — Implementation Plan

This plan operationalizes [`spec.md`](spec.md) across **two agents** in this workspace: an
**implementation agent** that builds the feature, and a **QA / polish agent** that verifies it
against the mock afterward. It does not restate the design — it sequences the work, sets
defaults for the spec's open questions, and defines "done".

## Sources of truth

- **What to build:** [`spec.md`](spec.md) (requirements F/S/H/D/C/R/T/M/CH/I/A/L/P/TH, build order).
- **How it must look & behave:** [`mocks.html`](mocks.html) — open in a browser; the **Flows**
  tab is primary. This is the visual source of truth for the QA pass.
- **Design history / rationale:** [`mocks.context.md`](mocks.context.md).
- **Baseline already provided** (do **not** re-implement — see spec → *Baseline*): this work is
  stacked on `bryden/remote-repo-design`, which already ships (a) `origin/main` as the global
  default source branch (no source-branch picker in `AddWorkspacePage`) and (b) iOS safe-area
  insets in CSS (`env(safe-area-inset-*)` in `index.html` + `PageLayout` + `TopBar`).

## Two-agent workflow

1. **Agent 1 — Implementation** (this handoff, model **`opus[1m]`**). Implements the spec
   end-to-end following the phases below, spike first. On completion (build/typecheck/tests
   green + a self-review against `mocks.html`), it **hands off to Agent 2 in this same
   workspace** via `/sculptor-experimental:handoff`, model **`opus[1m]`**, seeding Agent 2 with
   the QA brief below and a short summary of what was implemented + any known gaps.
2. **Agent 2 — QA & polish** (model **`opus[1m]`**). Runs `/auto-qa-changes` to drive the app in
   a headless browser at a narrow (~390 px) viewport, walks every flow in the spec's *User
   Scenarios*, compares the rendered UI to `mocks.html`, and fixes polish gaps (spacing, color,
   type, icons, theme tokens, safe-area, touch targets) until it matches. Then re-verifies and
   reports with screenshots.

## Defaults for the spec's Open Questions (so Agent 1 is unblocked)

Agent 1 should proceed with these unless it discovers a reason to revisit (then ask the user):

1. **Swipe gestures →** tap-first. Pager dots + the dashed new-agent dot are tappable; swipe is a
   follow-up, out of scope for this pass.
2. **Review-all gating →** treat review-all as **always-on inside the mobile shell** (don't make
   mobile depend on the desktop `isReviewAllEnabledAtom` flag); verify `CombinedDiffView` renders
   unified in a narrow column during the spike.
3. **Sand token remap →** resolved by the spike: remap the **Radix/app token names the reused
   components actually read**, scoped to the shell root class. Confirm Pierre (shadow-DOM diff)
   re-themes; if it doesn't inherit, give it its own scoped path.
4. **Model & effort placement →** behind the `+` dropdown (per I3). A secondary sheet is a later
   refinement, not this pass.
5. **"View pull request" →** show the item only when a PR URL is available; open it externally.
   Low priority — fine to stub/hide if the URL isn't reliably present.
6. **Platform conventions →** safe-area is already handled in CSS (Baseline); **defer** back
   gesture and system font.
7. **On-screen keyboard (`visualViewport`) →** deferred (no phone delivery yet).
8. **Global TopBar →** add an `isMobile` (+ Workspace-route) branch in `PageLayout` that
   **suppresses the global `TopBar`** for the mobile Workspace view; the mobile header owns the
   `env(safe-area-inset-top)` padding. `TopBar` stays (and reflows per P3) on Home/Settings.
9. **Routing / back →** keep overlays (drawer, review-all, terminal) as **in-shell state** for
   this pass; "back" closes the overlay (it does not navigate the router). Deeper hash-router
   integration is a follow-up.

## Implementation phases (Agent 1)

Follow the spec's build order. **Spike before chrome** — the riskiest assumption is that the
reused content renders correctly outside `DockingLayout`.

- **Phase 0 — Spike (de-risk).** Add `useLayoutMode` (matchMedia `@768px`, re-render only on the
  boolean flip via `useSyncExternalStore`) + the single `WorkspacePage` branch. Stand up a
  **bare** `MobileWorkspaceShell` (no chrome) that mounts the real **chat**, then **review-all**,
  then **terminal** in a plain single-column flex. In a ~390 px window confirm: each renders,
  **sizes** correctly (chat virtualizer gets a `min-height:0` flex parent), scrolls/streams;
  review-all renders **unified** narrow; terminal renders full-screen; **no re-render storms**
  (`measure-react-renders` vs `origin/main`); the **scoped sand override** re-themes the reused
  components (esp. Pierre). If any of sizing / scroll / Pierre / render-counts break, adjust the
  plan before building chrome.
- **Phase 1 — Foundation.** Harden `useLayoutMode` (expose `mode`/`isMobile`/`platform`/`isTouch`)
  + the `WorkspacePage` branch (F1–F4) + the scoped **sand** token override on the shell root
  (TH1/TH2). Verify desktop is untouched and panel-layout persistence is not corrupted (F3).
- **Phase 2 — Shell skeleton.** `MobileWorkspaceShell` mounting the reused chat in the real
  single-column layout (S1–S5); suppress the global `TopBar` for this view (Open Q8).
- **Phase 3 — Header + drawer.** `MobileWorkspaceHeader` (H1–H4, owns the top safe-area inset) and
  `WorkspaceDrawer` (D1–D6: grouped-by-repo, collapsible, pinned New-workspace button, empty state).
- **Phase 4 — Changes + review-all + terminal.** `ChangesPill` (C1–C3, floating list overlaying
  chat) → reused review-all overlay (R1–R5, unified); the **⋮** Radix dropdown (M1) → reused
  terminal overlay (T1–T2).
- **Phase 5 — Mobile chat input.** `MobileChatInput` (I1–I4) sharing `ChatInput`'s submit/draft
  core (`usePromptDraft`, send/interrupt, model/fast/effort atoms — extract the core, don't
  duplicate) + the `+` context menu (M2).
- **Phase 6 — Agent pager.** `AgentPager` (A1–A3): centered dots + dashed new-agent circle;
  tapping a dot switches agent; the dashed dot lands on the empty-agent compose destination (CH2).
- **Phase 7 — New-workspace landing.** `MobileNewWorkspace` (L1–L4): name-only, tappable
  `repo · origin/main` meta line; **shares `AddWorkspacePage`'s create-workspace submit core**
  (`createWorkspaceV2` + `createWorkspaceAgent` + `navigateToAgent`; `useDraftTabName`) — already
  defaults `origin/main`; drops the new-branch field and gated harness/mode selectors.
- **Phase 8 — Reflow simple pages in place** (`isMobile`/CSS): Home single column (P1), Settings
  keeps its `.mobileNav` 825 px container-query pattern (P2), TopBar collapses workspace tabs into
  a menu where it's still shown (P3).

**Per-phase discipline:** keep the desktop path untouched (F2/F3); reuse content leaves
unchanged (CH1); use design tokens (`frontend-design-tokens` skill) — no hard-coded colors;
`just generate-api` if `ElementIds`/backend models change.

## Pre-handoff checklist (Agent 1 → Agent 2)

- [ ] `just format`, `just check`, `just test-unit` all green.
- [ ] `just generate-api` run if any `ElementIds`/backend models changed.
- [ ] `measure-react-renders` confirms **no desktop render-count regression** and no mobile storms.
- [ ] Self-review every *User Scenario* (1–7) against `mocks.html` at ~390 px.
- [ ] Commit on this branch; write a short **"what's implemented + known gaps"** note in the
      Agent 2 handoff seed.

## QA & polish phase (Agent 2)

**Goal:** the running app at ~390 px matches `mocks.html` in behavior *and* polish.

**How:** `/auto-qa-changes` (headless browser + screenshots). Mind the harness quirks: there are
**edge-click dead zones**, verify toggled UI via **hot-reload**, and **the harness has no LLM
key** — so verify chat/tool rendering against seeded/existing conversation state (or FakeClaude),
not live streaming.

**Walk each flow** (spec *User Scenarios* 1–7 / mock **Flows** tab): land→create workspace;
monitor chat; drawer switch (Flow A); changes pill → review-all (Flow B); terminal (Flow C);
agent pager switch + new-agent; empty states.

**Polish checklist vs the mock** — fix where they diverge:

- **Theme/color:** sand bg `#FAE8CA`, accent `#F50D00`, supporting surface/ink/diff tokens; reused
  chat/review-all/terminal are re-themed (no dark-theme bleed-through, esp. Pierre diff). Tokens,
  not hard-coded values.
- **Typography:** Inter (UI), JetBrains Mono (code); sizes/weights match the mock; no invisible
  text falling back to a dark host color on sand.
- **Icons:** real Lucide, **circled** variants — `square-menu` (☰), `circle-ellipsis` (⋮),
  `circle-chevron-left` (back), `circle-plus` (`+`); correct sizes.
- **Spacing & chrome:** seamless header/status-bar (no seam), border under the header, no border
  above the pager dots, centered pager dots + dashed new-agent circle, rounded floating input, no
  horizontal overflow down to ~390 px (S4).
- **Touch targets:** ~44 px hit areas (S5); safe-area insets honored (header top, shell bottom).
- **Overlays:** drawer dims the backdrop; ⋮ / `+` are anchored dropdowns with **no dim**
  (transparent click-catcher); review-all/terminal are full-screen with a working back.
- **Desktop regression:** confirm ≥768 px is visually and behaviorally unchanged.

**Then:** fix gaps, re-run `/auto-qa-changes`, and report with before/after screenshots + a list
of anything intentionally deferred.

## Done

- All spec requirements implemented; desktop unchanged (F2/F3).
- Every flow verified at ~390 px and matching `mocks.html` polish.
- Checks green; render counts clean; screenshots captured.
