# QA: Compact "Uniform Panels" Workspace Layout

**Branch:** `bryden/build-compact-layout`  **Base commit at QA start:** `e39f1b989a2`
**QA agent:** read-only w.r.t. source — only this file is edited. Bugs are documented, NOT fixed.

> NOTE: another agent is implementing UI changes on this same branch concurrently.
> If the source shifts under QA, findings are timestamped against the commit above and
> re-verified where feasible; moving-target cases are flagged inline.

## Scope

The compact layout (`sculptor/frontend/src/components/panels/`) is four sections —
**Left / Center / Right / Bottom** — each a `PanelSection` bound to a `ZoneId`, laid out
by `CompactLayout.tsx`. Two recently-built features are the focus:

- **Section splitting** — `SplittableSection.tsx`, `sectionHooks.ts`, `sectionLayoutAtoms.ts`.
  A section splits once into two sub-sections (stacked = `horizontal`, side-by-side = `vertical`)
  via a tab's right-click menu. The split half binds to a `<zone>:split` zone. Emptying a half
  should collapse the split.
- **Drag tabs between sections** — `PanelDndProvider.tsx`, `PanelSection.tsx`, `TabBar.tsx`,
  `SortableTab.tsx`. One app-level `DndContext`; dragging a tab into another section moves it
  (`movePanel(panelId, zone, insertIndex)` on drop), with a ghost placeholder + drop-target
  highlight while dragging.

### Relevant localStorage keys
`sculptor-zone-assignments`, `sculptor-zone-order`, `sculptor-active-panel-per-zone`,
`sculptor-zone-visibility`, `sculptor-section-split`, `sculptor-section-size-percent`,
`sculptor-tab-strip-position`.

### Section test ids
`panel-section-<side>` (left/center/right/bottom), tabs `panel-tab-<panelId>`,
add buttons `panel-section-add-<side>`.

## Behaviors to test (checklist)

