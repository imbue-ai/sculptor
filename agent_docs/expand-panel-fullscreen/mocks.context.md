# Expand Panel to Fullscreen — Mock Context

## Description

Explore options for expanding a single workspace panel to fill the screen.
Today the compact workspace layout shows several panels at once (Left /
Center / Right + Bottom sections, each a uniform `PanelSection` with a tab
strip and header). We want a way to temporarily blow one panel up to (near)
full screen and a fast way back.

Requirements driving the exploration:

- **Focus panels with keybindings.** Per-panel focus shortcuts already exist
  (each panel has a `defaultShortcut`, e.g. Files ⌘P, Terminal ⌃`). We want
  the focused panel clearly indicated, and we may surface its focus hotkey in
  the panel header so it's discoverable.
- **Expand hotkey + close hotkey.** A hotkey maximizes the focused panel to
  fill the screen; a simple hotkey (Esc, or the same toggle) restores it.
- **An "expand" affordance.** Some icon in the panel header (a Maximize glyph)
  reveals the option for mouse users.
- **What does the expanded view look like?** The far-left nav rail must stay
  visible (never covered). The top workspace bar (branch / diff summary /
  panel toggles) may or may not be covered — this is the main axis the three
  variants explore.

## Variants explored (all in `mocks.html`)

- **Variant A — Maximize in grid.** The panel grows to fill only the panel
  grid region. Nav rail **and** top bar stay visible. Least disruptive; keeps
  all navigation chrome on screen.
- **Variant B — Immersive full-bleed.** The panel covers the top bar too —
  everything except the far-left nav rail. A slim floating exit pill is the
  only chrome. Most screen real estate; zen-like for deep diff/terminal work.
- **Variant C — Spotlight overlay.** The panel lifts into a large centered
  card over a dimmed backdrop (nav rail still visible beside it). A modal-style
  interaction: click the backdrop or press Esc to dismiss. Good for a quick
  peek without committing to a layout change.

## Decisions

- **Expanded view = Variant D (Immersive, tabs become the top bar).** A
  maximized panel fills everything except the far-left nav rail — it covers the
  workspace banner. Crucially, that covered banner space is **replaced by the
  maximized section's tab strip** (not left blank): if the section holds several
  panels, their tabs ride along the top so you can **switch panels without
  leaving the maximized view**. An exit control (`Esc` hint + restore glyph)
  sits at the right of that strip, where the banner's controls were.
- **Nav rail always stays visible** in the expanded view (never covered).
- **Expand hotkey = `⌃⌘F`** (mirrors the macOS native-fullscreen mnemonic) to
  maximize the focused panel. **`Esc` restores** (the restore glyph / `⌃⌘F`
  again also restore).
- **Focus hotkey badge is always visible** on each panel's tab in the header
  (e.g. `⌘3`) — most discoverable. One shortcut per panel (`⌘1`–`⌘6` in the
  mock); existing named shortcuts (`⌘P` Files, `⌃`` Terminal) still focus too.
- **Maximize affordance for mouse** = a `Maximize2` (⤢) icon at the right edge
  of the panel header; it swaps to a restore (⤡) glyph while expanded.

## Rejected Alternatives

- **Variant A — Maximize in grid.** Panel fills only the grid; nav rail + top
  bar both stay visible. _Reason: the user preferred the immersive treatment —
  more screen for the panel. Superseded by D._ Kept in `mocks.html`.
- **Variant B — Immersive full-bleed (plain).** Same immersive footprint as D,
  but the covered top-bar area is left blank. _Reason: D is strictly better —
  it reuses that area for the section's tab strip so you can switch panels while
  maximized._ Kept in `mocks.html`.
- **Variant C — Spotlight overlay.** Panel lifts into a centered card over a
  dimmed backdrop (modal "peek"). _Reason: a modal interaction is more than is
  wanted; the immersive maximize is simpler._ Kept in `mocks.html`.

## Open Questions

Resolved enough to spec; these are deferred design details, not blockers (the
user wrapped up the mock without requiring them):

- **Preserve banner context while maximized?** D's promoted top strip currently
  replaces the whole workspace banner. Decide whether to keep a slim bit of
  global context on its right (branch → main, +/− diff summary, Open PR) so it
  isn't lost while maximized. _Deferred — design during build._
- **Single-tab maximize look.** How maximizing a single-panel section (e.g. the
  agent or terminal) presents — its one tab as the top bar vs. a plain title.
  _Deferred._
- **Split sections.** Maximize should target just the focused half of a split
  section, and that half's tabs become the top bar. _Deferred — confirm during
  build._
- **Panel toggles / restore-layout control** in the promoted strip (mirroring
  the real banner's controls). _Deferred._
- **Relationship to existing focus/zen modes.** "Maximize panel" is distinct
  from `focus_mode` (⌘\, hides all panels to show chat) and `zen_mode` (⌘⇧\,
  hides chrome). Confirm it's a separate, composable action rather than folding
  into either.
- **`⌃⌘F` clash check.** Verify against existing bindings before implementing
  (`focus_mode` ⌘\, `zen_mode` ⌘⇧\, Find-in-file ⌘F — `⌃⌘F` is currently free).

## Tweaks Log

- Requested: Pick a direction; confirm expand hotkey; choose focus-badge prominence.
  Changed: Selected Variant A (Maximize in grid) as the direction; confirmed
  `⌃⌘F` to maximize + `Esc` to restore; kept the always-visible focus badge.
  Moved Variants B and C to Rejected Alternatives (kept in `mocks.html`).
  Marked A as the selected direction in the mock and labelled B/C as explored.
- Requested: "I actually like the immersive approach more — the top bar should
  instead become the panel section header, so if a section has multiple panels
  you can switch between them."
  Changed: Added **Variant D — Immersive, tabs become the top bar** as the new
  selected direction and switched the selection from A to D. Upgraded the mock so
  sections can hold multiple tabs (Left: Files + Commits; Right: Changes +
  Review) to demonstrate switching while maximized. In D's maximized state the
  section's tab strip is promoted to a full-width banner-like top bar (replacing
  the workspace banner) with an Esc/restore control on the right; the nav rail
  stays visible. A/B/C kept in `mocks.html` as exploration history; A and B moved
  to Rejected Alternatives (superseded by D).
