# Branch deep-review findings — `bryden/ui-refresh-2`

Deep review of the whole branch (merge-base `f20f0758`, ~118 commits, 562 files)
against the `agent_docs/ui_refresh/` docs, performed 2026-07-01. Method: six
parallel focused reviews (state/persistence, shell components, panel content,
spec conformance, cruft sweep, simplification), with the highest-severity
findings re-verified directly in source. Findings that two or more independent
reviews converged on are marked **[×2]**.

All frontend paths are relative to `sculptor/frontend/src/`.

Overall verdict: the core architecture (flat sub-section keyspace,
proxy-over-`atomFamily` one-write switch, consolidated snapshots behind the
persistence adapter, pure reducers in `sectionActions.ts`, the memo boundaries
below `SectionGrid`) matches the design docs closely and is high quality. The
issues below are at the edges — none require rearchitecting.

---

## P0 — Correctness bugs (fix before merge)

- [x] **P0.1 Per-agent isolation is incomplete in the chat surface.** `ChatInput`
  was keyed on the panel's agent, but components inside the same per-panel
  surface still read `useWorkspacePageParams()`:
  - `pages/workspace/components/chat-alpha/StatusPill.tsx:78-79` — the **Stop
    button interrupts the route's agent**, and the pill's PLAN artifact/task
    list follow the route agent.
  - `pages/workspace/components/QueuedMessages.tsx:25-56` and
    `QueuedMessageBar.tsx:32,71` — queued-message edit/delete/undo target the
    route agent while the message ids belong to the panel's agent.
  - `chat-alpha/AlphaToolGroup.tsx:58` — harness capability gates read the
    route agent (wrong pills for a pi panel viewed under a Claude route).
  - `chat-alpha/AlphaChatIntro.tsx:28`, `panels/NotesPanel.tsx:21-23`,
    `panels/SkillsPanel.tsx:83-84` — lesser instances of the same coupling.
  Fix: thread `taskId`/`workspaceId` props (or a chat-task context provider at
  the panel root); treat any `useWorkspacePageParams().agentID` under
  `chat-alpha/` as a bug.

- [x] **P0.2 Cross-workspace open-file events mutate the *viewed* workspace's
  persisted layout.** **[×2]** `setActiveDiffTabAtom` records the tab under
  `payload.workspaceId` but the reveal writes `openPanelAtom` /
  `jumpToSectionAtom`, which proxy to the **active** workspace
  (`pages/workspace/components/diffPanel/atoms.ts:296-301`;
  `useUnifiedStream.ts:196-203` dispatches for any workspace). An agent in
  background workspace B pops the Files panel open in workspace A — and it
  persists. Fix: skip the reveal when
  `payload.workspaceId !== get(activeWorkspaceIdAtom)`.

- [x] **P0.3 Agentless workspaces render a blank page.**
  `pages/workspace/WorkspacePage.tsx:87` (`if (!agentIDFromUrl) return null;`)
  with no zero-task branch in the fix-up effect, so the "workspaces can have
  zero agents" goal only holds when a stale agent id is in the URL. Matches the
  known `sculpt workspace create` blank-screen bug. Also: the saved-agent
  mapping is never cleared on agent delete. Fix: render the section shell with
  an empty center when the workspace has no agents.

- [x] **P0.4 Registry sync runs post-paint and rebuilds every task tick.** **[×2]**
  `common/state/hooks/useWorkspaceDynamicPanels.ts:123-133` is a plain
  `useEffect` while the scope flip + agent placement are `useLayoutEffect`s —
  the first committed frame after a switch renders the previous workspace's
  dynamic panels (violates the seamless-switch acceptance bar in
  `persistence_interface.md`). The effect also writes a brand-new registry
  array on every task tick with no equality guard, re-rendering every
  whole-registry subscriber several times per second during streaming. Fix:
  `useLayoutEffect` + an equality guard (the `panelDefinitionEqual` comparator
  already exists).

- [x] **P0.5 Stale agent-tab context menus.**
  `components/sections/registry/panelRegistry.ts:136-148` —
  `panelDefinitionEqual` omits `contextMenuActions`/`onRename`/`onRequestClose`,
  so async diagnostics arriving after a status change never re-emit through
  `selectAtom`: "Copy session id / transcript path" stay disabled with stale
  closures. Fix: compare the callbacks (with identity-stable upstream
  memoization), or resolve menu actions at open time via `store.get`.

