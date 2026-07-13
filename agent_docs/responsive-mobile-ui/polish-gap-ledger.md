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
- **E3 (T2) ✅ DONE (pending device confirm)** — `WorkspaceRow` delete button + repo column were **hover-gated** (`opacity:0` until `:hover`) → unreachable on touch. Fix: a `@media (hover: none), (pointer: coarse)` block in `WorkspaceRow.module.scss` reveals `.repo` + `.deleteButton`, and the same block in `ClosedWorkspaceRow.module.scss` reveals its `.actions` cluster (which was double-gated with `visibility:hidden`). Pure-CSS, fires ONLY when the pointer can't hover → desktop untouched at any window width. USER to confirm on device (Home recent list + closed-workspaces list: delete/action affordances visible without hover). The repo column's 80px reserved width is folded into E4.
- **E4 (T2) [DESKTOP-REACHING]** Row metadata is desktop-shaped (fixed `.time 60px` / `.repo 80px`), wasteful at 390px — big empty gap between name and "1h ago". (E3's CSS now makes the 80px repo column always-visible on touch; whether to instead reflow/collapse it stays open here.)
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
  - REGRESSION found + fixed (`8043761`): the decouple broke EXTERNAL writes to the draft atom (QueuedMessages undo-overwrite restoring a clobbered draft no longer reached the editor). Fixed with a manual `store.sub` that pushes external writes into the editor imperatively; self-writes skipped via a last-emitted ref (no per-keystroke serialize).
  - RESIDUAL lag ✅ DONE: the per-keystroke `editor.getMarkdown()` serialization in `Editor.onUpdate` was the remaining synchronous per-keystroke work (O(doc), worst with IME). Added an opt-in `Editor.changeDebounceMs` (coalesces serialize+onChange on a trailing timer; flushed on blur + unmount); ChatInput passes 150ms on mobile / 0 on desktop. To run the editor uncontrolled during typing: ChatInput's editor `value` is a STABLE per-task initial (external writes arrive via the store.sub), `getDraft()` reads the LIVE editor so send has the full text, and sendMessage clears via `clearEditor()` (imperative). VALIDATED in harness: full text sends, input clears on send, flush-on-blur draft persistence works. Tradeoff: send button enables ~150ms after typing starts. USER to confirm typing-smoothness on device.
- **BE2 (T1) ✅ DONE (pending device confirm)** — Chat autoscroll "snaps to bottom too early". Root cause: `useAlphaAutoScroll`'s `BOTTOM_THRESHOLD` (200px) — on a short mobile viewport that's ~¼ of the screen, so pin-to-bottom re-engages well before the actual bottom. Fix: use a tighter threshold (80px) when the scroll container's `clientHeight < 700` (layout-driven, no mobile flag; desktop unchanged at 200). The 80px/700px values are first guesses — USER to confirm the snap point feels right on device (harness can't feel scroll); tune if needed.

## Mobile browser / keyboard (user-reported on real Firefox Android)

- **KB1 (T1) ✅ DONE** — Switching agents auto-focused the chat input → popped the virtual keyboard → relayout just from checking on an agent. The reused `Editor` defaults `autoFocus=true` and remounts per agent (keyed by taskID). Fixed: `ChatInput` passes `autoFocus={!isMobile}` so mobile only focuses on tap; desktop keeps autofocus. (Verify on device.)
- **KB2 (T1) ✅ DONE** — Mobile browser chrome (address bar) obscured the bottom of the chat input. `--app-height` (and `body`) used `100vh`, which is the chrome-HIDDEN height, so the app overflowed the visible area. Switched to `100dvh` (dynamic viewport, chrome-aware; `vh` fallback retained; `dvh==vh` on desktop/Electron). (Verify on device.)

## Cross-cutting

- **X1** Mobile components (except `MobileNewWorkspace`) lack `data-testid`/`ElementIds` — blocks the e2e suite AND made this QA harder (had to click by coordinates). Adding them is a prerequisite for Phase C automated verification.
- **X2 (elevation in dark theme)** Drop-shadows are invisible over near-black, so mobile overlays (drawer, sheet) don't separate from a dimmed dark chat via shadow alone. The drawer is OK now because the strengthened scrim dims its background; the bottom sheet's top edge over the dimmed chat is still subtle. Wants a holistic treatment for all mobile overlays in dark theme (e.g. a brighter top hairline and/or a lifted surface), not per-surface hacks. Lower priority; needs a small design call.

