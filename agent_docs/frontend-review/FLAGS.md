# Frontend review — flagged issues triage

The frontend-review batch run (`agent_docs/frontend-review/_prompt.md`, applied
to every non-generated frontend source group — a component plus its co-located
stylesheet and unit test) fixed issues by default and **flagged** only those
that genuinely need a human decision. This file collects all flagged items with
their disposition.

- **604 component groups reviewed; ~617 fixes applied; 17 flags raised across 16
  distinct issues** (the duplicate `isDismissibleOverlayOpen` is written up from
  both sides). Severity: **12 MEDIUM, 4 LOW.** No HIGH/CRITICAL — nothing flagged
  is an active crash or data-loss bug.
- **Status:** **Theme C resolved** (3 inert/dead-wired features — investigated
  through full history and deleted as dead code) and **Theme B resolved** (2
  false-coverage tests — confirmed to guard still-live features and fixed with
  real assertions). Themes A, D, and E remain open for a human.
- The per-file `agent_docs/frontend-review/<path>.md` reports the run produced
  are **no longer kept** — this directory retains only this file and `_prompt.md`.
  Each report's full text still lives in its per-group commit
  (`git log --diff-filter=A -- agent_docs/frontend-review/<path>.md`). Line
  numbers below are from those reports and may drift.
- "Bucket" refers to the prompt's five FLAG-only buckets: #1 ambiguous intent,
  #2 true external contract, #3 needs test changes, #4 architectural/out-of-scope,
  #5 non-obvious security.
- The whole branch is green after the run: `just typecheck`, `just lint`,
  `just ratchets`, and `just test-unit-frontend` (2325 tests) all pass.

---

## Theme A — Bespoke `useEffect`+`useState` HTTP fetch instead of TanStack Query (7 flags)

The dominant finding. These all violate the same `sculptor.md` conventions
(`use_tanstack_for_pulled_data`, `no_bespoke_fetch_caching`,
`no_state_updates_on_unmounted`): HTTP-pulled reads are fetched in an effect and
cached in component state/atoms with hand-rolled race/debounce guards, rather
than going through a `@tanstack/react-query`-backed hook under
`common/state/hooks/`. They were **not** auto-fixed because each needs a *new*
shared hook plus a per-endpoint design decision (query-key shape, freshness /
`staleTime`, refresh-vs-optimistic semantics) and has no test coverage to prove
a conversion preserves behavior. **Bucket #4** (some also #2/#3 as noted).

**Recommended disposition:** treat as one coordinated migration, not seven
one-off rewrites — several of these endpoints share the "pre-workspace,
project-scoped, not WS-pushed" shape and a sibling already uses the bespoke
pattern (`useRepoInfo`), so converting piecemeal would leave the surface
inconsistent. File one ticket for the cluster.

- **MEDIUM** `common/state/atoms/ciBabysitterStatus.ts:8-40` — atom-based fetch
  cache + manual sequence-counter for `getCiBabysitterState`; endpoint is **not**
  on the unified WebSocket stream, so the optimistic-update-reconciled-by-WS
  pattern doesn't apply cleanly. Sole consumer `PrDetailDropdown.tsx`. (#4, borders #2)