- [x] **P0.6 Pierre highlighter gate missed on the chip-diff popover.**
  `chat-alpha/AlphaChipDiffPopover.tsx:266,274` mounts `PatchDiff` ungated —
  the first chip popover of a cold session can render permanently blank, the
  exact bug class f9b9b16b fixed ("Gate every Pierre mount"). Fix: route it
  through `usePierreHighlighterReady`/`PierreDiffView`.

- [x] **P0.7 Mark-read/artifact-sync only follow the active *center* panel.**
  `common/state/hooks/useWorkspaceShellBootstrap.ts:83-88` — an agent panel
  viewed in the right/bottom section (or a split-center secondary) is never
  marked read while the user watches it stream. Fix: derive the viewed agent
  from the active sub-section, or run mark-read per mounted agent panel.

- [x] **P0.8 Cmd+K panel/agent commands misbehave.**
  - "Show {panel}" performs `togglePanelAtom`, which **closes** an open,
    active, expanded panel (`CommandPalette/dynamic/panels.ts:56-72` →
    `sectionActions.ts:310-313`). Rename to "Toggle" or add a jump-only action.
  - The Cmd+K agent-create path drifted from the dropdown path despite
    `addPanelCore.ts`'s "can't drift" comment: no pi-disabled fallback, no
    navigation to the created agent, silent failure (no toast)
    (`CommandPalette/dynamic/addPanel.ts:96-104` vs
    `useAddPanelActions.ts:93-122`). Move the fallback into
    `createAgentInLocation` and align the perform.
  - `togglePanelAtom`'s never-placed/`fallbackSection` branch is unreachable
    and untested (`sectionActions.ts:319-320`).

- [x] **P0.9 Maximize can point at a collapsed section.** `toggle_left_panel`
  while left is maximized collapses it in the persisted layout while the
  transient maximize still shows it full-screen (`transientAtoms.ts:19`,
  `useWorkspaceShortcuts.ts:134-145`, `SectionGrid.tsx:70-79`). Enforce
  "maximized ⇒ expanded" in `withToggleSection`'s collapse path.

- [x] **P0.10 FilesPanel selection doesn't survive a tab switch.**
  `panels/FilesPanel.tsx:35` uses local `useState` where Changes/Commits use
  per-workspace atoms precisely so the open file survives unmount
  (`fileBrowser/atoms.ts:62-68`, `historyPanel/atoms.ts:7-13`). Add a
  `filesPanelSelectionAtomFamily`.

## P1 — Spec divergences and product decisions

Each shipped something different from what `goals.md`/`user_stories.md` still
promise, with no record in the audit docs. Decide: implement, or re-spec and
record in `removed-and-changed-features.md`.

- [x] **P1.1 `/btw` popup was never deprecated.** **[×2]** goals.md lists it
  under "Features to deprecate"; it is fully live end-to-end
  (`ChatInput.tsx:95-98,304-313`, `ChatPanelContent.tsx:143`,
  `useUnifiedStream.ts:185-191`, backend `btw_process_manager.py`,
  `test_btw.py`, POM, 6 ElementIDs). Execute the removal or formally
  un-deprecate.
- [x] **P1.2 FCC sidebar is fixed 240px, not resizable/shared.** **[×4]**
  `panels/ExplorerLayout.tsx:10-13,60`; `ExplorerLayout.test.tsx:34-40` now
  asserts no resize handle; the persisted `explorerListWidthPx`
  (`persistence/types.ts:28,53`) is dead but *required* by snapshot
  validation. goals.md and FCC-04 still promise drag-resize with shared width.
- [x] **P1.3 Splits self-heal instead of persisting.** goals.md: "Splits remain
  after the last panel in a sub-section is removed." Implementation
  auto-closes the split (`sectionActions.ts:74-81,140,176`; locked by unit
  test). The reinterpretation lives only in the gitignored
  `plan/01_04_action_atoms.md:33-36`.
