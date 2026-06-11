# Add Panel Launcher — Mock Context

## Description

Explore better ways to **add a panel** to a section in the compact /
uniform-panels workspace layout. Today a section's `+` opens a plain Radix
`DropdownMenu` (New Agent / New Terminal / existing agents / existing
terminals / static panels), and an empty section shows a vertical stack of
launcher cards (`EmptyPanelLauncher`). Both flat-list a growing set of
panels with no search and no keyboard navigation.

The rough idea: a **cmd+k-like picker** for choosing which panel to add —
either as a centered overlay window, or embedded directly into the section.

### Design considerations (from the user)
- **Search** — there may be many panels (8 static panels today, plus one
  panel per agent and per terminal), so the picker needs to filter.
- **Keyboard navigation** — arrow up/down through options, Enter to add.
- **Restoring / moving existing terminals & agents** — agents and terminals
  are single-instance per workspace. "Adding" one that already exists really
  means *moving* it into this section (or restoring a closed one). Today this
  is an undifferentiated list item; we want a clearer model.

### What the app already gives us
- A full Raycast-style command palette (`components/CommandPalette`, built on
  `cmdk`) — opaque panel, top search input, hairline divider, grouped list,
  rows with icon + title + muted subtitle + trailing kind/shortcut, subtle
  gray selection highlight, built-in arrow-key nav. This is the visual anchor.
- Panel definitions carry `displayName`, `description`, `icon`, and
  `defaultShortcut` — everything a rich picker row needs.
- `useAddPanelMenu(zone)` already exposes exactly the data a picker needs:
  `staticPanels`, `existingAgents`, `existingTerminals`, `openPanel(id)`
  (= move into this zone), `createAgent()`, `createTerminal()`.

## Decisions
- **Chosen direction: the modal cmd+k palette (Variant A), refined → tab "A★".**
  A centered overlay, opened from the section `+` or the global ⌘K. Reuses the
  Raycast/cmdk style the app already ships.
- **Scope pill stays.** The "Add to <Section>" pill on the right of the input is
  liked and kept. It doubles as the destination selector ("Add to … ▾").
- **Open existing / Restore closed are sub-pages, not inline groups.** The top
  level stays short (Create · Panels · two drill-in rows). Selecting a drill-in
  row navigates to a breadcrumb sub-page ("Add panel ▸ Open existing" /
  "▸ Restore closed") with the relevant list. ⌫ / esc goes back.
- **Panel options appear in the main ⌘K too.** Add-panel entries (New agent/
  terminal, the static panels, and the two drill-in rows) show up among the
  global command-palette results, grouped under "Add panel".
- **Destination model = Option C (context-dependent).**
  - Opened from a section's `+`: the "Add to <Section> ▾" pill is **pre-filled**
    with that section and is a **changeable inline dropdown**.
  - Opened from the global ⌘K: the destination pill is **empty** (a quiet ghost
    "Add to…"). Choosing a panel to add then opens a **separate "choose section"
    window** where you pick the location.
- **Destination wording — natural, no phantom splits.** Each section appears
  **once** ("Left / Center / Right / Bottom"). A section expands into halves
  **only when it's actually split**, using natural names — "Top right" /
  "Bottom right" — never "Right — top". When nothing is split, no halves show
  anywhere.
- **New empty-section state.** A **Quick add** of up to **5** options chosen
  from what's *popular* and *not already open* (a curated default set, NOT a
  literal recents history), laid out as a **left-aligned list** (Option A,
  chosen over the tile grid), **plus a clear button to open the full ⌘K
  picker**. No misleading ⌘K shortcut hint. The section header's `+` remains a
  second way in. The button treatment is the **"Browse all panels" button**
  (chosen over a search-box affordance and an "All panels…" list row; see A★
  state 2).
- **Casing.** Section names are **capitalized as standalone labels** (menu
  items, location-window rows: "Top right") but **lowercased inside a sentence**
  (pill / placeholder: "add to the top right section").
- **Move/restore model (carried from A).** Existing agents/terminals show where
  they currently live (location chip) and offer **Move here / Reveal** rather
  than silently duplicating; closed items offer **Restore here**.

## Open Questions
(Carried into the spec — not blocking the mock.)
- **Quick-add ranking.** Exact rule for the 5 defaults — weighting of
  "popular" vs "not already open"; whether it's per-workspace or global; any
  manual pinning.
