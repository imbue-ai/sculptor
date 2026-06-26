# Mobile polish gap ledger (Phase A triage)

Captured by driving the `auto-qa-changes` harness at a **390px** viewport against
`maciek/scu-1618-mobile-ui`. Screenshots live in the workspace `attachments/screenshots/`.

**Standing context — NOT gaps:** the "sand" palette (#FAE8CA/#F50D00) was deliberately
dropped; the mobile chrome tracks the app's normal light/dark theme. The `spec.md`
TH1/TH2 sand requirements are stale — ignore them. Color/contrast gaps below are
within the normal theme.

Tiers: **1** = functionality/clearly-wrong · **2** = visual correctness · **3** = polish.

---

## Surface A — New-workspace landing (`MobileNewWorkspace.tsx` / `.module.scss`)
Screenshot: `0003_get.png`

- **A1 (T2) ❌ NOT REPRODUCIBLE** — all three pills already use the same border: `RepoSelector` (Repo) renders `Select.Trigger variant="ghost"`, `BranchSelectorCore` (Source) gets `triggerVariant="ghost"`, and Branch is a custom `.pill` div — all share `.pill/.pillTrigger { border: 1.5px solid var(--mobile-line) }`. No Radix surface box overriding it. Any perceived difference is very subtle (opaque `.pill` bg vs transparent ghost trigger), not a border bug.
- **A2 (T2)** Pill content asymmetric across the 3 rows: Source has a "source" label, Repo doesn't; right-edge affordance differs (chevron vs. shuffle/regenerate vs. chevron). Unify.
- **A3 (T3)** Large dead band above the title — centered group sits low; vertical balance feels lopsided/"jammed at top".
- **A4 (T2)** Pill surfaces don't lift above the page base — both near-identical dark tone; the intended `--gray-2` page / `--gray-3` control contrast isn't visible.
- **A5 (T3)** "Untitled workspace" placeholder is the largest, dimmest element — can read as a disabled/empty state rather than an editable title.
- **A6 (T3)** Create button is indigo/blue (matches the desktop modal) — confirm intentional vs. the rest of the mobile accent language.
- **Clean:** header layout + 44px targets, bottom-pinned safe-area Create button, no overflow/clip, correct Lucide icons.

## Surface B — Chat shell, empty state (`MobileWorkspaceShell` / `MobileWorkspaceHeader` / reused `AlphaChatInterface` / `ChatInput` mobile toolbar)
Screenshot: `0011_get.png`

- **B1 (T1) ✅ DONE** — Chat stream top **clipped under the status row**. Fixed: made `.statusRow` an in-flow flex row (was `position:absolute` overlay) so the reused chat (`.container`, `flex:1`) starts below it. Validated; no clipping, chat still fills.
- **B2 (T2) ✅ DONE** — same root cause as B1 (the floating pill row overlapped the intro); fixed by the same change.
- **B3 (T1/T2) ❌ FALSE POSITIVE** — the pager-dots design (spec A1) was DELETED in fc15efd and replaced by the `AgentSwitcher` pill (the "Claude 1 ▾") + `AgentSheet` bottom sheet for switch/create. Spec A1 is stale. Agent switching works via the pill→sheet; no dots by design.
- **B4 (T2)** Header **subtitle missing** — H2 wants `agent · repo` subtitle + status dot under the workspace-name title; only the title shows.
- **B5 (T3)** Header icons aren't the circled Lucide variants (`square-menu`, `circle-ellipsis`); right icon is plain `•••`.
- **B6 (T2)** Large empty dead band mid-screen — intro hugs top, input pinned bottom, ~50% empty/unbalanced.
- **B7 (T3)** Send button is dim grey-on-grey — reads as disabled in the composable empty state; low contrast.
- **B8 (T3)** Toolbar shows a bare `+` (not `circle-plus`) plus a separate always-visible sliders/settings control — spec I3 wanted model/effort hidden behind the `+`.
- **Clean:** real `AlphaChatIntro` empty state (not a void), no horizontal overflow.

## Surface C — Workspaces drawer (`WorkspaceDrawer.tsx` / `.module.scss`)
Screenshot: `0016_get.png`

- **C1 (T1) ✅ DONE** — **Backdrop dim too weak**. Fixed: `--mobile-overlay` bumped `--color-overlay`→`--black-a9` (stronger scrim across all mobile backdrops) + drawer `box-shadow: var(--mobile-shadow)`. Validated via harness.
- **C2 (T1) ❌ FALSE POSITIVE** — `imbue/tiny-viper` IS the generated workspace branch name (Sculptor names branches `imbue/<animal>`), not a repo slug. The drawer correctly shows the branch (same value the landing's Branch pill shows). No change.
- **C3 (T2)** Repo-group chevron + folder icons are very low-contrast (`--mobile-ink-3`) — disclosure affordance hard to see.
- **C4 (T2)** No divider/section heading between Home/Settings nav rows and the workspace list (D2 "Workspaces" concept).
- **C5 (T2)** New-workspace CTA is inverted ink-on-surface (near-white) — confirm intentional vs. using the app accent.
- **C6 (T3)** Single-repo group is chrome-heavy (header + count "1" + indented row for one item); faint status dot; muted avatar.
- **Clean:** drawer slide/width, pinned bottom CTA, safe-area insets, 44px+ hit areas, ellipsis overflow, empty-state markup.

---

## Surface D — AgentSheet (`AgentSheet.tsx` / `.module.scss`)
Screenshot: `0043_get.png` (bottom sheet, opened from the agent switcher pill — this is the B3 "pager" replacement; it works)

- **D1 (T2) ~PARTIAL** — added `box-shadow: var(--mobile-shadow)` to the sheet (light-theme elevation + consistency with the drawer). Validation showed the shadow is invisible in DARK theme (dark shadow over near-black). Dark-theme top-edge separation is still subtle → see **X2** (cross-cutting).
- **D2 (T2) — likely harness-only** — the "New agent" row looked flush at the bottom, but `.sheet` already has `padding-bottom: calc(--space-3 + env(safe-area-inset-bottom))`; the harness reports 0 safe-area, so on a real phone the home-indicator inset adds the breathing room. Deferred (re-check on device).
- **D3 (T3) ✅ DONE** — sheet title bumped `--mobile-ink-3`→`--mobile-ink-2` so it reads as a heading, not a subline.
- **D4 (T3)** Large empty gap between the single agent row and the separator/New-agent block (under-filled with one agent).
- **D5 (T3) ✅ DONE** — tightened the agent row's dot-to-name gap `--space-3`→`--space-2` so the status dot reads as attached to the name.
- **D6 (T3)** Grabber handle is faint (`--mobile-line` over a near-equal surface).
- **Clean:** proper bottom sheet w/ grabber + rounded top, current agent checked w/ status dot, clear `+` New agent affordance.

## Surface E — Home page reflow (`HomePage.tsx/.scss`, `MobileHomeHeader.tsx`, shared `WorkspaceRow`)
Screenshot: `0048_get.png`. Header is clean (replaces TopBar, centered title, safe-area).

- **E1 (T1)** No new-workspace CTA on Home itself — the only "+ New workspace" is pinned in the drawer (behind the hamburger). The most-expected Home action has no visible affordance. Add a visible button/FAB.
- **E2 (T1) [DESKTOP-REACHING]** `WorkspaceRow` touch target <44px (`min-height:24px` + `--space-3` ≈ 40px). Shared component → fix in the desktop-reaching cluster (or a mobile row variant).
- **E3 (T2) [DESKTOP-REACHING]** `WorkspaceRow` delete button + repo column are **hover-gated** (`opacity:0` until `:hover`) → permanently invisible/unreachable on touch; the repo column still reserves 80px dead width. The row was reused, not reflowed for mobile.
- **E4 (T2) [DESKTOP-REACHING]** Row metadata is desktop-shaped (fixed `.time 60px` / `.repo 80px`), wasteful at 390px — big empty gap between name and "1h ago".
- **E5 (T3)** Sparse one-item body: ~80% empty void, no anchor/CTA (EmptyState only renders at zero items).
- **E6 (T3)** Search bar sits flush under the header — a little more top breathing room would help.

> **NEW CLUSTER — "WorkspaceRow mobile reflow" (desktop-reaching):** E2/E3/E4 share a root cause (the shared `WorkspaceRow` isn't mobile-aware). Handle on the desktop-reaching branch — either a mobile-specific row or an `isMobile` branch in `WorkspaceRow`.

## Surface F — Settings page (`SettingsPage.tsx`, `MobileSettingsHeader.tsx`)
Screenshot: `0052_get.png`. Header/back, nav-as-dropdown collapse, and theme segmented control render correctly.

- **F1 (T1)** "Software Updates" row: the `N/A ▾` channel select + disabled "Check for updates" button sit side-by-side (`gap="2"`, never wraps at 390px), an awkward two-tier layout. On mobile they should stack / go full-width. (`SettingRow.module.scss` `.controlRow` flex-wrap — gate on mobile.)
- **F2 (T2)** Nav `Select.Trigger` is full-width with label left + chevron far-right and a big empty gap between — reads like a stretched input, not a nav control. Constrain width / center.
- **F3 (T2)** Large vertical void (~65px) between the nav dropdown and the section description (`.mobileNav pt=5` + section `mt/mb` stack).
- **F4 (T2)** Inconsistent horizontal gutters — nav dropdown `px=5` doesn't align with the section content's left edge. Share a gutter.
- **F5 (T3)** Theme segmented control off-state (`--gray-11`) is dim vs the selected item.
- **F6 (T3)** `N/A ▾` select trigger ~32px tall (<44px touch target); same trigger is used for enabled selects elsewhere.
- **Clean:** no overflow/clip, back chevron 44px, centered title.

## Behavioral (from code analysis — not visible in stills)

- **BE1 (T1, perf) ~PARTIAL** — TipTap typing lag. Root cause confirmed by reading the code: every keystroke writes `promptDraftAtomFamily`, and `ChatInput` subscribes via `useAtom(promptDraft)` → the WHOLE `ChatInput` tree re-renders per keystroke (+ the editor's value-sync re-serializes via `getMarkdown()` a 2nd time).
  - DONE (safe, desktop): memoized `ModelSelector` + `EffortSelector` (`React.memo`; their props are atom-backed/`useCallback`-stable) so they bail out of the per-keystroke re-render. NOTE: on MOBILE these aren't even rendered (the toolbar is a lazy Radix `DropdownMenu`), so the mobile toolbar is already light — the memos help DESKTOP typing, not the reported mobile lag.
  - ✅ DONE (the real mobile fix): **decoupled the draft from `ChatInput`'s render** — `useSetAtom` + `useStore` (no per-keystroke subscription); a `draftFlags` (`hasContent`/`isBypass`) bailout state for the send-button; send/interrupt/append read the live draft via `getDraft()` (`store.get`); `appendText` pushes content imperatively; a task-switch effect re-syncs flags. Typing is now pure ProseMirror, no React re-render. VALIDATED in the mobile harness: type→register, send (live draft)→clears, button enable/disable, draft restore across navigation. (Untested-but-reasoned: `/clear`, `/btw` bypass, multi-agent isolation, mention-hydrate — user to confirm on device.)
  - Gotcha learned: Fast Refresh chokes on a function→`memo` HOC change (shows `TypeError: Component is not a function`); a full reload clears it — always reload-test memo/HOC edits in the harness.
- **BE2 (T1)** Chat autoscroll "snaps to bottom too early" — the reused virtualizer/autoscroll running in the mobile flex container rather than its docked parent. Needs investigation in `useAlphaAutoScroll` against the mobile shell layout.

## Cross-cutting

- **X1** Mobile components (except `MobileNewWorkspace`) lack `data-testid`/`ElementIds` — blocks the e2e suite AND made this QA harder (had to click by coordinates). Adding them is a prerequisite for Phase C automated verification.
- **X2 (elevation in dark theme)** Drop-shadows are invisible over near-black, so mobile overlays (drawer, sheet) don't separate from a dimmed dark chat via shadow alone. The drawer is OK now because the strengthened scrim dims its background; the bottom sheet's top edge over the dimmed chat is still subtle. Wants a holistic treatment for all mobile overlays in dark theme (e.g. a brighter top hairline and/or a lifted surface), not per-surface hacks. Lower priority; needs a small design call.

## Not yet captured (follow-up pass)
Home reflow, Settings reflow, the `+` / settings dropdown menus open, agent switcher/sheet,
changes-pill → review-all overlay, terminal overlay. The last three need agent-generated
state (a real task producing a diff / terminal), so they're slower to reach.
