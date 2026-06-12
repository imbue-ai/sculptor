# Changes Panel Redesign — Mock Context

## Description

Explore variants of the workspace "Changes" panel (the diff/file-browser
panel). Today the panel header stacks three rows before the file tree
begins: a Files/Changes/Commits segmented control, an All/Uncommitted
segmented control, and a centered "Commit N changes" button.

Pain points from Bryden:

- The segmented control(s) take up a lot of space.
- The commit button underneath is weird — centered, and he never clicks
  it. It is still useful for first-time users, so it should stay
  discoverable without being prominent.
- The chrome around the file location (the breadcrumb header on the
  diff view) is fine — keep it as-is.
- The ⋯ overflow menu has a ton of options with seemingly random
  separator lines, including options that are no longer relevant
  (e.g. "Close" next to "Close tab").
- File-row hover should be visually consistent with the vertical nav
  sidebar's hover treatment (rounded corners, inset, translucent gray
  via `--gray-a3`, like `WorkspaceNavSidebar.module.scss`).

## Decisions

- The Files/Changes/Commits row is **panel-level chrome** ("the panel
  section row"). The All/Uncommitted scope picker belongs on its own
  row directly **under** it — never merged into the section row.
- Panel section switcher: the Files/Changes/Commits **segmented
  control stays** (it is NOT a dropdown), but **shrunk and
  left-aligned** instead of full width, with the add-panel "+" at the
  right end of the same row.
- Scope picker: A's text-toggle style — the selected option gets a
  subtle box (`--gray-a3`), the unselected option is plain text with
  no box. **No border** under the scope row.
- ⋯ overflow menu: Variant B's treatment — 7 top-level items; Copy
  path, Open in, and Close fold into submenus.
- Commit action: anchored to a footer at the bottom of the panel
  (from B), rendered as a plain button reading "Commit N changes" —
  **no icon**. Keeps the words visible for first-time users without
  occupying header space.
- File-row hover: sidebar-consistent treatment (rounded 6px, inset
  margins, translucent `--gray-a3`; active file uses `--accent-a3` +
  `--accent-11`) — from the original brief, applied in all variants.
- Diff-view breadcrumb chrome stays as-is (original brief).

## Rejected Alternatives

- Variant A's badged commit icon button — too implicit; the user wants
  the explicit "Commit N changes" wording.
- Merging the scope toggle into the panel section row (Variant A) —
  the scope picker must live under the section row.
- The commit-icon + text footer styling from Variant B — dropped the
  icon in favor of a plain button.
- Variant C ("tighten, don't rearrange") — passed over in favor of the
  A + B combination.
- Original centered "Commit N changes" row under the header — replaced
  by the footer placement.
- Replacing the Files/Changes/Commits segmented control with a view
  dropdown (Variant B's header) — agent misread the feedback; "the
  dropdown from Variant B" meant the ⋯ menu treatment. The segmented
  control stays.
- Border under the scope row — removed; the scope row sits borderless
  above the tree.
- Menu treatments A (labeled groups) and C (ruthless trim + ⌘K) —
  user chose B's submenus.

## Tweaks Log

- Requested: Combine A's All/Uncommitted text toggle, B's view
  dropdown, and B's commit footer — but drop the footer icon and make
  it a button that says "Commit N changes". Correction: the
  All/Uncommitted picker must sit on its own row UNDER the
  Files/Changes/Commits row, which is the panel section row.
  Changed: Added Variant D ("Combined — A + B synthesis") to
  mocks.html: section row = "Changes ⌄" dropdown + "+", scope row
  beneath with A-style toggle, footer = full-width plain "Commit 3
  changes" button. Menu left closed in D pending a menu-treatment
  decision.
- Requested: In Variant D, no border under All/Uncommitted, and
  Files/Changes/Commits is not a dropdown (it stays a segmented
  control). Menu treatment: Variant B.
  Changed: Variant D's section row now uses the Files/Changes/Commits
  segmented control + "+"; removed the border under the scope row;
  folded B's submenu-style ⋯ menu into D's frame (shown open with the
  Copy path submenu).
- Requested: Shrink the Files/Changes/Commits segmented control and
  left-align it instead of full width. Converged — wrap up.
  Changed: Variant D's segmented control now uses the small size,
  left-aligned with the "+" at the row's right end. Session closed
  with Variant D as the final direction.
