# Task 4.2: Split sections — create, direction rules, close, self-heal UI

## Goal

Wire the split UI on top of the split action atoms: the right-click "Create
{direction} split and move panel" option with per-section direction rules, the
one-split-max constraint, the empty-split-half empty state, and the close-split
affordance.

## Stories addressed

SPLIT-01 (right-click panel → "Create {direction} split and move panel"; the panel
moves into the new sub-section), SPLIT-02 (direction set per section), SPLIT-03
(one split max), SPLIT-04 (split remains when a half empties; empty half shows the
section empty state), SPLIT-05 (close split from the empty state → merge back),
SPLIT-06 (maximized split shows one sub-section — coordinated with Task 4.3).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**Split behavior** (`goals.md` → "Split sections"; `state_design.md` → "Sections and
sub-sections"): a section splits into exactly two sub-sections (one split max).
Splitting is via right-clicking a panel and choosing "Create {direction} split and
move panel" — the chosen panel moves into the new sub-section. Directions depend on
the section: left/right split **top/bottom** (axis `horizontal`), bottom splits
**left/right** (axis `vertical`), center supports **either**. A split remains after
its sub-section empties (the empty half shows the section empty state); it is closed
from an option on that empty state, after which remaining panels merge back into one
section.

**The atoms already exist** (Task 1.4): `splitSectionAtom`, `closeSplitAtom`,
`setSplitRatioAtom`, and `allowedSplitAxesForSection`/`canSplitAxis` (Task 1.1). This
task is the **UI wiring**: the context-menu option, the direction label mapping, and
the empty-state close-split button.

**Direction labels:** map (section, axis) → the user-facing direction word for the
menu label, e.g. center + horizontal → "bottom" (or "top"), left/right + horizontal
→ "bottom"/"top", bottom + vertical → "right"/"left". Define this mapping here (it
drives the SPLIT-01 label "Create {direction} split and move panel").

This task depends on **Task 1.4** (split atoms), **Task 2.4** (`PanelSection`/
`SectionHeader` for the panel context menu + the split divider via `SplittableSection`),
and **Task 3.5** (`EmptySectionState` — add the close-split button).

## Files to modify/create

- `sculptor/frontend/src/components/sections/SplittableSection.tsx` — modify: render
  the split divider (`ResizeHandle` on the split axis) and the two sub-sections
  (already scaffolded in Task 2.4; confirm ratio + axis behavior).
- The panel tab/right-click **context menu** (in `SectionHeader.tsx` / `PanelTab`):
  add the "Create {direction} split and move panel" item(s), enabled only for
  allowed axes and only when no split exists (one-split-max).
- `sculptor/frontend/src/components/sections/EmptySectionState.tsx` — modify: show
  the "close split" button when the empty pane is a split half (calls
  `closeSplitAtom`).
- `sculptor/frontend/src/components/sections/splitDirection.ts` — new: the
  (section, axis) → direction-label mapping + the allowed-direction list per section.
- `sculptor/sculptor/constants.py` — `SPLIT_CREATE_OPTION`, `SPLIT_CLOSE_OPTION`;
  `just generate-api`.

## Implementation details

1. Add the panel right-click context-menu item(s) "Create {direction} split and move
   panel". Compute the available directions from `allowedSplitAxesForSection(section)`
   + the label mapping; disable / omit when a split already exists (SPLIT-03).
   Selecting it calls `splitSectionAtom({section, panelId, axis})` — the panel moves
   into the new secondary sub-section.
2. `SplittableSection` renders primary + `ResizeHandle` (split axis, writing
   `setSplitRatioAtom`, clamp 15–85%) + secondary, choosing stacked (horizontal) vs
   side-by-side (vertical).
3. When a split half empties, it shows `EmptySectionState` (the split stays —
   SPLIT-04); the empty state shows a **close-split** button (SPLIT-05) calling
   `closeSplitAtom` (merges the remaining panels back, Task 1.4 handles the data).
4. SPLIT-06 (maximized split shows one sub-section) is implemented in **Task 4.3**
   (maximize) — coordinate so a maximized split renders only one half.
5. The self-heal data rules (emptying a half auto-closes; reload guard) are already in
   `closePanelAtom` (Task 1.4) — this task only reflects them in the UI.

## Testing suggestions

- SPLIT-01..06 e2e land in **Task 4.6** (`test_section_splits.py` +
  `test_section_empty_state.py` for the close-split affordance) via the
  `section_split.py` POM (`create_split`, `get_subsection`,
  `close_split_from_empty_state`, `assert_directions_available`).

## Gotchas

- Direction labels are section-dependent — get the mapping right (left/right →
  top/bottom; bottom → left/right; center → either).
- One split max — disable the create-split option when a split exists.
- The split **stays** when a half empties (SPLIT-04); only the empty-state
  close-split button removes it.
- Don't duplicate the self-heal data logic — it lives in `closePanelAtom`.

## Verification checklist

- [ ] Right-click panel → "Create {direction} split and move panel" with correct
  per-section directions; panel moves into the new half.
- [ ] One-split-max enforced in the UI; split divider resizes with clamp.
- [ ] Empty split half shows the empty state with a close-split button that merges
  back.
- [ ] `SPLIT_CREATE_OPTION`/`SPLIT_CLOSE_OPTION` ids added + `just generate-api`;
  `just check` passes.
