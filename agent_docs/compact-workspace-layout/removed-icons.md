# Removed icons / actions (compact-workspace-layout)

This iteration **removes** a set of secondary icons and dropdowns to make the
workspace feel compact and clean (REQ-ICONS-1, REQ-TOPBAR-7). Per REQ-ICONS-2
they are tracked here so they can be reintroduced behind **three-dot overflow
menus** (the follow-up task), or otherwise restored.

Nothing here is "deleted forever" — each row notes where the behavior lived and
how to bring it back.

## File browser (now the Files / Changes / Commits panels)

The old `FileBrowserPanel` header (`fileBrowser/FileBrowserHeader.tsx`) hosted
four secondary icons. The split panels (`FilesPanel`, `ChangesPanel`,
`CommitsPanel`) render the underlying content directly and drop the header, so
these are gone for now:

| Icon / action      | Lucide icon       | What it did                                  | Backing atom / handler                          |
| ------------------ | ----------------- | -------------------------------------------- | ----------------------------------------------- |
| Flat-list / tree   | `List`/`ListTree` | Toggle tree vs. flat file view               | `toggleViewModeAtom` → `fileBrowserStateAtomFamily.viewMode` |
| Collapse all       | `ChevronsDownUp`  | Collapse all folders / commits in the view   | `collapseAllFoldersAtom` / `collapseAllChangesFoldersAtom` / `collapseAllCommitsAtom` |
| Search files       | `Search`          | Open the in-panel file search                | `setSearchAtom` → `fileBrowserStateAtomFamily.searchOpen` |
| Refresh            | `RefreshCw`       | Re-fetch the file tree                        | `useFileTree(...).refetch`                       |

> Note: the `FileBrowserHeader` / `FileSearch` components and the atoms above
> still exist — only the icons that triggered them were removed from the new
> panels. A three-dot menu can re-expose them per panel.

The old `FileBrowserPanel.tsx` itself is now unused (kept on disk for reference).

## Diff / file viewer (single-file mode)

`DiffTabBar` gains a `singleFileMode` (used by the Center's `DiffPanel singleFile`):

| Icon / action          | Lucide icon              | What it did                                  | Notes                                   |
| ---------------------- | ------------------------ | -------------------------------------------- | --------------------------------------- |
| Multi-file tab strip   | (tab list)               | Switch between several open file diffs        | Dropped — one file at a time (REQ-CENTER-4) |
| Expand / review mode    | `Maximize2`/`Minimize2`  | Fullscreen the diff over the chat            | Dropped (relied on the old expand-mode docking) |
| Diff scope picker      | (segmented control)      | "All" vs "Uncommitted" in the combined view  | Combined view is now the Review All panel (REQ-CENTER-5); the picker lives there |

Kept per-file controls: find-in-file, split/unified toggle, line-wrap toggle,
markdown render toggle, and **close**.

## Top bar — PR/MR button (REQ-TOPBAR-7)

The PR/MR button no longer has a dropdown in any state:

| Removed dropdown        | What it did                                              |
| ----------------------- | ------------------------------------------------------- |
| Create chevron          | "Edit prompt…" (opened `PrPromptDialog`)                |
| Open-PR detail popover  | Pipeline status, reviews, comments (`PrDetailDropdown`) + the pipeline/review status dots |
| Assign-MR mismatch menu | "Create → branch" / "switch target" choice on target mismatch |

States now: no PR → **Create** button; open PR → **link**; merged/closed →
disabled-looking link. `PrDetailDropdown.tsx` / `PrPromptDialog.tsx` are unused
(kept on disk).

## Chrome removed entirely

| Element                    | Where it was            | Replacement                                              |
| -------------------------- | ----------------------- | ------------------------------------------------------- |
| Left / right icon rails    | `LeftSidebar`/`RightSidebar` | Each side is now a panel section with a tab strip + "+" |
| Bottom bar                 | `BottomBar.tsx`         | Side toggles moved to the top bar; **focus-mode** button (`ScanLine`) removed from view |
| Closed-workspaces pill     | `ClosedWorkspacesPill`  | Removed — the "closed workspace" concept is gone (REQ-NAV-8) |
| Top-bar icon cluster       | `TopBar.tsx`            | Home / Search / Settings / Help moved into the nav sidebar |

## Known simplifications (spike deviations from the spec)

- **Per-repo "+" in the nav sidebar** opens the New Workspace page but does not
  yet pre-select that repo (AddWorkspacePage takes no project param). (REQ-NAV-4)
- **Sidebar-collapsed and repo-group-collapse** persist **globally** rather than
  per-workspace (REQ-PERSIST-1) — the sidebar is global chrome. `navAtoms.ts`.
- **Active panel per zone** persists globally (the other per-workspace bits —
  section visibility, diff-open — are per-workspace via `usePerWorkspacePanelLayout`).
- The center split ratio (`diffPanelSplitRatioAtom`) is per-workspace via
  `usePerWorkspacePanelLayout`; the L/R/Bottom section sizes are global %
  (`sectionSizePercentAtom`), per REQ-PERSIST-2.