## Not yet captured (follow-up pass)
Home reflow, Settings reflow, the `+` / settings dropdown menus open, agent switcher/sheet,
changes-pill → review-all overlay, terminal overlay. The last three need agent-generated
state (a real task producing a diff / terminal), so they're slower to reach.

## Round 2 — device-reported issues (2026-06-26, real Firefox Android)

- **R2-S1 (Settings column squeeze) ✅ DONE (`50f36cf`, pending device confirm)** — In Settings, the Repo row ("Remove repo & agents" button + Configure link) and each Panels row (zone Select + hotkey chip + Switch) keep a wide control cluster in the same `justify-content: space-between` row as the label, so on a narrow screen the controls don't shrink and the repo name/path + panel title/description get crammed into a cramped, badly-wrapping column. Fix: below 768px (or coarse pointer) stack the controls under the label — `RepoRow.module.scss` media query on `.repoRowHeader`; `PanelsSettingsSection.tsx` via Radix responsive `direction`/`align` props. Desktop unchanged.
- **R2-S1b (other squeeze candidates — FOUND, not yet fixed)** — Same `space-between` + non-shrinking-right-cluster pattern flagged elsewhere by recon; NOT all are real (several already have `flex:1; min-width:0`). Worth a device look before touching: `KeyboardShortcutsDialog` `.shortcutRow` (label vs badge); `SkillList` `.emptyRow` (both sides `nowrap`); `ActionGroupSection` `.groupNameField` (has `flex:1`, missing `min-width:0`); `SettingRow` `.control` (`flex-shrink:0`, relies on `flex-wrap`); `MobileNewWorkspace` `.pillValue` (`nowrap`, no `min-width:0` on container); `WorkspaceDrawer` `.repoHeader` (name `nowrap`, count `margin-left:auto`). Adding `min-width:0` to the flagged flex children is zero-risk where they already truncate; the rest want eyes-on first.
- **R2-T1 (Tool preview popovers too wide on touch) ✅ DONE (`ec9ee00`, pending device confirm)** — `AlphaToolPillRow` / `AlphaChipRow` / `AlphaContextSummary` hardcoded the chat popover to `width: 560`, wider than a phone screen, so file read/write/diff previews overflowed off-screen with no horizontal scroll. Fix: add `maxWidth: calc(100vw - 24px)` to each `POPOVER_STYLE` so the popover shrinks to fit (its `pre-wrap` body reflows; code/diff bodies keep their own `overflow-x`). Desktop keeps the exact 560px. NOTE: if long *diff* lines (Pierre, `white-space: pre`) still overflow inside the now-narrower popover, that's a separate inner-scroll follow-up — the width cap was the headline bug.
- **R2-A1 (Chat "pops in" late on agent entry) — MEASURED; root cause = CPU remount cost, NOT data-timing. My first (data-timing) diagnosis was WRONG — user was right it's render cost.** Measured in the revived harness (real 8-msg chat, longtask PerformanceObserver across a navigate-away-and-back):
  - **It's a remount cost, proven by construction:** navigating via `#/` (redirects back, NO unmount) = ~1ms; via `#/home` (real unmount→remount) = ~450ms (mobile) / ~525ms (desktop). Same resident data both times ⇒ the delay is the synchronous CPU work of REBUILDING the view, not fetching/streaming.
  - **~85% is ONE synchronous task:** a single 300–500ms longtask = the remount render+commit. (Mobile single task ~360–394ms; desktop ~316–505ms.)
  - **Attribution (mobile 390px = the path the user hits → `MobileWorkspaceShell`, NOT desktop `DockingLayout`):** A/B with markdown parse skipped: ~360ms → ~213ms, so **markdown render ≈ 150ms (~33%)**; the remaining **~213ms = shell + `AlphaChatInterface` + virtualizer mount/reconciliation**. (Desktop path is different: skipping markdown there changed nothing — its cost is the `DockingLayout`/panel remount.) Numbers are for an 8-msg chat; markdown is ~constant (virtualized visible window), the per-history terms scale with length.
  - **Why the cheap fixes DON'T apply:** react-markdown re-parses on every render/mount, and caching the `<ReactMarkdown>` element descriptor does NOT skip the parse (the parse happens when React renders the component, not when the element is created) — so there's no trivial markdown memo. The agent view is keyed by taskID, so every switch remounts + re-parses.
  - **High-leverage fix = KEEP-ALIVE:** don't unmount the workspace/chat on navigation (render hidden when away / cache rendered chat per recent task) → revisits skip the whole remount+reparse (~450ms→~0). Architectural (routing/lifecycle), with memory (N workspaces resident) + correctness care. Lower-leverage alternatives: replace react-markdown with a parse-once-cache-the-hast renderer (~150ms); attack the ~213ms shell/virtualizer mount hotspot (needs more instrumentation); or a perceived-perf band-aid (keep outgoing chat visible during the transition to kill the blank flash). Recommend keep-alive; awaiting user steer on depth. Files: `WorkspacePage.tsx` (mobile branch L131), `MobileWorkspaceShell.tsx`, `ChatPanelContent.tsx`, `AlphaChatInterface.tsx`, `AlphaMarkdownBlock.tsx`.
  - Harness method (reusable): control port in `attachments/screenshots/control-port.txt`; test chat = ws_01kw1jjj…/agent/tsk_01kw1jjj…; measure via `evaluate` longtask observer around `location.hash` away→back; resize to 390 to hit the mobile path.
  - **PARTIAL FIX SHIPPED — preserve the O(history) computation across remounts** (keep-alive deferred as too big a lift). Memoized the pure full-history builders by input-array reference (`WeakMap`): `buildSubagentTree`, `buildSubagentMetadataMap` (`subagentTree.ts`), `buildToolResultMap` + new `filterRenderableNodes` (`alphaMessageUtils.ts`). Enabler: `mergeChatAndQueuedMessages` now fast-paths to return the input array **by reference** when nothing is queued, so for an idle agent `effectiveChatMessages === completedChatMessages` (the task-detail atom's stable array) across remounts → the WeakMaps hit and the builders are skipped. Correct by construction: message arrays are never mutated in place (the reducer always makes new arrays), so same-ref ⇒ same-contents; if the ref ever isn't stable the cache just misses (no benefit, never stale). 40 unit tests pass (4 new cache-behavior tests). NOTE: on the measured 8-msg chat these builders were negligible (~0 win there) — this targets the **un-virtualized O(history)** term that only bites LONG chats, so the speedup is UNVERIFIED on a long chat (needs a long-chat harness run or device feel). Does NOT touch the ~150ms markdown reparse or the ~213ms shell/virtualizer mount — those still want keep-alive. Files: `subagentTree.ts(.test)`, `alphaMessageUtils.ts(.test)`, `AlphaChatInterface.tsx`.
- **R2-A2 (AskUserQuestion not scrollable on mobile — HARD BLOCKER, user-reported on device) — FIXED (CSS-only, ships in this branch).** The failure: when the agent poses a question, `AskUserQuestion` replaces the composer in the chat's bottom input region; a tall question card (several long-description options) made the input region taller than a short mobile viewport, and with the app at fixed viewport height and no page scroll the later options + submit sat below the fold with nothing to scroll — unanswerable without switching to desktop. The shipped fix is the proposed low-risk CSS, in `AskUserQuestion.module.scss`: on `(pointer: coarse), (width <= 767px)` the `.card` gets `max-height: 70dvh` and `.optionsList` gets `min-height: 0; overflow-y: auto`, so the options region scrolls inside the card while the footer (submit + nav dots) stays pinned and reachable. Desktop is unaffected. dvh tracks the dynamic viewport, so browser-chrome show/hide is accounted for; remaining device check: confirm 70dvh leaves the card comfortable with the on-screen keyboard up.
