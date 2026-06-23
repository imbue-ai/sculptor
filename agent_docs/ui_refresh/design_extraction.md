# Design extraction

This document is a companion to `goals.md`. It catalogs the styling and components worth copying from the throwaway prototype branches — `bryden/scu-1474-compact-workspace-layout` and `bryden/scu-1494-rewrite-new-workspace-modal` — into the rewrite.

It is a styling map only. `goals.md` is the source of truth for behavior, and the prototypes’ in-branch notes (their `agent_docs`, test plans, and similar markdown) should not be trusted — see “Relationship to the prototype” in `goals.md`.

Paths below are relative to `sculptor/frontend/src` on the prototype branches (`scu-1474` unless marked `scu-1494`). Copy each component’s `.module.scss` (and its structural JSX) into the rewrite, but re-derive behavior from `goals.md`. Copy the shared foundation first — everything else depends on it.

## Shared foundation (copy first)
- Tokens and globals: `styles/tokens.css` (durations `--duration-*`, z-index `--z-*`, shadows `--shadow-*`, scrollbar tokens), `index.css` (app zoom/height, Inter font, `.icon-xs…xl` sizing, `body.sculptor-resizing webview { pointer-events: none }`, search highlight), `styles/radix-overrides.css`.
- Radix Themes scales (`@radix-ui/themes`): `--gray-*`, `--accent-*`, `--space-*`, `--radius-*`, `--font-size-*`, `--font-weight-*` are used everywhere below.
- The thin-scrollbar mixin (`styles/_scrollbar.scss`, `@include thin-scrollbar`) — used by every scroll area.

## Workspace sidebar (scu-1474)
- `components/nav/WorkspaceNavSidebar.tsx` + `.module.scss` — the rail: drag gutter with `getTitleBarLeftPadding()` for macOS traffic lights, top nav pills (active = `--accent-a3`/`--accent-11`), collapsible repo groups (hover-revealed actions via `:focus-within`/`[data-state=open]`), workspace rows (28px pill, `--space-5` indent, hover `--gray-a3`, active `--accent-a3`, hover-reveal delete + menu icons).
- `components/nav/CollapsedSidebarToggle.tsx` + `.module.scss` — the show-sidebar icon when collapsed.
- `components/InlineRenameInput.tsx` + `.module.scss` — inline rename (inset box-shadow border); reused by panel-tab rename.
- `components/statusDot/StatusDot.module.scss` — workspace status dots.
- ⚠️ Net-new, NOT in the prototype: the **resizable sidebar + minimum width** (the prototype rail is a fixed 240px, no handle), and the **version row + “Report a bug” entry in the sidebar bottom** (the prototype bottom is Settings + Help; version lives in the footer via `components/VersionDisplay.tsx`). Build the resize handle and relocate the existing `VersionDisplay` and `ReportProblemPopover` (both on `main`) into the sidebar.

## Sections, tabs, splits, empty state, drag & drop (scu-1474)
- `components/panels/PanelSection.tsx` + `.module.scss` — section frame; the active-section **ring** is `.focused`/`.ringVisible::after` (1px `--accent-9` border, opacity fade). Copy the visual; rebuild the (brittle) timing, keeping the ~2s duration.
- `components/panels/SectionTabBar.tsx` (+ section-scoped styles in `PanelSection.module.scss`); tab pills in `components/tabs/SortableTab.module.scss` (compact) + `TabBar.module.scss` — 34px header, pill tabs (active = `--gray-4`), always-visible close button, drag drop-edge box-shadows.
- `components/panels/SplittableSection.tsx` + `.module.scss` — stacked/side-by-side split, ratio flex-basis, 15–85% clamp, self-heal on empty.
- `components/panels/ResizeHandle.tsx` + `.module.scss` — 1px divider, ±4px hit-area, hover `--gray-a7`, active `--accent-9`.
- `components/panels/EmptyPanelLauncher.tsx` + `.module.scss` — section empty state (centered Browse button + up-to-5 quick-add buttons + split hint).
- `components/panels/PanelDndProvider.tsx` + `.module.scss` — dnd-kit context, drag-overlay tab, per-zone droppables (incl. collapsed-section and split sub-section zones).
- `components/DeleteConfirmationDialog.tsx` (+ `pages/workspace/components/TerminalCloseConfirmation.tsx`) — the close/delete AlertDialog.
- `components/panels/PanelHeader.tsx` + `.module.scss` — 41px header for static panels.
- Add-panel: reuse the **item-row styling** from `components/panels/AddPanelPalette.module.scss` (icon + title + “recently used” pill), but render it in a **dropdown**, not the cmdk overlay (per “Adding a panel” in `goals.md`).

