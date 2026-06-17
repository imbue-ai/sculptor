# File Browser Panel (Files / Changes / Commits) — Mock Context

## Description

Redesign the master-detail layout shared by the **Files**, **Changes**, and
**Commits** panels in the Sculptor workspace. Three changes:

1. **Fixed-width file tree.** Today the file viewer (detail) is stored as a
   *percentage* of the panel width and the tree flexes, so widening the whole
   panel scales both. Invert it: the tree gets a **fixed pixel width** (min
   200px) that stays constant when the panel resizes — only the viewer
   expands/contracts. Dragging the divider still re-sizes the tree.
2. **Header row above the tree** (41px, matching the diff viewer's file
   header). Drop the old "File browser" title. Files & Changes get an
   always-visible search input + action icons; Commits gets a branch summary +
   action icons.
3. **Hide/show-tree toggle.** A new control to collapse the tree so the viewer
   goes full-width. The placement of the *show* affordance (since hiding the
   tree also hides its header) is the main open question this mock resolves.

## Decisions

- Applies to **all three** panels (Files, Changes, Commits) via the shared
  `MasterDetailPanel`.
- **Tree = fixed pixel width**, `min 200px`; the **viewer flexes** to absorb
  panel resize. Drag still adjusts the tree width. (Persisted in px, not %.)
- Tree width persists **per-panel**, not shared across the three.
- **Drop the "File browser" title.**
- Header height **41px**, matching `DiffFileHeader` / the tab bar.
- **Breadcrumb stays in the viewer.** The viewer keeps its existing
  `DiffFileHeader` (breadcrumb + line stats + diff "…" menu). No hoisting the
  breadcrumb out of `DiffPanel` — keeps the build small. (Reversal of the earlier
  Variant-A decision.)
