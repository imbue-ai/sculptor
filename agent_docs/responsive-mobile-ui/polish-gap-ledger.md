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

- **A1 (T2)** Pill borders inconsistent: the Branch `.pill` shows a crisp `var(--mobile-line)` border; the reused Radix Select triggers (Repo, Source) read as near-borderless — the Radix trigger styling overrides the group's border. Make `.pillTrigger` match `.pill`.
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
- **B3 (T1/T2)** **Agent pager dots missing** — spec S1/A1 want centered dots + dashed new-agent dot under the input; none render. (Verify whether they only appear with ≥1 agent / multiple agents.)
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

## Behavioral (from code analysis — not visible in stills)

- **BE1 (T1, perf)** TipTap typing lag: every keystroke writes the `promptDraftAtomFamily` jotai atom → full `ChatInput` re-render, plus `getMarkdown()` serialization twice per keystroke. Fix: debounce/uncontrolled draft + isolate the subscription + drop the double serialize. (Shared with desktop; verify with `measure-react-renders`.)
- **BE2 (T1)** Chat autoscroll "snaps to bottom too early" — the reused virtualizer/autoscroll running in the mobile flex container rather than its docked parent. Needs investigation in `useAlphaAutoScroll` against the mobile shell layout.

## Cross-cutting

- **X1** Mobile components (except `MobileNewWorkspace`) lack `data-testid`/`ElementIds` — blocks the e2e suite AND made this QA harder (had to click by coordinates). Adding them is a prerequisite for Phase C automated verification.

## Not yet captured (follow-up pass)
Home reflow, Settings reflow, the `+` / settings dropdown menus open, agent switcher/sheet,
changes-pill → review-all overlay, terminal overlay. The last three need agent-generated
state (a real task producing a diff / terminal), so they're slower to reach.