## Layout shell & workspace header (scu-1474)
- `components/panels/CompactLayout.tsx` + `.module.scss` — the four-section shell, percent→pixel resolver, center min 400px / sides floor 150px.
- `pages/workspace/components/WorkspaceBanner.tsx` + `.module.scss` — the simplified workspace header (branch pill, section toggles, drag spacer); re-home the PR button + diff summary per `goals.md`.
- Maximized presentation: `.maximized` in `PanelSection.module.scss` (absolute inset:0, `--z-sticky`) + `getTitleBarLeftPadding()` for OS controls.

## Agent & terminal panels (scu-1474)
- `pages/workspace/panels/AgentPanel.tsx` (wrapper) + `pages/workspace/components/ChatPanelContent.tsx` / `chat-alpha/AlphaChatInterface.(tsx|module.scss)` — the chat surface (centered scroll area, persistent thumb, bottom bar).
- `pages/workspace/panels/TerminalPanel.(tsx|module.scss)` and `pages/workspace/components/AgentTerminalPanel.(tsx|module.scss)` — xterm container (`--terminal-panel-bg`, overlay scrollbar).
- Agent-type picker: the `ChooseAgentPage` rows in `AddPanelPalette.tsx`.

## Files / Changes / Commits & diff viewer (scu-1474)
- `pages/workspace/panels/MasterDetailPanel.(tsx|module.scss)` (→ `ExplorerLayout` in the rewrite) — resizable explorer (200px min list, 280px min detail) + the empty `EmptyDetail`.
- `pages/workspace/panels/MasterDetailTreeHeader.(tsx|module.scss)` (→ `ExplorerTreeHeader` in the rewrite) — 41px header with search box + tree-options menu.
- `pages/workspace/panels/fileBrowser/FileTree.(tsx|module.scss)`, `TreeRow.tsx` — 28px pill rows (hover `--gray-a3`, active `--accent-a3`, deleted line-through, green/red mono line stats), flat + tree variants.
- `pages/workspace/components/diffPanel/DiffPanel.(tsx|module.scss)`, `DiffFileHeader.(tsx|module.scss)`, `DiffSkeleton.(tsx|module.scss)`, `InFileSearchBar.(tsx|module.scss)`, `DiffScopePicker.(tsx|module.scss)` — diff viewer, breadcrumb header, the static (no-shimmer) skeleton, search bar, scope toggle. The **three-dot menu** is assembled from `DiffViewMenuItems` (split/unified, wrap, find, markdown) + the tree options (flat/tree, collapse) — this is where the relocated icons now live.
- `pages/workspace/panels/historyPanel/HistoryTabContent.(tsx|module.scss)`, `CommitEntry.tsx` — commit graph (dots: gray / green = HEAD / amber-ring = uncommitted) + rows + popover; `ChangesTabContent.module.scss` commit footer.

## New workspace modal & empty first-run (scu-1494)
- `components/NewWorkspaceModal/NewWorkspaceModal.(tsx|module.scss)` + `components/PaletteDialog/PaletteDialog.(tsx|module.scss)` — opaque Raycast-style dialog (720px, centered at 14%, `--shadow-xl`).
- `components/NewWorkspaceModal/NewWorkspaceForm.tsx` — borderless title (heading scale) + auto-growing prompt textarea, breadcrumb context row of pills (repo / agent type / mode / branch), footer (“keep open” switch + Cmd+Enter hint + Create).
- `components/NewWorkspaceModal/BranchNameField.(tsx|module.scss)` — monospace branch pill with sanitization, shuffle button, stable error slot.
- Inline first-run: `pages/home/RecentWorkspaces.(tsx|module.scss)` `.inlineForm` (card-wrapped form on empty home) + `components/NewWorkspaceModal/homePromptPrefill.ts` (the `/sculptor:help` prefill).

## Do not copy (prototype-specific)
- The cmdk **AddPanelPalette overlay** as the add-panel surface — we use a dropdown; keep only its row styling.
- The **focus-ring timing** logic (brittle setTimeout/pulse) — rebuild it; keep only the CSS treatment.
- One-off hacks: hardcoded 11px font sizes, `margin: 0 !important` Radix ghost overrides, `field-sizing: content` (Chromium-only).
- Hardcoded title-bar padding constants — keep the `getTitleBarLeftPadding()` helper, don’t inline numbers.
