# Mobile Changes Pill — Mock Context

## Description

Redesign the mobile workspace's **Changes pill** (the card under the
header that today reads `⎇ Changes  +1 −0 · 1 file  ⌄` and expands a
floating file list). The redesign:

- **Restyle it like the status indicator** (`StatusPill`) — the compact,
  subtle pill chrome (`gray-1` surface, `gray-4` border, `radius-2`,
  `shadow-sm`, `font-size-1`) instead of the current larger card
  (`radius-4`, bigger padding, accent CTA).
- **Replace the "Changes" label with the PR button, then the file
  changes summary** — left = a plain **Create PR** button, right = the
  `+X −Y · N files` summary that toggles the list. **Drop the PR
  split-button popover** (the `Edit prompt…` chevron) — just a single PR
  button.
- **Center the pill** in its slot (it's compact now, not full-width).
- **Expanded list = the file-browser Changes tab, as a flat list** —
  reuse the `FlatListRow` look: `filename · dimmed/parent/path · spacer ·
  +X −Y · status letter (M/A/D/R)`, ~28px rows, no status badge boxes.
- **Add an All / Uncommitted toggle** (the `DiffScopePicker`
  `SegmentedControl`) at the top of the list. **Drop the commit button.**
- **Make "Review all" more subtle** — not the filled accent button;
  a quiet ghost/text affordance.

Built in the established mobile mock language (warm "sand" light theme,
phone frame, Lucide icons) to stay consistent with
`responsive-mobile-ui/mocks.html`.

## Decisions
- **Theme:** dark, to match the live app (the attached screenshot).
- **Pill chrome:** match the `StatusPill` indicator — `--surface` fill,
  hairline `--line` border, small radius (~`radius-2`), `--shadow-sm`,
  small text. Compact, centered, content-width.
- **Collapsed layout:** PR button on the **left**, file-changes summary
  (`+X −Y · N files`) + chevron on the **right**. Tapping the summary
  expands the list.
- **PR button:** a **soft** (filled-soft) button showing a **plus icon +
  "PR"** — drop the word "Create", drop the git-pull-request icon, drop
  the split-button `Edit prompt…` popover. Provider-aware label
  (PR / MR). Open-PR state shows `PR #482` + pipeline/review status dots.
- **Expanded list:** the file-browser **Changes tab as a flat list**
  (`FlatListRow`: name · dimmed parent path · `+/−` · colored status
  letter M/A/D/R), ~28–30px rows, no status badge boxes.
- **All / Uncommitted toggle:** `DiffScopePicker` segmented control at the
  top of the panel. **Commit button removed.**
- **Review all:** subtle ghost text affordance (gray text + layers icon)
  at the foot — not the filled accent CTA.

## Rejected Alternatives
- **Sand light theme** — used in the first pass to match
  `responsive-mobile-ui/mocks.html`; rejected in favor of dark to match
  the live app screenshot.
- **"Create PR" full label with git-pull-request icon** — replaced by the
  soft `+ PR` button (plus icon + "PR").
- **Flip order (changes-left, PR-right)** and **PR icon-only** — not
  chosen; PR stays left, labeled.

## Tweaks Log
- Requested: Initial generation.
  Changed: Built the redesign mock — StatusPill-style centered bar
  (Create-PR + changes summary), flat-list expansion with All/Uncommitted
  toggle, subtle Review-all. (Sand theme, first pass.)
- Requested: Switch to dark theme; PR as a soft button with just a plus
  icon + "PR" (drop "Create").
  Changed: Converted the whole mock to a dark palette; reworked the PR
  button into a soft filled button with a plus icon and "PR" label
  (PR/MR provider-aware), removed the inter-segment divider.