- **MEDIUM** `components/ClosedWorkspacesPill.tsx:80-101` — bespoke
  `listRecentWorkspaces()` fetch with `isFetchingRef`/`lastFetchedKey`/`cancelledRef`
  coalescing; also an **unhandled promise rejection** (client is
  `throwOnError: true`, the async IIFE has no `catch`, so a failed fetch never
  retries). Already tracked as **SCU-487**; converting invalidates its
  coalescing-focused test suite. (#4, #3)
- **MEDIUM** `pages/add-workspace/hooks/useBranchNamePreview.ts:46-107` — dual
  debounced fetches (`previewBranchName`, `branchExists`) with request-id guards;
  sibling `useRepoInfo` (used right beside it in `AddWorkspacePage.tsx`) uses the
  same pattern → migrate the pair together. (#4)
- **MEDIUM** `pages/add-workspace/components/RecentWorkspaces.tsx:33-34,63-79` —
  `listRecentWorkspaces()` in an effect; deliberately fetches once and reconciles
  optimistic deletes via `deletedWorkspaceIdsAtom`, so refresh semantics are a
  design call. (#4)
- **MEDIUM** `pages/workspace/components/AgentTabs.tsx:67-81` (`DiagnosticsSubMenu`)
  — `getWorkspaceAgentDiagnostics` across four `useState`s; intentionally
  re-fetches on every submenu open, so a cached hook with `staleTime: Infinity`
  could serve stale "no session" data. (#4)
- **MEDIUM** `pages/settings/components/EnvironmentVariablesSection.tsx:36-53` —
  `getEnvVarNames` in a mount effect + imperative Refresh; missing unmount guard;
  no test file in group to guard a conversion. (#4, #3)
- **LOW** `components/RequireOnboarding.tsx:18-62` — `getConfigStatus` via
  effect; `OnboardingWizard.tsx` does the identical fetch → a clean fix is a
  shared `useConfigStatus` hook updating both, and the component also mixes
  server state with a local `onComplete` callback. (#4)

## Theme B — Tests that assert nothing (false coverage) (2 flags) — ✅ RESOLVED (fixed)

Both blocks were investigated through history: each was an **incomplete-from-birth
stub guarding a feature that is still live** (not a remnant of removed behavior),
so the verdict was fix, not delete. Both fixed; branch re-verified green
(typecheck, lint, frontend suite). The context-menu file was run 5× to confirm
the Radix-submenu interaction is not flaky.

- **`components/actions/ActionContextMenu.test.tsx` "move to group submenu" —
  FIXED.** Three of four tests asserted nothing and the fourth only checked the
  sub-trigger; they never opened the submenu because Radix menus need Pointer
  Capture / `scrollIntoView`, absent in jsdom. Added those no-op DOM polyfills to
  `vitest.setup.ts`, then rewrote the tests to open the submenu and assert real
  behavior: `onMoveToGroup(action, null)` on **No group**,
  `onMoveToGroup(action, groupId)` on a group, and the disabled (no-call) state
  for the already-ungrouped and current-group options. (Selection uses
  focus+Enter — Radix's reliable path in jsdom; plain `user.click` silently
  no-ops there.)
- **`chat-alpha/__tests__/AlphaFileChip.test.tsx` "executing label" — FIXED.** The
  `Writing…`/`Editing…` tests only checked the button was disabled, never the
  label. Moved `getExecutingLabel` into `chipRowUtils.ts` (its `ChipData` home,
  keeping `AlphaFileChip.tsx` exporting only its component) and unit-tested it
  directly for Write, Edit, and the no-block fallback, plus a render smoke test
  for the disabled executing state.

## Theme C — Inert / dead-wired features (3 flags) — ✅ RESOLVED (deleted)

All three were investigated through the full pre-epoch history (the `gitlab`
remote, ~78k commits) to settle "abandoned dead code vs. unfinished feature to
wire up." Verdict: all three are dead. Deleted as three atomic commits; branch
re-verified green (typecheck, lint, 2314 frontend tests).

- **`pages/workspace/WorkspacePage.tsx` — `ZenTopGradient` — UNFINISHED, never
  worked → removed.** `.zenGradient` was **never defined in any stylesheet in
  78k commits**; the component was born referencing the missing class, so zen
  mode only ever showed an empty zero-height div. Zen mode itself is live and
  unaffected. Since the gradient never functioned and its styling intent was
  never recorded anywhere, the inert component (+ its now-unused
  `zenModeActiveAtom` import) was removed rather than speculatively authored.
- **`chat-alpha/AlphaChatView.tsx` + `AlphaChatInterface.tsx` — `onHeightChange`
  — DEAD → removed.** History showed it was a real feature, deliberately
  decommissioned: renamed to the intentionally-unused `_onHeightChange`, and an
  earlier (never-shipped-to-`main`) commit already removed it from both files,
  noting it was never consumed and that removal lets plain `React.memo` work.
  Replicated that removal; `useViewportStability` is still invoked for its
  scroll-compensation effects.
- **`pages/workspace/utils/utils.ts` — `getToolDisplayName` /
  `getToolDisplayNamePresent` — DEAD → removed.** Not "a maintained surface
  awaiting wiring" (the report's tentative read was wrong): history shows they
  had production callers that were deleted when the classic chat component tree
  was removed and the alpha UI migrated to its own tool-summary helpers. Removed
  both, their now-orphaned cascade (`parseBackgroundTaskType`, the
  `TASK_OUTPUT`/`TASK_STOP` display maps, the `BackgroundTaskType` type), and the
  dead `utils.test.ts`. The module's live helpers (`stripHtml`, `isDiffTool`,
  `isHiddenTool`, …) are unaffected.

## Theme D — Duplicate, behaviorally-divergent utility (1 issue, buckets #1/#4)

- **MEDIUM** `isDismissibleOverlayOpen` is defined twice with the same name and
  documented purpose but **opposed implementations**:
  `common/overlayUtils.ts:9-49` scans the DOM for open Radix overlays *and* TipTap
  @-mention/skill popovers regardless of focus, while
  `common/ShortcutUtils.ts:203-209` only matches focus-trapped
  `[role="dialog|alertdialog|menu|listbox"]` (blind to TipTap popovers and Radix
  `Select`). Consumers are split — `usePageLayoutKeyboardShortcuts.ts` + `AgentTabs.tsx`
  use the overlayUtils copy; `WorkspaceTabs.tsx`, `panels/hooks.ts`,
  `keybindings/hooks.ts` use the ShortcutUtils copy — so global keyboard handlers
  gated through the latter do **not** suppress while a mention/skill list is open
  (latent UX bug). The two docstrings advocate opposite designs, so which is
  canonical is ambiguous (#1) and consolidating changes runtime keyboard behavior
  at three call sites with no test to prove equivalence (#4). Recommended: keep
  the more complete `overlayUtils.ts` version, delete the `ShortcutUtils.ts` copy,
  repoint its three importers, and QA overlay keyboard handling.

## Theme E — Standalone items

- **MEDIUM** `components/FilePreviewList.tsx:111-114` (bucket #1) — in `http`
  mode, per-file `URL.createObjectURL(blob)` results are never
  `URL.revokeObjectURL`'d, leaking object URLs across a chat with many remote
  images. The obvious "revoke on unmount" fix **conflicts with the documented
  intentional behavior** at lines 64-66 (media is registered with the agent-level
  lightbox and kept alive after unmount so virtualized off-screen images stay
  viewable). Correct scope (track ownership in the shared lightbox registry?) is a
  human call.
- **MEDIUM** `pages/workspace/components/chat-alpha/hooks/useAlphaScrollPersistence.ts:31-65`
  (bucket #4) — its `scroll` listener saves position on every scroll without
  consulting the shared `isProgrammaticScrollRef`, violating
  `chat_scroll_listeners_respect_programmatic_flag`. The naive "plumb the ref" fix
  doesn't work: `useAlphaAutoScroll` runs first and clears the flag in the same
  event dispatch, so this listener (which saves a frame later in `rAF`) always
  sees it already cleared. A correct fix requires reordering hooks / changing
  flag-clear ownership across the scroll subsystem. Practical impact today is low.
- **LOW** `pages/workspace/components/UndoQueuedMessageDialog.tsx:72` (buckets #2/#3)
  — ✅ **RESOLVED (renamed).** The "Remove" button carried
  `data-testid={ElementIds.UNDO_QUEUED_MESSAGE_COPY_BUTTON}` while the actual copy
  `IconButton` had none — the id, its POM accessor, and the integration test all
  called the Remove control a "copy button." Confirmed via the test that the
  intent was always to target Remove (the test clicks it to discard the queued
  message), so renamed the whole chain to `UNDO_QUEUED_MESSAGE_REMOVE_BUTTON`:
  the `ElementIDs` constant in `constants.py`, the `data-testid`, the POM method
  `get_undo_queued_message_remove_button`, and both test call sites. The frontend
  type regenerates from `constants.py` (it is gitignored, not committed). Verified
  green: `just check`, typecheck, lint, frontend suite. (The copy `IconButton`
  still has no test id — intentional; nothing tests copy-to-clipboard.)
