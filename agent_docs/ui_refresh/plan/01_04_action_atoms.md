# Task 1.4: Write-side action atoms + layout invariants

## Goal

Build the write-only Jotai action atoms that mutate the consolidated per-workspace
layout, with all the layout **invariants** enforced in one place. Keeping every
multi-field change behind these actions makes each mutation a single atomic
snapshot write (one debounced persist) and keeps the rules (center never collapses,
split self-heal, single-instance, active reassignment) consistent.

## Stories addressed

SEC-05..08 (collapse/expand; center can't collapse), SEC-10 (active section
constraints), SPLIT-03/04/05 (one split max; self-heal; close-split merge),
PANEL-07 (close removes panel), PANEL-15 (single-instance default), AGENT-04/
TERM-* (close last panel leaves section empty — see Decision B1).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the
workspace shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**Where this fits** (`supplemental/state_atoms.md` → "Write-side action atoms"):
all layout mutations go through write-only action atoms that update the
consolidated `workspaceLayoutAtom` (from Task 1.3). This keeps multi-field moves
atomic and centralizes the invariants.

**The invariants** (`supplemental/state_atoms.md` → "Invariants enforced inside the
actions", `goals.md` → "Collapsed vs. expanded" / "Split sections" / "Panels"):
- **Center never collapses** — `toggleSectionAtom` ignores `center`.
- **Active section must be expanded** — collapsing the section that holds the
  active sub-section reassigns the active sub-section (default: center's primary).
- **Split self-heal** — emptying a split *secondary* closes the split; emptying a
  split *primary* promotes the secondary's panels up and closes the split. Guard
  the reload window where a dynamic (agent/terminal) panel is assigned but its
  task/terminal source has not loaded yet — do **not** collapse/self-heal during
  that window.
- **Single-instance** — adding an already-open single-instance panel activates it
  in place instead of duplicating.
- **Closing the last panel** leaves the (non-center) section eligible to collapse
  per `goals.md`, and for center leaves the empty center showing the section empty
  state (Decision B1: empty, not auto-create).

This task depends on **Task 1.1** (`sectionTypes.ts` helpers) and **Task 1.3**
(`workspaceLayoutAtom` + slices). It also references the transient ring atoms from
**Task 1.5** for `jumpToSectionAtom` (sequence the two so 1.5's atoms exist, or
import lazily — see Gotchas).

## Files to modify/create

- `sculptor/frontend/src/components/sections/sectionActions.ts` — new. All
  write-side action atoms.
- `sculptor/frontend/src/components/sections/sectionActions.test.ts` — new. Vitest
  (table-driven invariant tests).

## Implementation details

Implement each action atom from `supplemental/state_atoms.md` → "Write-side action
atoms". Each reads the current `WorkspaceLayoutState` via `workspaceLayoutAtom`,
computes a new immutable snapshot, and writes it back once:

1. `movePanelAtom({ panelId, to: SubSectionId, index? })` — update `placement` +
   `order`; if `to` is a split half that doesn't exist, this is invalid (callers
   only target existing sub-sections). Maintain active panel if the moved panel was
   active in its source.
2. `openPanelAtom({ panelId, in: SubSectionId })` — set placement, append to order,
   set active. **Single-instance:** if a single-instance panel is already open
   anywhere, activate it in place (do not duplicate).
3. `closePanelAtom({ panelId })` — remove from `placement`/`order`/`activePanel`;
   pick a new active panel for that sub-section if needed; then apply
   **self-heal**: if the sub-section is a split half that is now empty, run the
   split-merge rules; if the section is now fully empty and non-center, it remains
   expanded-but-empty (shows empty state) unless caller collapses it. (The empty
   state itself is the component's concern; this atom only fixes data.)
4. `setActivePanelAtom({ panelId, in: SubSectionId })`.
5. `toggleSectionAtom({ section })` — flip `expanded[section]`; **no-op for
   `center`**. On collapse, if the active sub-section is in this section, reassign
   active to center's primary.
6. `splitSectionAtom({ section, panelId, axis })` — create `splits[section] =
   {axis, ratio: 0.5}` (reject if a split already exists — one split max), move
   `panelId` into the new secondary sub-section, set it active there. `axis` must
   satisfy `canSplitAxis(section, axis)` (Task 1.1).
7. `closeSplitAtom({ section })` — merge the secondary's panels back into the
   primary (preserving order), delete `splits[section]`, fix active sub-section if
   it pointed at the removed secondary.
8. `setSplitRatioAtom({ section, ratio })` — clamp to the split ratio bounds
   (`design_extraction.md` notes the prototype's 15–85% clamp).
9. `setActiveSectionAtom({ subSection })` — set `activeSubSection` **silently** (no
   ring pulse) — used by plain clicks (`goals.md` → "Active section").
10. `jumpToSectionAtom({ subSection })` — set `activeSubSection` **and** pulse the
    ring (bump the ring nonce from Task 1.5) — used by keyboard cycle / add / drop
    / workspace entry.
11. `removeWorkspaceLayoutAtom({ workspaceId })` — drop the family entry and call
    `layoutPersistenceAdapter.remove({kind:"workspace", workspaceId})` (workspace
    delete).

## Testing suggestions

- Vitest with a Jotai store: one test per invariant —
  - `toggleSectionAtom({section:"center"})` is a no-op.
  - collapsing the section holding the active sub-section reassigns active to
    center.
  - `splitSectionAtom` then emptying the secondary (`closePanelAtom`) auto-closes
    the split and merges back (self-heal); the "dynamic panel assigned but source
    not loaded" guard does **not** self-heal.
  - `openPanelAtom` for an already-open single-instance panel activates in place
    (no duplicate in `order`).
  - `splitSectionAtom` rejects a second split (one-split-max).
  - `setActiveSectionAtom` does not bump the ring nonce; `jumpToSectionAtom` does.
- Run `just test-unit-frontend`.

## Gotchas

- Every action writes the snapshot **once** (compute the full new state, then a
  single `set`). Multiple sequential writes would cause multiple persists and
  intermediate invalid states.
- The self-heal **reload guard** is subtle: during workspace load a dynamic panel
  id may be in `placement` before its task/terminal source atom has hydrated; don't
  treat that as "empty" and collapse the split.
- `jumpToSectionAtom` depends on the ring-nonce atom built in Task 1.5. **Define the
  nonce atom in Task 1.5 and import it here** — a forward reference within Phase 1 is
  fine (both land before any Phase-2 consumer); do not duplicate the atom.
- Decision B1: closing the last agent in center leaves it empty (do **not**
  auto-create a replacement here).

## Verification checklist

- [ ] All eleven action atoms present and writing single atomic snapshots.
- [ ] Center-never-collapses, active-reassignment, split self-heal (+ reload
  guard), one-split-max, and single-instance invariants are enforced and tested.
- [ ] `setActiveSectionAtom` silent vs. `jumpToSectionAtom` pulsing.
- [ ] Unit tests pass via `just test-unit-frontend`.