- [x] **P1.4 Empty-state quick actions use recently-*closed* (transient,
  reset on reload), not "most recently created … not open"**
  (`transientAtoms.ts:106-124` vs goals.md).
- [x] **P1.5 "Keep open" retains more than spec** — also mode, source branch,
  and per-prompt agent settings incl. plan mode
  (`NewWorkspaceForm.tsx:271-281`); a sticky plan-mode across multi-creates is
  the surprising part.
- [x] **P1.6 PANEL-13 focus keybindings missing** — no `focus_<panel>` binding
  ids exist (`common/keybindings/definitions.ts`); the plan task
  (`04_05_keyboard_shortcuts.md` step 3) was never built.
- [x] **P1.7 AGENT-07 mark-unread deferred** — whole `test_mark_unread.py`
  skipped; also absent from the panel-tab context menu. Needs a ticket or a
  conscious drop.
- [x] **P1.8 Sidebar-toggle shortcut dead outside workspace routes** —
  `useWorkspaceShortcuts` is mounted only by `WorkspaceLayoutShell`, and the
  Cmd+K command is `when: isWorkspace` (`builtinCommands/panels.ts:115`),
  while the sidebar is visible on Home/Settings too.
- [x] **P1.9 Doc contradiction on close-last-panel.** `state_atoms.md` and
  `panel_registry.md` say closing the last panel collapses the section; the
  code (and its unit test) leave it expanded-empty, which matches
  `state_design.md`. Fix the two supplemental docs (or the code).
- [x] **P1.10 Bare "terminal" first-agent type still offered.**
  `newWorkspace/AgentTypeSelect.tsx:72-74` offers it while the add-panel model
  explicitly excludes a bare terminal agent type (decision B2); via
  `lastUsedAgentTypeAtom` it leaks into the pinned "New {recent} agent" row.
- [x] **P1.11 Debug chat view is unreachable dead code** — `debugViewAtomFamily`
  is read (`ChatPanelContent.tsx:94`) but never written; `DebugChatView.tsx` +
  test + story are dead. Delete or re-wire (flagged in
  removed-and-changed-features.md; still undecided).
- [x] **P1.12 Review All experimental toggle gates nothing** —
  `SettingsPage.tsx:469` + `isReviewAllEnabledAtom` remain but the panel is
  registered unconditionally (`panelRegistry.ts:62`). Gate it or delete the
  setting.

## P2 — Cruft & debt cleanup

### Repo / infra
- [x] `offload.tmp.toml` (repo root, untracked) — delete before merge; and
  delete the dead `[groups.isolated]` group from `offload.toml:47-50` (collects
  0 tests; the reason the temp file exists).
- [x] Uncommitted working-tree changes: `sculptor/testing/playwright_utils.py`,
  `tests/.../test_browser_panel.py`, `test_error_states.py` — commit or discard.
- [x] `agent_docs/ui_refresh/plan/` is committed while README.md claims it is
  gitignored — reconcile (DECISIONS_NEEDED C6).

### Dead frontend code (grep-verified zero importers)
- [x] `components/ClosedWorkspacesPill.tsx` + `ClosedWorkspaceRow.tsx` + both
  test files + `.module.scss` + `closedWorkspaceIdsAtom`
  (`atoms/workspaces.ts:343-355`) — orphaned since TopBar was deleted, yet the
  tests were updated to stay green. Deprecation target per goals.md.
- [x] `components/tabs/` tree (TabBar, SortableTab, OverlayScrollbar + scss) —
  only a story imports it; old consumers all deleted.
- [x] `components/panels/ResizeHandle.{tsx,module.scss,test.tsx}` **[×3]** —
  byte-identical dead duplicate of `components/sections/ResizeHandle.*`; also
  drop the now-unused `react-resizable-panels` dependency.
- [x] Orphan stylesheets: `components/ExitZenModeButton.module.scss`,
  `pages/workspace/WorkspacePage.module.scss`.