- **Location-window keyboard entry.** When the empty-destination ⌘K has a panel
  selected, what key opens the location window — `↵` (then the window handles a
  second `↵`), or a distinct key? And does the window support its own search.
- **Sub-page back affordance.** esc-to-back vs an explicit back arrow in the
  breadcrumb vs ⌫ on empty query.

## Rejected Alternatives
- **B · Embedded section palette** — set aside. The user prefers a modal that
  can also be opened globally; the empty section instead gets the dedicated
  "Add panel button + Recents" state rather than a full inline palette.
- **C · Anchored popover** — set aside in favor of the centered modal (A) for
  consistency with the existing command palette.
- **D · Standalone segmented palette** — superseded by A★, which folds in D's
  best ideas (Open-existing / Restore as their own surfaces, Recents) using
  drill-in sub-pages instead of an always-visible segmented control.
- **Empty state — tile grid (Option B)** — set aside in favor of the
  left-aligned list (Option A). Tile grid kept in `quickTiles()` for reference.
- **Open-picker affordance — search box / "All panels…" row** — set aside in
  favor of the explicit **"Browse all panels" button** in the empty state.

## Tweaks Log
- Requested: Initial exploration (4 directions for adding a panel).
  Changed: Built Variants A (modal), B (embedded), C (popover), D (location-aware),
  all in the app's cmdk/Raycast style; verified rendering in Chromium.
- Requested: Go with A; make Open-existing / Restore into sub-pages; keep the
  "Add to <section>" pill; answer how a naive ⌘K open picks the destination
  (keyboard-selectable target, handle split sections); new empty-section state
  with a clear Add-panel button + Recents; surface panel options inside ⌘K.
  Changed: Added tab "A★ refined" (now the default) with 6 states — new
  empty-section state, top-level palette from the `+`, Open-existing sub-page,
  Restore-closed sub-page, naive global ⌘K with panels among commands, and the
  target menu expanding split sections. Recorded B/C/D as set aside.
- Requested: Use Option C for the destination (from-panel = changeable inline
  dropdown; from-⌘K = empty pill that opens a separate location window on add);
  make the empty state more minimalist with "Quick add" = 5 popular/not-open
  defaults (not a literal recents history) and a lighter Add-panel button; fix
  some icons rendering far too large.
  Changed: Added a global svg sizing safety-net (fixes oversized icons across
  all tabs). Reworked A★ to 7 states: minimalist empty state (light button +
  Quick add), top-level from `+`, inline changeable destination dropdown,
  Open-existing & Restore sub-pages, global ⌘K with an empty destination pill,
  and a dedicated "Add <panel> to…" location window listing sections incl.
  split halves.
- Requested: Edge cases & polish — don't show halves when nothing is split;
  natural wording ("Top right section") for splits; drop the misleading ⌘K
  hint; drop the empty-state Add-panel button since the header `+` already adds
  panels; and fix the odd alignment of Quick add.
  Changed: Destination lists now show each section once and expand only a truly
  split section into natural "Top right" / "Bottom right" (new no-split vs split
  states). Empty state is now Quick-add only (no button, no shortcut) with the
  section header `+` highlighted as the entry point, plus a polish-options state
  comparing a left-aligned list vs a tile grid. A★ is now 9 states.
- Requested: Chose the left-aligned list (Option A); bring back a clear button
  somewhere to open ⌘K (the "All panels…" was too quiet) and show more variants
  of it; drop section-name casing when it appears in a sentence.
  Changed: Empty state now = Quick add (Option A list) + a clear "Browse all
  panels" button; added a state comparing three open-picker treatments (search
  box / Browse-all button / "All panels…" row). Lowercased section names in the
  pill + placeholder ("add to the right / top right section") while keeping menu
  and location-window labels capitalized. Recorded the tile grid as set aside.
- Requested: Chose the "Browse all panels" button for opening ⌘K; wrap up.
  Changed: Marked the Browse-all button as the chosen open-picker treatment in
  A★ (state 1 uses it; state 2 keeps the alternatives as history). Finalized the
  context — moved resolved choices into Decisions, set-aside options into
  Rejected Alternatives. Mock session complete (not committed).
