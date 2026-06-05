# Uniform Panels (compact workspace layout — iteration 2)

## Overview

This builds directly on the compact-workspace-layout spike
(`agent_docs/compact-workspace-layout/spec.md`, implemented on branch
`bryden/build-compact-layout`). That iteration still treats three things as
**special cases** that live outside the panel/section model:

- **The Center content (chat)** — a bespoke region, not a panel section.
- **The diff/file viewer** — opens as a center split rather than inside the
  panel that triggered it.
- **The terminal** — pinned to the Bottom zone only, not addable elsewhere.

The driving idea of this iteration: **everything is a panel.** Chat (agents),
the terminal, and the file/diff viewers are all panels that live in panel
sections, are added via a section's "+", and share the same tab-strip
treatment. Removing the special-casing should make the layout simpler and more
flexible (any content in any section).

Key shifts (rough — to be sharpened in Q&A):

- **In-panel diff/file viewer.** Opening a file from the Files / Changes /
  Commits panels shows the diff/file viewer **inside that panel**, not in the
  center split.
- **Agents are panels.** Agent chats become panels; a new agent can be created
  in any section.
- **Terminal is a panel.** The terminal works like agents — addable to any
  section, no longer Bottom-only.
- **Center becomes a panel section.** The center is just another section, so
  the agent tabs move to the **top** of the section (matching the other tab
  strips).
- **Drop the dedicated chat split.** Remove the special second-agent pane
  (`SecondaryChatPane` / `secondChatAgentId`) for now — side-by-side chats fall
  out naturally from agents-as-panels.
- **Tab-strip position setting.** An experimental setting controls whether a
  panel section renders its tab strip at the **top** or **bottom**.

This is a continuation of the spike (functional prototype), not production
hardening. It will be handed off to a fresh agent for implementation.

## User Scenarios

### Opening a file's diff in-panel
The user selects the **Changes** panel and clicks a changed file. The panel
shows a **master-detail split** — the changes list and the selected file's diff
together, inside the panel — rather than opening a center split (REQ-DIFF-1/2).
The same applies to **Files** (file viewer) and **Commits** (commit file diff).

### Creating an agent in a section
The user clicks **+** on a section and chooses **New Agent**. A new agent tab
appears in that section's tab strip and becomes active (REQ-AGENT-2). Agent tabs
sit at the **top** of the section, like the Files/Terminal tab strips
(REQ-AGENT-3).

### Comparing two agents (no special split)
The user opens one agent in the Center section and a second agent in the Right
section — each is just a tab in its section. Two chats appear side-by-side with
no dedicated chat-split machinery (REQ-AGENT-4).

### Terminal in any section
The user clicks **+** on the Right section and adds **Terminal**; it renders in
that section. The Bottom zone is now a generic section too (REQ-TERM-1/2).

### Flipping tab strips to the bottom
The user toggles the experimental **Tab strip position** setting to *Bottom*;
every section now renders its tab strip at the bottom (REQ-SET-1).

## Requirements

### Uniform panel model (REQ-PANEL-*)
- **REQ-PANEL-1:** The Center MUST be a normal panel section, rendered by the
  same component as the Left / Right / Bottom sections — no bespoke center
  content, no `CenterPanes`-style 2-pane split.
- **REQ-PANEL-2:** A section's tab strip MAY hold any mix of panels and agents.
- **REQ-PANEL-3:** The full-width top bar's section toggles MUST reflect the
  Left / Right / Bottom sections (the old terminal-specific toggle becomes a
  Bottom-section toggle), since the terminal is no longer a special zone.

### Agents as panels (REQ-AGENT-*)
- **REQ-AGENT-1:** Each agent (task) MUST be representable as its own tab in a
  section's tab strip.
- **REQ-AGENT-2:** A section's **+** MUST offer **New Agent** (creates a fresh
  agent here) plus a list of existing agents that are **not currently open** in
  any section; selecting one opens it in this section.
- **REQ-AGENT-3:** Agent tabs MUST render at the top of the section by default
  (matching the other tab strips), replacing today's below-the-chat `AgentTabs`
  strip.
- **REQ-AGENT-4:** The dedicated chat-split pane (`SecondaryChatPane` /
  `secondChatAgentIdAtomFamily`) MUST be removed; side-by-side chats are achieved
  by opening agents in different sections.
- **REQ-AGENT-5:** An agent MUST be **single-instance** — open in at most one
  section at a time. Relocating an agent to another section MUST be supported
  (move), never duplicated.

### Single-instance panels (REQ-INST-*)
- **REQ-INST-1:** Every panel (Files, Changes, Commits, Review All, Terminal,
  each agent, …) is single-instance: it lives in exactly one section at a time,
  and adding it to another section **moves** it (matches the current
  zone-assignment model). The "+" of a section only lists panels/agents not
  already open in that section.

### In-panel diff / file viewer (REQ-DIFF-*)
- **REQ-DIFF-1:** Opening a file from Files / Changes / Commits MUST show the
  diff/file viewer **inside that panel** as a master-detail split, not in the
  center.
- **REQ-DIFF-2:** The split MUST be **side-by-side** — the list on the left, the
  selected file's diff on the right — with a **resizable** divider between them.
- **REQ-DIFF-3:** The viewer MUST show **one file at a time** (a single detail
  pane); selecting another file updates the detail in place.
- **REQ-DIFF-4:** The Center MUST no longer host a diff/file viewer or a 2-pane
  split (the center `diffPanelOpenAtom` behavior, `CenterPanes`, and the
  single-file center `DiffPanel` are removed).

### Terminal as a panel (REQ-TERM-*)
- **REQ-TERM-1:** The terminal MUST be a panel addable to **any** section (no
  longer Bottom-only; drop the `BOTTOM_ONLY_PANEL_IDS` restriction).
- **REQ-TERM-2:** Each terminal MUST be its **own panel** — drop the internal
  multi-terminal tab strip; a section's **+** offers **New Terminal** (and lists
  existing not-currently-open terminals), parallel to agents (REQ-AGENT-2).
  Terminal panels are single-instance (REQ-INST-1).
- **REQ-TERM-3:** The Bottom zone MUST become a **generic section** accepting any
  panel.

### Tab-strip position setting (REQ-SET-*)
- **REQ-SET-1:** A **global** experimental setting (Settings → Experimental) MUST
  control whether section tab strips render at the **top** or **bottom**; default
  **top**.

### Default layout (REQ-DEFAULT-*)
- **REQ-DEFAULT-1:** On first load: **Left** = Files / Changes / Commits (Files
  active); **Center** = the default agent; **Right** = empty/collapsed; **Bottom**
  = the Terminal panel, collapsed. (Bottom is a generic section that simply starts
  with the terminal in it.)

## Non-Goals

- Per-section tab-strip position (global only for now).
- Chat split as a dedicated feature — removed; side-by-side emerges from sections.
- Production hardening / backward-compat with the previous iteration.

## Open Questions

- The **mechanism** for moving an already-open agent/terminal to another section
  (drag the tab across sections vs close-and-reopen). Single-instance is decided
  (REQ-AGENT-5 / REQ-INST-1); the exact move gesture is a detail for architecture.
- **Persistence of dynamic panels.** Agents/terminals are per-workspace and
  created at runtime — how their section placement persists (vs the static
  registry panels) is an architecture detail.