- [x] Dead exports/atoms: `layoutScopeAtom`, `activeSubSectionAtom`
  (`sectionAtoms.ts:34,137`), `getRegisteredPanelComponent`
  (`panelRegistry.ts:80`), `isSectionId` (test-only), the
  `removeWorkspaceLayoutAtom` re-export (`sectionActions.ts:17`),
  `agentTabOrderAtom` (`atoms/agentTabs.ts:8-13`), dead `DiffSkeleton`
  (exported, never rendered), `PanelDefinition.tabIcon` (built with
  `createElement` per task tick, rendered nowhere).
- [x] Hollowed-out diff-tab model (`diffPanel/atoms.ts`): dead
  `closeOtherDiffTabsAtom`/`closeAllDiffTabsAtom`/`reorderTabsAtom`/
  `openCombinedDiffTabAtom`/`diffPanelOpenAtom`/`diffPanelSplitRatioAtom`;
  `openTabs` grows unboundedly in persisted state with no tab bar to prune it;
  the deprecated `sculptor-diffPanel-open` key is still written on every open
  (`atoms.ts:301`) despite state_design.md's "the rewrite stops writing them";
  `HOST_PANEL_BY_KIND.combined → changes` is unreachable and now semantically
  wrong; `commitSelectionFromTab` has zero callers (wire CommitsPanel like its
  siblings or delete the mapping + fallback branches).
- [x] `explorerListWidthPx` dead-but-validated snapshot field (see P1.2).

### Dead settings (live UI wired to nothing)
- [x] "Per-workspace panel layout" toggle (`SettingsPage.tsx:429-439` +
  `isPanelLayoutPerWorkspaceAtom` + `is_panel_layout_per_workspace` in
  `config/user_config.py:271`) — its consumer was deleted; this is the
  share-sizes setting Task 7.2 mandated removing.
- [x] "Default split ratio" row (`FileBrowserSettingsSection.tsx:53-67` +
  `fileBrowserSplitRatioAtom` + `file_browser_default_split_ratio`).
- [x] Backend `PanelLayoutConfig` zone model (`config/user_config.py:83-90` +
  `panel_layout` field) — zero readers/writers.
- [x] Dead `close_workspace` (Meta+W) keybinding still defined and listed on
  the keybindings page with no handler (`definitions.ts:33-38`).

### ElementIDs / test harness
- [x] ~40 ElementIDs newly orphaned by this branch in `sculptor/constants.py`
  (zen/focus buttons, `DIFF_TAB`, `SETTINGS_PANELS_*` ×10, old tab/agent/
  terminal ids, `CLOSED_WORKSPACES_*` ×5, …) — delete + `just generate-api`.
  Keep `AGENT_TYPE_MENU_ITEM_TERMINAL` (used for a negative assertion).
- [x] Dead POM getters targeting testids never rendered:
  `testing/elements/workspace_sidebar.py:108-115`, `panel_tab.py:103-107`,
  `terminal.py:345-346`, `diff_panel.py:49`, `file_browser.py:26-45`.
- [x] Orphan POM modules: `testing/elements/history_panel.py`, `task.py`,
  `task_list.py`.
- [x] Stale skip reasons: `test_agent_panel.py:31,92` and
  `test_agent_concurrent_streaming.py:55` skip because "DnD not wired until
  Task 4.1" — Task 4.1 landed on this branch; unskip or restate the real
  blocker. Also stale: `test_restarts.py:15`, `test_multi_repo.py:293`,
  misnamed `test_open_command_palette_via_topbar_button`.
- [x] Intentional shims to sweep later (documented, keep for now):
  `get_workspace_tabs()` (`project_layout.py:62`), `testing/elements/agent_tab.py`.

### Comment hygiene
- [x] Plan/doc leakage in tests: ~40 files reference `Task X.Y` / `Decision
  B2` / `e2e_test_plan.md` / `goals.md` (pointers into a gitignored folder);
  one frontend leak at `LocalStorageLayoutAdapter.test.ts:96` (PERSIST-xx).
  Decide: keep story IDs (user_stories.md is committed), strip task/decision
  refs.
