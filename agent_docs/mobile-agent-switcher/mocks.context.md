# Mobile Agent Switcher — Mock Context

## Description

Explore redesigns of the bottom **agent switcher** on the mobile Workspace view.

Today the switcher is `AgentPager`: centered pager dots (one per agent; the active
dot is elongated + accent-colored) plus a trailing dashed "new agent" dot. The dots
carry **no label** — the active agent's name lives in the header subtitle
("Agent 2 · code") next to the workspace title, which feels cramped.

Sculptor's model is **workspace → many agents** (unlike Claude Code, which has only
agents). The design direction is to free the header to show just the **workspace**,
and move the **agent identity down to the switcher**, where you actually switch
agents.

Constraints: mobile / narrow viewport, neutral dark theme (`accentColor: gray`,
`appearance: dark`) with green/amber/red status colors, `.mobileTheme` token layer
(`--mobile-surface-2` background now unified across header/chat/pager). The switcher
sits directly below the chat input. Must keep a new-agent affordance and scale
gracefully from 1 to several agents.

## Variants explored (exploration mode)

- **A — Dots + centered label.** Closest to today: pager dots (status-colored,
  active elongated) with the active agent's name centered beneath. New-agent = dashed
  dot. Lightest-touch.
- **B — Labeled segment strip.** Horizontally-scrollable chips, one per agent
  (status dot + short name), active chip highlighted, trailing "+" chip. Explicit,
  horizontal, name always visible per agent.
- **C — Current-agent bar → sheet.** A single full-width bar showing the active
  agent (status + name + count + chevron); tap opens a bottom sheet listing all
  agents with status/last-activity and a "New agent" row. Tiny dot peek above. Best
  for many agents.

## Decisions
- The full agent list lives in a **bottom drawer / sheet** (the part liked in C) —
  rows with status + last activity, plus a "New agent" row.
- The always-visible **current-agent picker must be minimal** — no status dots, no
  "n / 3" count. Ideally just the active agent's name.
- **Swipe** left/right switches between agents (the appeal of B); **tap** opens the
  drawer for the full list.
- Converged into **Variant D**: a minimal, swipeable agent-name picker that opens the
  liked bottom drawer.
- Picker shows **only the active agent's name** (no dots, count, neighbors, or hint),
  but is rendered as a **subtle pill with an always-visible ⌄** so it clearly reads as
  a tappable control (discoverability). Swipe the pill to switch agents; tap to open
  the drawer. New-agent lives in the drawer.

## Rejected Alternatives
- **A — dots + centered label**: dots-only with no swipe; user didn't like it.
- **B — segment strip (as tap-only chips)**: only interesting if swipeable; the
  swipe idea is carried into D, the static chip strip is dropped.
- **C — dot "peek" row**: unnecessary, removed.
- **C — heavy bar trigger** (status dot + name + count + chevron): too much; the
  picker should be more minimal.

## Tweaks Log
- Requested: don't like A/B/C as-is; like the bottom drawer but want a minimal
  current-agent picker (no dots like C) and the ability to swipe between agents (B).
  Changed: added **Variant D** — a minimal swipeable agent-name picker (no dots, no
  count) that opens the liked bottom drawer. Kept A/B/C in mocks.html under an
  "Earlier explorations" divider as a record.
- Requested: make the picker even more minimal.
  Changed: in Variant D, removed the peeking neighbor names (non-active names now
  fully transparent and cross-fade in only as they become centered) and removed the
  hint line — collapsed picker is now just the active name + a ⌄.
- Requested: "Where's the caret? How do users know they can press it?" — the bare
  caret was being clipped by the truncating name, and bare text wasn't discoverable.
  Changed: rebuilt the picker as a subtle **pill** (faint surface + hairline border)
  with the name + an always-visible ⌄ that can't be clipped, so it reads as a control.
  Swipe = drag the pill left/right (name slides + fades); tap = open the drawer.