- **Layout (settled direction).** Two panes, each with its own 41px header:
  - **Tree header:** `[🔍 search] [… tree opts] [⛛ tree toggle]`. Search filters
    the tree live (Changes too). Commits has no search → header is just
    `[… collapse] [⛛ toggle]`.
  - **Diff header (the viewer's existing `DiffFileHeader`):** `[breadcrumb …]
    [+N −N] [⟳ refresh] [⋯ diff opts]`. **Refresh moved here**, next to the
    breadcrumb (it's the one tree action that lives on the diff side).
- **Toggle hops (Variant B behavior).** When the tree is open, the toggle is in
  the tree header. When collapsed, the tree (and its header) disappear and the
  toggle reappears **to the left of the breadcrumb** in the diff header; the
  viewer fills the panel.
- **Two separate "…" menus.** Tree "…": **Tree view / Flat list** + **Collapse
  all folders** (collapse-all-commits on Commits). Diff "…": the existing diff
  options (find-in-file, split/unified, wrap, render).
- **Toggle icon = `folder-tree`** (lucide FolderTree), NOT the panel-toggle
  glyph — already used for the section sidebars.
- **Files & Changes** tree header: `[🔍 search] [⟳ refresh] [… tree opts]
  [⛛ toggle]` (toggle position pending the B-vs-D choice). Search filters the
  tree live; wired for Changes too.
- **Commits**: no search row (not a file tree). The "N commits vs `main`" branch
  summary is dropped.

## Rejected Alternatives

- **Detail-as-percentage resize model** (current behavior) — rejected; it's the
  bug being fixed (both panes scale when the panel resizes).
- **Keeping the "File browser" title** — rejected; the always-on search input
  takes that space on Files & Changes.
- **One shared tree width across all three panels** — rejected; they're three
  separate panels, so each remembers its own width.
- **Search on the Commits panel** — rejected for now; Commits isn't a file
  tree.
- **Variant A — top bar spanning both panes with the breadcrumb hoisted up** —
  rejected. The user prefers the breadcrumb in the viewer; hoisting it would also
  mean refactoring `DiffPanel`'s header/view-options out into a shared bar (more
  invasive). Reverted to two side-by-side headers.
- **Variant C — collapsed rail** — rejected; costs a permanent sliver of width.
- **Panel-toggle glyph for the tree toggle** — rejected; already used for the
  section sidebars elsewhere in the app. Using `folder-tree` instead.
- **Branch-comparison summary on Commits** — dropped along with the Commits
  header row. (Was in the prior mock revision.)
- **Single combined "…" menu** (the A-era idea of one menu holding both tree and
  diff options) — rejected with A. Each pane keeps its own "…": tree opts on the
  tree header, diff opts on the viewer header.
- **Standalone collapse-folders icon** — dropped; its chevron glyph read
  ambiguously and it's low-frequency, so it lives in the tree-side "…" menu.
- **Flat-list / tree-view toggle as a standalone icon** — rejected; folded into
  the tree-side "…" menu.

## Open Questions

- **Commits' sparse header.** With no search, the commit-list header is just
  `[… collapse] [⛛ toggle]`. Acceptable, or move those into the diff header too?
- **Narrow-panel behavior** (spec/build detail). When the panel is too narrow to
  fit `200px tree + min viewer`, auto-collapse the tree (rely on the toggle)?

> Resolved: toggle home — Variant B behavior (tree header when open, left of the
> breadcrumb when collapsed). Variant E (toolbar row) and D (zone strip) rejected.
> Refresh lives in the diff header; search stays in the tree header.

> Resolved: the Commits "N commits vs `main`" branch summary is dropped (the user
> confirmed it's fine to lose) — see Rejected Alternatives.

## Tweaks Log

- Requested: "an icon not rendered properly — fix before continuing" (screenshot
  showed a giant white glyph bleeding over the Files panel header).
  Changed: the active tab's folder `<svg>` (and a few other icon SVGs) had no
  explicit size, so they rendered at the SVG default (~300×150). Added a default
  `.section svg { width:15px; height:15px }` rule (plus `.ztab svg` 14px) so
  every panel icon is sized; verified all five scenes render cleanly via
  headless-Chrome screenshots.
- Requested: "I like variant B; move refresh to the top header, drop the ⋯ from
  the file tree, use folder-tree for the toggle; for Commits drop the header."
  Changed: locked Variant B as the design and rebuilt the three main scenes:
  refresh + collapse moved to the zone tab strip; tree header reduced to search
  + a folder-tree tree-toggle; ⋯ removed; Commits header dropped (actions on the
  zone strip, commit list starts at top). Toggle now uses the `folder-tree`
  icon (not the panel glyph). Variants A and C kept and tagged "not chosen".
  Tentatively moved collapse to the zone strip and dropped flat-list — flagged
  in the mock for confirmation.
- Requested: "Ahh shit I meant variant A, the one with the extra header. Can we
  fix that?"
  Changed: switched the canonical design to **Variant A** and rebuilt all three
  scenes. An extra top header now spans both panes (below the zone strip): open-
  file breadcrumb on the left; refresh, collapse, diff "…" menu, and the
  folder-tree tree toggle (far right) on the right. The viewer's own breadcrumb
  header is removed (moved up); Files/Changes keep a slim search row in the tree;
  Commits has no search row. The toggle is uniform (top header) for all three.
  B and C demoted to "not chosen". Verified shown + hidden states via headless
  Chrome.
- Requested: "What's the collapse icon for? … [put flat-list] into the '…' menu."
  Changed: removed the standalone collapse icon (ambiguous glyph) and the
  flat-list toggle from the top header; both now live in the "…" view-options
  menu (Tree view / Flat list, Collapse all folders, + the diff options). Top
  header is now just refresh + "…" + tree toggle. Rendered the "…" menu open in
  the Files scene so its contents are visible.
- User confirmed the top header + "…" menu look right and to leave the Commits
  branch summary dropped → mock session wrapped up on Variant A.
- Requested (during implementation kickoff): "I like the breadcrumb where it is.
  Maybe we need to mock this." → **Reopened.** Reverted Variant A: the breadcrumb
  stays in the viewer's own header. Rebuilt the mock as **two side-by-side 41px
  headers** (tree header | viewer breadcrumb header), each with its own "…" menu.
  This also drops the invasive `DiffPanel` header refactor. Re-framed the toggle
  question as **B (tree header, hops to breadcrumb when hidden) vs D (zone tab
  strip, never moves)** and mocked both interactively. Verified Files + the B/D
  options (incl. B hidden state) via headless Chrome.
- Requested: "D crowds the '+' — make another variant that pushes everything into
  a dedicated file-header row and keeps it always visible."
  Changed: added **Variant E** — a full-width toolbar row below the tabs holding
  search + refresh + "…" + tree toggle, always visible. Rebuilt the three main
  scenes on E and added it as the lead option on the Toggle-home tab. The
  breadcrumb stays in the viewer; hiding the tree leaves the toggle in place and
  the viewer goes full-width. Verified shown + hidden states via headless Chrome.
- Requested: "E isn't it. Search stays in the file tree; refresh goes into the
  diff header with the breadcrumb; toggle in the tree when open, and to the left
  of the breadcrumb when collapsed."
  Changed: rebuilt all three scenes to that exact spec — search + tree "…" +
  toggle in the tree header; refresh + breadcrumb + diff "…" in the diff header;
  the toggle hops to the left of the breadcrumb on collapse. Replaced the
  options tab with a side-by-side "Collapse behavior" demo (open vs collapsed).
  Verified via headless Chrome.
- User **locked this design** (and confirmed Commits' sparse `[… collapse]
  [toggle]` header is fine) → moving to implementation.