- [x] ~13 comments point at deleted components (`AgentTabs`, `WorkspaceTabs`,
  `PageLayout`, `DockingLayout`, zone visibility): `PluginOverlays.tsx:8`,
  `DevModeIndicator.tsx:20`, `Toast.tsx:43`, `CommandRegistrations.tsx:23`,
  `CommandPalette/runtime.ts:67`, `dynamic/workspaceActions.ts:22`,
  `builtinCommands/navigation.ts:76`, `contextActions/useGitAndOpenInRuntime.ts:18`,
  `atoms/tasks.ts:85`, `panels/ActionsPanel.tsx:406`,
  `diffPanel/atoms.ts:120,281`, `panels/browser/BrowserViewSlot.tsx:20`; plus
  the stale zen-mode comment at `CommandPalette/hooks.ts:41`.
- [x] Stale factual comments: `useCreateWorkspace.ts:145` (renamed function),
  `defaultLayout.ts:27` (terminal ids start at 1, not 0),
  `agentPanelPlacement.ts` header (cites a deleted constant);
  `state_atoms.md:28` cites a prototype hook that doesn't exist.

## P3 — Consistency & quality

- [ ] **Wide subscriptions above the memo boundaries.** **[×2]**
  `useAddPanelActions.ts:86-90` subscribes to the whole layout + whole
  registry and is mounted by every `SectionHeader`, `EmptySectionState`,
  `useWorkspaceShortcuts` (→ the shell), and the bootstrap — so every
  split-ratio pointer move and every task tick re-renders the shell,
  `PanelDndProvider`, `WorkspaceHeader`, and all four dropdowns. The contract
  (`component_tree.md`) says "on open only". Fix: subscription-free actions
  hook + list-building inside the opened dropdown content (see P4.2).
- [ ] `CommandPalette/hooks.ts:239,242` — whole layout + registry subscribed
  while the palette is closed; gate on `isOpen`.
- [ ] `WorkspaceSidebar.tsx:247,330-338,557-571` — whole `tasksArrayAtom`
  subscription, O(workspaces×tasks) recompute per tick, unmemoized
  `SidebarWorkspaceRow` with five inline-closure props. Apply the branch's own
  per-key-slice pattern.
- [ ] `WorkspacePage.tsx:43` + `useWorkspaceShellBootstrap.ts:52` — top-level
  `tasksArrayAtom` subscriptions; narrow to a per-workspace deduped slice;
  consider `memo(WorkspaceHeader)`.
- [ ] **Keyboard a11y on panel tabs:** `role="tab"` divs are draggable but not
  activatable (Enter starts a drag, no `onKeyDown` to switch panels; no
  `role="tablist"` ancestor; close button is interactive-inside-interactive)
  (`SectionHeader.tsx:140-154,279`).
- [ ] Resize-handle cascade fix is a patch, not a structure: callers must win
  a cross-module specificity fight to reposition the handle
  (`WorkspaceSidebar.module.scss:271-283`); add a first-class
  `variant="edge-overlay"` to `ResizeHandle` instead.
- [ ] Smaller: duplicated recency-`useMemo` between `FilesPanel.tsx:69-76` and
  `ChangesPanel.tsx:100-107`; `bgOverrideSheet` shadow-DOM effect duplicated
  between `PierreDiffView.tsx` and `ReadOnlyPreview.tsx`; quick-open book icon
  silently flips the global `markdownRenderModeAtom` to "rendered"
  (`DiffViewer.tsx:252-256`); empty delete-dialog name for untitled agents
  (`useWorkspaceDynamicPanels.ts:66`); manual Refresh affordance lost in the
  viewer (dead `headerActions`/`trailingActions` slots, no menu item)
  (`DiffViewer.tsx:92-93`, `DiffViewerMenu.tsx`); `useActiveSectionRing`
  doesn't reset the ring atom on unmount; three call sites hand-derive
  `isMaximized` instead of a slice atom; duplicated collapsed-gutter constant
  (`SectionHeader.tsx:267` / `WorkspaceHeader.tsx:218`) and 40px titlebar
  height (two scss files + inline style); no `version` field in persisted
  snapshots (add `version: 1` while "no backwards compatibility" still covers
  it); `ensureAgentPanelsPlacedAtom` bypasses the reducers and can duplicate
  `order.center` entries (`agentPanelPlacement.ts:47-55`, no test file);
  orphaned `sculptor-layout-ws-*` keys are only GC'd via the local
  optimistic-delete path (add an idle sweep against the workspace list).

