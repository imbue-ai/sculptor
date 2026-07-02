# Task 3.5: AddPanelDropdown + EmptySectionState quick actions

## Goal

Build the section-header `+` **dropdown** for adding panels and finish the
`EmptySectionState` launcher (the ≤5 quick actions). Both reuse the prototype's
add-panel **row styling** but render as a dropdown (not the cmdk overlay).

## Stories addressed

PANEL-01 (`+` opens a dropdown; panels added land in that section), PANEL-02
(recent-agent pinned with its Cmd+Shift+T binding visible), PANEL-03 (agent-type
sub-menu), PANEL-04 ("New terminal" beneath the agent options), PANEL-05 (every
single-instance panel not already open listed below), PANEL-06 (new-agent binding /
Cmd+K always create the agent in center), PANEL-12 (Cmd+K → "Add panel" → location →
valid panels), SEC-19 (empty-state add button + ≤5 quick actions), TERM-05 (registered
terminal-agent programs surface in the agent-type sub-menu).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**The dropdown** (`goals.md` → "Adding a panel"; `supplemental/panel_registry.md` →
"Adding a panel"): each section header's `+` opens a **dropdown** with, in order:
"New {recent} agent" (recent agent type, Claude by default) with its **Cmd+Shift+T**
binding shown; a sub-menu to create an agent of a different type; "New terminal";
then **every single-instance panel not already open**. Panels added from a section's
dropdown are created **in that section**. But the new-agent binding **and** adding an
agent via Cmd+K always create the agent in the **center** section (center's primary
sub-section when split), regardless of the active section. There is **no bare
"Terminal" agent type** (Decision B2). Cmd+K also offers "Add panel" → choose
location → valid panels for that location (PANEL-12).

**Empty state** (`goals.md` → "Section empty state"; SEC-19): a centered add-panel
button (opens the same dropdown) plus up to five quick actions — always "New
{recent} agent" and "New terminal", then up to three most-recently-created-but-closed
panels. A split half's empty state also shows a "close split" option (Task 4.2).

**What to copy** (`design_extraction.md`): reuse the **item-row styling** from
`components/panels/AddPanelPalette.module.scss` (icon + title + "recently used"
pill) but render it in a **dropdown** (Radix DropdownMenu), **not** the cmdk
overlay. The empty-state shell is `components/panels/EmptyPanelLauncher.tsx` (built
as a shell in Task 2.4 — finish the quick actions here). The agent-type rows come
from the `ChooseAgentPage` rows in `AddPanelPalette.tsx`.

**Agents/terminals are not in the re-add list** (`panel_registry.md` → "Closing /
moving"): closing them ends them; only single-instance panels are offered again.

This task depends on **Task 1.4** (`openPanelAtom`/`movePanelAtom`), **Task 1.6**
(registry — which single-instance panels exist + which are open), **Task 2.4**
(`SectionHeader` `+` + `EmptySectionState` shell), and the agent/terminal creation
helpers (the new-agent/new-terminal actions — reuse today's create-agent/create-
terminal flows).

## Files to modify/create

- `sculptor/frontend/src/components/sections/AddPanelDropdown.tsx` + `.module.scss` —
  new (Radix dropdown, reusing AddPanel row styling).
- `sculptor/frontend/src/components/sections/EmptySectionState.tsx` — modify (from
  Task 2.4 shell): add the ≤5 quick actions.
- Cmd+K "Add panel" integration: extend the existing command-palette registration
  (grep the current Cmd+K/command-palette code) with an "Add panel" → location →
  panels flow.
- `sculptor/sculptor/constants.py` — add `ADD_PANEL_DROPDOWN`, `ADD_PANEL_NEW_AGENT`,
  `ADD_PANEL_AGENT_TYPE_SUBMENU`, `ADD_PANEL_NEW_TERMINAL`, `ADD_PANEL_PANEL_OPTION`,
  `SECTION_EMPTY_QUICK_ACTION` (then `just generate-api`).

## Implementation details

1. `AddPanelDropdown({ subSection })`: render the dropdown items in the order above.
   The single-instance list is "registered single-instance panels not currently
   open anywhere." Selecting a single-instance panel calls `openPanelAtom({panelId,
   in: subSection})` (lands in **that** section). "New terminal" creates a terminal
   in that section. "New {recent} agent" / agent-type sub-menu creates an agent —
   **always in center** (PANEL-06), regardless of `subSection`. Show the Cmd+Shift+T
   binding next to the recent-agent item (read from the keybindings registry, Task
   4.5).
2. Exclude agents/terminals from the single-instance re-add list (they are
   multi-instance; closing ends them).
3. Drop the bare "Terminal" agent type from the agent-type sub-menu (Decision B2);
   keep Claude / pi (gated) / registered terminal-agent programs.
4. `EmptySectionState`: centered add button (opens `AddPanelDropdown`) + up to five
   quick actions: always "New {recent} agent" + "New terminal", then up to three
   most-recently-created-but-closed panels (track a recent-closed list — a small
   transient/session list of recently closed single-instance panel ids). A split
   half also shows "close split" (Task 4.2 wires `closeSplitAtom`).
5. Cmd+K "Add panel" (PANEL-12): a submenu to pick a location (section/sub-section)
   then the valid panels for it; reuse the dropdown's item list logic.

## Testing suggestions

- PANEL-01..06/12 e2e land in **Task 3.7** (`test_panel_add_dropdown.py`, incl. the
  agent/terminal-type assertions — the file is owned there, co-developed with
  Sections); SEC-19 empty-state e2e in **Task 4.6** (`test_section_empty_state.py`).
  This task builds the surfaces + the `ADD_PANEL_*`/`SECTION_EMPTY_QUICK_ACTION`
  testids the POMs target.

## Gotchas

- It is a **dropdown**, not the cmdk overlay (reuse only the row styling).
- New agents always land in **center** even when opened from another section's `+`
  (PANEL-06) — easy to get wrong.
- Agents/terminals are **not** in the single-instance re-add list.
- No bare "Terminal" agent type (Decision B2).
- The recent-closed quick-action list must exclude currently-open panels and
  agents/terminals.

## Verification checklist

- [ ] `AddPanelDropdown` lists: recent-agent (+Cmd+Shift+T), agent-type sub-menu,
  New terminal, then single-instance-not-open; section-add lands in that section;
  new agents land in center.
- [ ] `EmptySectionState` shows the add button + ≤5 quick actions (+ close-split for
  split halves).
- [ ] Cmd+K "Add panel" → location → valid panels works.
- [ ] No bare "Terminal" agent type; agents/terminals absent from the re-add list.
- [ ] `ADD_PANEL_*` + `SECTION_EMPTY_QUICK_ACTION` ids added + `just generate-api`;
  `just check` passes.
