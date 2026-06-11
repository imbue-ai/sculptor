# Responsive Panel Sizing

## Overview

When the available screen space changes — resizing the app window,
switching between monitors of different sizes, or using a window manager
(e.g. macOS "magnet" / Rectangle to snap the window to half the screen) —
the workspace panel layout doesn't hold up well. Panels end up at awkward
sizes, content gets pushed off-screen, and small screens surface odd edge
cases. The result is a layout the user has to re-fix by hand every time
their screen size changes, and on small screens it's sometimes hard to
recover from at all.

**Current state (from the code).** The live workspace layout is
`CompactLayout`, and it already stores the main section sizes (left /
right / bottom) as **percentages of the window**, shared globally across
workspaces (`sectionSizePercentAtom`). The older pixel-based
`DockingLayout` is now legacy / test-only. So the headline "switch from
pixels to percentages" is largely already done in the live layout — which
means the real, remaining pain lives at the **edges**:

- **Pixel floors and center-protection.** Sections have a `150px` floor
  and the center has a pixel minimum; when the window is narrow these
  fight the percentages, squeezing or overflowing content rather than
  degrading gracefully.
- **No auto-collapse / auto-restore.** When the window gets too small to
  fit a panel, nothing hides it cleanly — and there's no notion of
  bringing it back when space returns. (The legacy layout collapsed
  one-way and never restored — likely the root of the "snap to half
  screen and my panels are gone for good" complaint.)
- **Round-trip fidelity.** Shrinking then re-growing the window (or
  snapping out and back) should return to the user's original
  arrangement, not a degraded one.
- **Global vs. per-workspace / per-screen-size sizing.** Sizes are global
  today; it's unclear whether a comfortable split on a big monitor should
  carry to a laptop screen unchanged.

The goal is to make the panel layout **resilient** to changes in
available space and to handle awkward small-screen situations gracefully
**on behalf of the user**, rather than leaving them to clean it up
manually.

How far to take this is an open question: a lighter-touch fix (robust
percentage sizing + smart min/max + auto-collapse/restore) versus a more
ambitious system that adapts the *arrangement* to screen size (related to
the separate named-"Layouts" effort in
`agent_docs/workspace-layouts/`). The user has flagged that the fully
adaptive approach might be over-engineering.

This is a UI / frontend change to the workspace panel layout system
(React frontend under `sculptor/frontend/src/components/panels/`).

## User Scenarios

(TBD — clarifying in Q&A)

## Requirements

(TBD — clarifying in Q&A)

## Non-Goals

(TBD — clarifying in Q&A)

## Open Questions

> **Status: PAUSED.** The user has in-progress code changes on this
> branch and asked to resume the spec Q&A once those land. The two
> goals questions below are queued to be re-asked on resume.

- **Ambition level.** When available space changes (resize /
  snap-to-half / smaller monitor), what's the ideal end state?
  - *Resilient sizing* — panels scale proportionally; a panel that no
    longer fits is auto-hidden and auto-restored when space returns;
    same arrangement.
  - *Adaptive arrangement* — also change which panels are shown / how
    they're arranged on small screens (overlaps named-Layouts).
  - *Minimal cleanup* — finish percentage-based sizing + sane min/max
    only; no auto hide/restore or adaptation.
- **Scope vs. the named-Layouts effort.** Sizing-resilience only, light
  adaptation (e.g. auto-hide a side on very small screens), or full
  screen-size-driven layout switching?
- **Round-trip fidelity.** After shrinking then re-growing the window
  (or snapping out and back), must the layout return exactly to the
  user's prior arrangement?
- **Global vs. per-workspace / per-screen-size sizing.** Should a split
  tuned on a large monitor carry unchanged to a laptop screen?

(TBD — resuming Q&A after in-progress code changes land.)