## P4 — Simplifications (highest leverage first)

- [x] **P4.1 One `layoutQueries.ts` for the read predicates.** **[×3]**
  `isSectionExpanded` exists in 4 copies (`sectionActions.ts:23-25`,
  `sectionAtoms.ts:124-127`, `addPanelCore.ts:56`,
  `useWorkspaceShortcuts.ts:39`); `panelsIn`/`openPanelsInSubSection` in 2
  (`sectionActions.ts:30-38` = `sectionAtoms.ts:98-107` — the most
  behavior-critical query in the model); `listAvailableStaticPanels` in 2
  (`addPanelCore.ts:74-81` / `useAddPanelActions.ts:222-230` — this pair
  already drifted once, per audit/decisions.md); plus two near-identical
  sub-section enumerators (`activeableSubSections` /
  `listAvailableLocations`). Single most likely source of future invariant
  drift.
- [x] **P4.2 Subscription-free add-panel hook** (fixes the P3 contract
  violation): one derived `availableStaticPanelsAtom` in `addPanelCore.ts`
  read by React and by Cmd+K via `store.get`; move list/label building inside
  `DropdownMenu.Content` (mounts only while open).
- [x] **P4.3 `atomCache.ts` re-implements jotai's `atomFamily`** — 1:1 swap at
  the ~14 definition sites; gains `.remove()` for eviction (fixes the
  `panelDefinitionByIdAtom` per-agent leak, low-impact but free).
- [x] **P4.4 `AppShell` toast scaffolding** (~100 of 214 lines): six
  hand-wired toast atoms → one `AtomToast` component over a config array.
- [ ] **P4.5** Merge `GhostTab`/`DragOverlayTab` into one `TabPill`; extract a
  `MenuRow` for `AddPanelDropdown`'s 5× repeated row markup.
- [ ] **P4.6** Fold `splitDirection.ts` (22 lines, one consumer) into
  `sectionTypes.ts`; delete `isMultiInstanceKind` (use
  `definition.kind !== "static"`); extract `appendTerminalTab` inside
  `addPanelCore` (duplicated block); one `resolveStoredAgentType` for the
  pi-disabled fallback (3 copies); one `recentAgentLabel` in `addPanelCore`
  (dropdown and Cmd+K currently disagree); single-source the 400px center
  min-width (TS constant → inline style or CSS var, drop the scss literal).
- [x] **P4.7 (medium-risk, do with integration suite in hand)** Unify the two
  bootstrap agent-placement paths (`useWorkspaceShellBootstrap.ts:111-131` +
  `agentPanelPlacement.ts`) into one additive ensure + one route-keyed
  activation effect.
- [x] **P4.8 (optional)** Extract `SidebarRepoGroup` + the empty-first-run
  block from the 638-line `WorkspaceSidebar.tsx`.

Estimated net effect of P4.1–P4.6 + the P2 dead-code deletions: **~400+ lines
and 6+ files removed, one npm dependency dropped**, ~10 duplicated concepts
collapsed to single definitions — all low risk under the existing vitest +
`test_panel_*`/`test_section_*` integration coverage.

## What's in good shape (no action)

- Doc-to-code fidelity of the core model: flat keyspace, one-write switch
  (verified single writer of `activeWorkspaceIdAtom`), consolidated snapshots,
  genuinely swappable adapter (debounced writes, `beforeunload` flush,
  never-throwing reads, shape validation), disciplined transient/persisted
  split.
- The DnD architecture: narrow per-section preview slices with value-level
  dedup, equality-guarded midline writes, synchronous drop commit, keyboard
  drag machinery with documented rationale.
- The memo boundaries below `SectionGrid` (identity-cached panel components →
  no remounts on registry rebuild/switch).
- Workspace creation: one factored `useCreateWorkspace` shared by modal,
  inline first-run, and sidebar direct-create; correct 409 handling; first-run
  gating enforced at both the palette and keydown layers.
- Unit tests target the real invariants (collapse rules, split self-heal,
  scope isolation, adapter corruption cases). Known gaps: `togglePanelAtom`
  branches, `agentPanelPlacement.ts` (no test file), move-triggered self-heal,
  jump-into-collapsed-section.
