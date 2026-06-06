# Uniform Panels — dead code to delete (follow-up)

The uniform-panels iteration (agents/terminals/center/diff all become panels)
left several files and exports orphaned. They were intentionally **left in place
during the spike** to keep the diff focused and avoid touching unrelated
subsystems (stories, tests, shared utils). This doc lists what can be removed as
a follow-up, grouped by confidence, with the importer facts to re-verify at
deletion time.

> Always re-run the importer greps before deleting — other in-flight branches may
> have added references. A quick `npx tsc --noEmit` after each deletion catches
> anything missed.

## A. Orphaned by this iteration — safe to delete

These have **no live importers** (only dead code / stories reference them).

- **`pages/workspace/components/DiffSplitContainer.tsx`** (+ `.module.scss`)
  The old center chat∥diff split container. Zero importers. Superseded by the
  in-panel `MasterDetailPanel`.

- **`pages/workspace/panels/FileBrowserPanel.tsx`** (+ `.module.scss`)
  The old three-tab (Browse/Changes/History) file browser. Zero importers —
  split into `FilesPanel` / `ChangesPanel` / `CommitsPanel` back in iteration 1
  but never deleted.

- **`pages/workspace/components/diffPanel/DiffTabBar.tsx`** (+ `.module.scss`)
  The multi-file diff tab strip + toolbar. After the polish pass (toolbar moved
  into the `DiffFileHeader` "…" menu) its only importers are the now-dead
  `DiffSplitContainer` and `stories/custom/tabs/TabBar.stories.tsx`. Delete
  alongside `DiffSplitContainer`; update or drop the story usage.

## B. Vestigial exports — remove with light refactors

Still imported, but no longer drive any behavior in the uniform-panels layout
(the in-panel viewer keys off each panel's own `diffPanelStateAtomFamily`
scope + `activeTabPath`, not a global open flag).

- **`diffPanel/atoms.ts`: `diffPanelOpenAtom`, `diffPanelSplitRatioAtom`,
  `closeDiffPanelAtom`**
  - `setActiveDiffTabAtom` still sets `diffPanelOpenAtom = true` — harmless, remove.
  - `common/state/hooks/usePerWorkspacePanelLayout.ts` (+ its test) saves/restores
    `diffPanelOpen` / `diffPanelSplitRatio` per workspace. Drop that sync — only
    zone visibility + sizes remain per-workspace.
  - `components/WorkspaceTabs.tsx` reads `diffPanelOpenAtom` — verify what it
    gates (it's the hidden keybinding host) and remove the now-moot branch.
  - `DiffTabBar` (dead) uses `closeDiffPanelAtom`.

- **`components/tabs` — the `rightContent` prop path**
  `TabBar`'s `rightContent` prop and the `compactScrollFill` / `compactRightContent`
  styles (TabBar.module.scss) exist only to right-pin trailing controls. The only
  user was `DiffTabBar` (dead) — `PanelSection` now passes the "+" as a child.
  Remove the prop + styles once `DiffTabBar` is gone. (`TabBar.stories.tsx` also
  exercises `rightContent`; update the story.)

## C. Unused CSS / minor cleanups

- **`pages/workspace/WorkspacePage.module.scss`: `.centerPanel`** — no longer
  referenced (the bespoke center wrapper is gone).
- **Diff header "…" menu** has both a **"Close"** (collapse the in-panel viewer,
  added in the polish pass) and the file-action **"Close tab"** — in single-file
  master-detail they do the same thing. Drop one for clarity (keep "Close").

## D. Possibly-unused `ElementIds` — verify against integration tests first

The old agent-tab strip, multi-terminal strip, and center diff toolbar are gone,
so these element IDs may be unused **in the frontend** now:
`AGENT_TAB`, `ADD_AGENT_BUTTON`, `TERMINAL_TAB`, `ADD_TERMINAL_BUTTON`,
`DIFF_EXPAND_TOGGLE`, `DIFF_CLOSE_PANEL_BUTTON`, `FILE_VIEW_TAB_MARKER`, `DIFF_TAB`.

⚠️ Several are still referenced by **Python integration tests** that target the
old layout (e.g. `sculptor/tests/integration/frontend/test_at_mention_file_chip_click_opens_tab.py`).
Those tests need rewriting for the new layout regardless; retire the IDs only
after the tests are updated. Removing `ElementIds` requires `just generate-api`.

## E. Pre-existing legacy — the whole `DockingLayout` subsystem (largest)

`DockingLayout` was the original docking UI; iteration 1's `CompactLayout`
replaced it in the workspace page. It is **dead in the app** — the only real
component importers are its own story and test:

- `components/panels/DockingLayout.tsx` (+ `.module.scss`, `.test.tsx`)
- `components/panels/{LeftSidebar,RightSidebar}.tsx` + `Sidebar.module.scss`
- `components/panels/SidebarIcon.tsx` (+ `.module.scss`)
- `components/panels/SidebarDropZone.tsx` (+ `.module.scss`)
- `components/panels/VerticalSplit.tsx`
- `components/panels/ZoneContent.tsx` (+ `.module.scss`) — used only by `VerticalSplit`
- `components/panels/PanelModal.tsx` (+ `.module.scss`)
- `components/panels/PanelContextMenu.tsx` — used only by `SidebarIcon`
- `stories/custom/panels/DockingLayout.stories.tsx`

**Untangle before deleting:**
- **`components/panels/PanelHeader.tsx` is SHARED** — used by Actions / Notes /
  Skills / FileBrowserHeader panels. **Keep it.**
- **`components/panels/utils.ts` references `SidebarDropZone`** — confirm it's a
  DockingLayout-only helper (e.g. `computeToggleAction`/drop-zone logic) and
  prune just that part; `utils.ts` itself is shared with the compact layout.
- The shared panel **atoms/hooks** (`atoms.ts`, `hooks.ts`, `sectionHooks.ts`)
  back the compact layout too — do **not** remove zone/assignment state, only the
  DockingLayout-specific rendering components.

This is the biggest chunk and is independent of uniform-panels; schedule it on
its own once the compact layout is confirmed to fully replace it.