Legend: [x] tested OK · [B#] bug found (see table) · [~] partial/limited

### Section splitting
- [x] Split each section (Left/Center/Right/Bottom) horizontally (stacked).
- [x] Split each section (Left/Center/Right/Bottom) vertically (side-by-side).
- [x] Resize handle works in a split; ratio clamps to 15%–85%.
- [x] Split persists across reload for STATIC-panel halves · [B5] does NOT persist for dynamic-panel halves.
- [x] "+" / add menu works in BOTH halves of a split.
- [x] Right-click split menu is hidden once a section is already split (`useCanSplitSection`).
- [B4] Splitting a single-tab section leaves an empty primary half.

### Collapse-on-empty (the core area of concern)
- [x] Empty SECONDARY (`:split`) half by closing its last tab → collapses.
- [x] Empty SECONDARY half by dragging its last tab out → collapses (self-heal).
- [x] Empty SECONDARY half by deleting the agent in it → collapses (self-heal).
- [x] Empty PRIMARY half by closing its last tab → promotes split half + collapses.
- [B1] Empty PRIMARY half by dragging its last tab out → does NOT collapse (known bug confirmed).
- [B1] Empty PRIMARY half by deleting/removing its content via non-close path → same root cause (self-heal watches only split zone).

### Drag tabs
- [x] Reorder within a strip (insertion index correctness).
- [~] Drag across sections — move/persist correct; mid-drag ghost+highlight NOT screenshottable (atomic drag, see notes).
- [x] Drag into a split half (primary and secondary).
- [x] Drag into an empty (open) section.
- [x] Drag the LAST tab out of a section (source collapses if non-center/non-split).
- [B2] Drag the only agent out of Center → Center ends up empty (invariant violation).
- [~] Ghost/placeholder + drop-target highlight — could not capture mid-drag (harness limitation).

### Interactions
- [x] Section visibility toggles (Left/Right/Bottom) with/without splits.
- [x] Rename via double-click (and context-menu "Rename" present).
- [x] Tab close with `closeReplacesIcon` (icon↔X swap) · [B3] misleading on the only agent.
- [B3] Close button shown on the only agent but click is a silent no-op.
- [~] Electron `<webview>` panels (terminal/browser) mid-drag — harness uses xterm in a browser, not a real Electron `<webview>`, so the freeze-during-drag risk could NOT be exercised here.
- [x] localStorage sanity after each operation (read via `evaluate` throughout).
- [x] Tab-strip-position = "bottom" renders correctly.

## Code-analysis hypotheses (to confirm in-app)

| # | Hypothesis | Where |
|---|---|---|
| H1 | Self-heal only watches the SPLIT zone count, never the PRIMARY zone → emptying the primary half by a non-close path leaves an empty primary + live split. | `SplittableSection.tsx:47-55` |
| H2 | `movePanel` preserves visibility & does NOT collapse the split when the last panel leaves a split primary (vs. close-button promote path). | `hooks.ts:147-155` vs `sectionHooks.ts:215-241` |
| H3 | `sectionSplitAtom` is global but panels are per-workspace → switching workspaces may collapse a split globally (cross-workspace data loss). | `sectionLayoutAtoms.ts:60`, `SplittableSection.tsx:47-55` |
| H4 | Center has no visibility gate in layout, but `movePanel` can hide/empty it → dragging the only agent out of Center leaves it empty, violating "Center always keeps an agent". | `CompactLayout.tsx:108-110`, `hooks.ts:147-155` |
| H5 | Close "X" appears on the only agent (alwaysCloseable) but `handleClose` returns early → click is a confusing no-op. | `PanelSection.tsx:134-144`, `TabBar.tsx:141` |
| H6 | Splitting a single-tab section yields an empty primary half showing only "+" with no obvious un-split affordance. | `sectionHooks.ts:128-142` |

**All six hypotheses were confirmed in-app:** H1+H2 → Bug 1; H3 → Bug 6; H4 → Bug 2; H5 → Bug 3; H6 → Bug 4. A seventh issue (Bug 5, orphan-on-reload) was discovered during testing and shares Bug 6's root cause.

## Resolution (fixes applied)

All six issues were fixed on this branch. Architecture decision (per the user): **panel layout
is now per-workspace by default**; the cross-workspace/cross-device backend sync was dropped
(Option A), with a fallback to the default layout when a workspace has no saved layout.

| # | Fix | Key files |
|---|---|---|
| 1 | `movePanel` now collapses + promotes the surviving half when a drag empties a split's PRIMARY half (mirrors the close path). | `components/panels/hooks.ts` |
| 2 | Empty Center is allowed and now persists per-workspace (the bootstrap respects existing placement); no forced re-cram. | per-workspace persistence (below) |
| 3 | The close "X" is hidden on the only/active agent (per-tab `closeable` flag) — no more silent no-op. | `components/tabs/{types,TabBar}.tsx`, `components/panels/PanelSection.tsx` |
| 4 | Single-tab split kept; the resulting empty half now shows a heading ("This split pane is empty — add a panel, or drag a tab here."). | `components/panels/{EmptyPanelLauncher,PanelSection}.tsx` |
| 5 | Self-heal made race-safe: it only collapses the SECONDARY half when no panel is still *assigned* there awaiting registration (agent task / terminal still exists) → no orphaning on reload. | `components/panels/SplittableSection.tsx` |
| 6 | `sectionSplitAtom` + all layout atoms (assignments/order/active/visibility/split) are snapshotted per-workspace in `usePerWorkspacePanelLayout`; `usePanelLayoutSync` (backend sync) removed; the obsolete "per-workspace layout" experimental toggle removed. New experimental toggle "Share panel section sizes across workspaces" (default shared). | `common/state/hooks/usePerWorkspacePanelLayout.ts`, `pages/workspace/WorkspacePage.tsx`, `pages/settings/SettingsPage.tsx`, `components/panels/sectionLayoutAtoms.ts` |

**Verification:** `npm run tsc` clean, `npm run lint` clean, full frontend unit suite green
(2271 passing) including new tests for the per-workspace persistence (reset/restore/switch/save,
sizes shared-vs-unique) and the `movePanel` split-collapse promote.
**Manual harness:** blocked in this environment — the `/manual-testing` harness deadlocks waiting
for Vite (it does not drain Vite's stdout pipe; Vite is confirmed to start in ~6s when not piped).
Behavioral re-verification via the harness is pending a working environment.

## Bugs found

**Summary:** 6 issues — **3 High** (panel/agent loss or invariant violation: #1 split primary drag-out, #2 agent dragged out of Center, #5 + #6 agent/terminal orphaned by split-state desync on reload / workspace switch), 1 Low–Med UX (#4 empty primary half on single-tab split), 1 Low UX (#3 misleading close X). #5 and #6 share a root cause (split state lost while the panel's zone assignment persists → orphaned, invisible, unrecoverable dynamic panel) but have different, both-realistic triggers (reload vs switching workspaces).

| # | Title | Steps to reproduce | Expected | Actual | Severity | File/area |
|---|---|---|---|---|---|---|
| 1 | **Dragging the last tab out of a split's PRIMARY half does not collapse the split (leaves a dead empty pane)** | 1. Left section has 2+ tabs. 2. Right-click a tab → "Split vertically" (so primary=[changes], split=[files]). 3. Drag `changes` (the primary half's only remaining tab) out to the Center section. | The split collapses; the surviving half (Files) reclaims the whole Left section (mirroring the close-button promote path). | Split stays active: `top-left` order = `[]` (empty primary, still visible showing only "Add a panel"/"+"), `top-left:split` = `[files]`, `sculptor-section-split` still has `{top-left:{axis:vertical,ratio:0.5}}`. Wasted/dead empty pane. Screenshot `0103_drag.png`. | High | `SplittableSection.tsx:47-55` self-heal only watches the SPLIT zone count, never the primary; `hooks.ts:147-155` `movePanel` preserves visibility & never collapses a split when its primary empties (contrast: close path `sectionHooks.ts:215-241` promotes + collapses). |
| 2 | **Dragging the only agent out of Center empties Center (invariant violation)** | 1. Make Center hold only the agent tab (move any other center tabs out). 2. Drag the "Agent 1" tab from Center into another section (e.g. Left). | Center should always keep an agent — the drag of the last/only agent out of Center should be blocked or re-routed, just like closing the only agent is blocked (`PanelSection.tsx:137-138`). | Center becomes empty: `center` order = `[]`, `visibility.center=false`, agent now lives in the narrow Left column; Center shows the "Add a panel" empty state. The agent chat is crammed into a side column. **Persists across reload** — bootstrap does not re-assert the invariant. Screenshot `0111_drag.png`. | High | `hooks.ts:movePanel` (no center guard); the close-path guard in `PanelSection.tsx:134-144` is not mirrored for drag. |
| 3 | **Misleading close "X" on the only/active agent — click is a silent no-op** | 1. Have a single agent (default). 2. Hover the agent tab. 3. A close "X" appears in the icon slot (`closeReplacesIcon`). 4. Click it. | Either no close affordance on the un-closeable only agent, or some feedback. | The X appears on hover but clicking does nothing — agent stays put (assignment unchanged). The affordance implies an action that silently fails. | Low (UX) | `PanelSection.tsx:134-144` returns early when no other agent exists; `SortableTab.tsx:94-98` still renders the X because `alwaysCloseable`/`isCloseable` is true. |
| 4 | **Splitting a single-tab section creates a permanently-empty primary half with no obvious un-split** | 1. Section with exactly one tab (e.g. Bottom with just Terminal 1, or Center with just the agent). 2. Right-click the tab → "Split vertically"/"horizontally". | Either splitting a single-tab section is disallowed, or the section ends up usefully divided. | The lone tab moves to the split half; the **primary half is left empty** (just "Add a panel"/"+"). There is no merge/un-split affordance — the only way back is to drag the tab into the empty half (collapses via self-heal). Confusing dead space. Confirmed on Bottom (`0149`) and Center (`0155`). | Low–Med (UX, likely by-design) | `sectionHooks.ts:128-142` (`useSplitSection` always moves the clicked panel to the split half); split menu offered even when the section has only one tab (`PanelSection.tsx:158-167`). |
| 5 | **Agent/terminal panel ORPHANED (invisible + unrecoverable) on reload when it is the only panel in a split half** | 1. With a single agent in Center, right-click the agent tab → "Split vertically" (agent moves to `center:split`, `sculptor-section-split.center` set). 2. Reload the page. | The split + agent are restored exactly as saved; the agent chat stays visible. | After reload `sculptor-section-split` = `{}` (self-heal deleted the center split) but `sculptor-zone-assignments` still has `agent→center:split`. The `center:split` zone is no longer rendered (no split), so the **agent tab/chat disappears entirely (0 agent tabs)**. The orphaned agent is NOT offered in any section's "+" menu (dynamic panels with a zone assignment are excluded), so there is **no UI recovery path** — only editing localStorage brings it back. Static panels in the same situation are recoverable via "+"; agents & terminals are not. Screenshots `0160_get.png` (empty center), `0167` ("+" menu missing Agent 1/Terminal 1). | **High** | RACE: `SplittableSection.tsx:36,47-55` reads `panelsInZoneAtom(splitZone)` which is registry-filtered (`atoms.ts:145-147`); on reload the async dynamic-panel registry is empty first, so `splitPanelCount===0` fires the self-heal and deletes the split before the agent registers. Orphan is then permanent because `useAddableDynamicPanels` (`sectionHooks.ts:291-298`) only lists panels with NO zone assignment. |
| 6 | **Splitting a section then switching workspaces orphans the agent (global split state vs per-workspace assignments desync)** | 1. Workspace A: right-click the agent tab in Center → "Split vertically" (`split.center` set globally, agent → `center:split`). 2. Create or switch to workspace B. 3. Switch back to workspace A. | The split + agent in workspace A are preserved independently of workspace B. | **Reproduced deterministically.** Entering B deletes the GLOBAL `sculptor-section-split.center` (B's `center:split` is empty → B's self-heal fires). Back in A: `split` = `{}` but `agent→center:split` still assigned → agent orphaned, Center shows "Add a panel", 0 agent tabs (`0196_get.png`). Same unrecoverable end-state as Bug 5. Also reproducible by clearing only `sculptor-section-split` + reload (`0160_get.png`). | **High** | `sectionSplitAtom` is GLOBAL + localStorage-only (`sectionLayoutAtoms.ts:60`) while `zoneAssignmentsAtom` placements are effectively per-workspace (registry-filtered, `atoms.ts:145-147`); the cross-workspace self-heal `SplittableSection.tsx:47-55` mutates the shared global split. |

## Verified-working behaviors (no bug)

- Split horizontally / vertically via tab right-click menu — works on **all four sections** (Left h+v, Right h, Bottom v, Center h+v); state + render correct.
- Resize handle in a split works and **clamps** to MIN_RATIO 0.15 / MAX_RATIO 0.85.
- Split **persists across reload** for sections whose split halves contain STATIC panels (e.g. Right split with Files/Changes survived reload at ratio 0.15). (Contrast Bug 5: dynamic-panel split halves do NOT survive.)
- Close-button on the **last primary tab** → promotes the split half up and collapses the split (`sculptor-section-split` → `{}`). Works.
- Emptying the **secondary (`:split`) half** via drag → self-heal collapses the split. Works.
- Emptying the **secondary (`:split`) half** by **deleting the agent in it** → self-heal collapses the split (center returns to whole). Works.
- Within-strip reorder via drag (insertion order correct).
- Drag a tab across sections (move persists to `sculptor-zone-assignments` / `-order`).
- Drag a tab into an empty, open section (Right) → moves in, section stays visible.
- Drag the **last tab out of a normal (non-split, non-center) section** → source collapses (`visibility.<zone>=false`). Works.
- Add panel via section "+" menu (New Agent / New Terminal / static panels listed); "+" works in BOTH halves of a split.
- Section visibility toggle (Top bar "Toggle right/left/bottom").
- Right-click split menu correctly hidden once a section is already split (`useCanSplitSection`).
- Rename agent via double-click on tab (inline input → Enter commits; tab + chat header update).
- Tab-strip-position experimental setting = "bottom" renders the tab strips at the bottom of every section cleanly (no overlap/clipping).
- Terminal (xterm) content survives being moved into a split half.

## Minor observations (low-severity / hygiene)

- `visibility["<zone>:split"]` is left as stale `true` after a split collapses (never reset). Harmless (zone not rendered without a split entry) but dead localStorage state.
- Deleting an agent leaves a **stale `sculptor-zone-assignments` entry** for the removed panel (e.g. `agent:…→center:split` lingered after delete). Harmless (panel unregistered → filtered out) but not cleaned up.
- Heavy tab manipulation accumulates **stale `sculptor-zone-order` arrays** (panel ids appearing in multiple zones' order lists). Deduped at read time by assignments, but messy.

## Test environment notes

- Harness viewport 1400x900. Repo: `manual_test_repo` (auto-created), branch `testing`.
- `evaluate` action reads localStorage reliably; used to verify zone atoms after each op.
- **Limitation:** the harness `drag` action is atomic (no pause mid-drag), so the in-flight
  ghost placeholder + drop-target highlight could not be screenshotted. Drag *outcomes* were
  verified via localStorage + post-drop screenshots.
- Minor: `visibility["top-left:split"]` is left as stale `true` after a split collapses
  (never reset to false). Harmless because the empty split zone isn't rendered when
  `sculptor-section-split` has no entry, but it is dead state in localStorage.
