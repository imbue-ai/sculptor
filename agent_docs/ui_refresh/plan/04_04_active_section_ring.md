# Task 4.4: Active section selection + the rebuilt ~2s ring fade

## Goal

Implement active-section selection (last interacted; click vs. cycle) and rebuild the
~2-second highlight-ring fade as a clean hook, keeping the ring a per-section
concern so the fade never re-renders other sections.

## Stories addressed

SEC-10 (active section = last interacted via click or cycle; a collapsed section
cannot be active; defaults to center on load), SEC-11 (on cycle and on workspace
load, the active section is briefly ring-highlighted, fading within ~2s), SEC-12
(cycle steps between sections including split sub-sections — the binding is Task 4.5;
the selection logic lives here).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**Active section vs. the ring** (`goals.md` → "Active section"; `state_design.md` →
"Active section and the highlight ring"): the **logical** active sub-section persists
(Task 1.3 `activeSubSectionAtom`) — re-entering a workspace restores where the user
was. The **ring visibility** is transient (Task 1.5) — it flashes on a deliberate
jump (keyboard cycle, add/drop, workspace entry) and fades within ~2s. A **plain
click** sets the active section **without** flashing the ring (`setActiveSectionAtom`,
silent); a **jump** sets it and pulses the ring (`jumpToSectionAtom`, bumps the ring
nonce). A collapsed section cannot be active; on load it defaults to center.

**Rebuild the timing** (`design_extraction.md` → "Do not copy": the focus-ring timing
logic is brittle — rebuild it; keep only the CSS treatment, already copied in Task
2.4). The ring CSS (`.focused`/`.ringVisible::after`, 1px `--accent-9`, opacity fade)
is on `PanelSection`. `RING_VISIBLE_MS = 2000` (Task 1.5).

This task depends on **Task 1.4** (`setActiveSectionAtom`, `jumpToSectionAtom`),
**Task 1.5** (ring atoms + `RING_VISIBLE_MS`, `isRingVisibleAtom`), and **Task 2.4**
(`PanelSection` ring CSS + per-ss `isRingVisibleAtom` subscription).

## Files to modify/create

- `sculptor/frontend/src/components/sections/useActiveSectionRing.ts` — new: the fade
  timer hook.
- `sculptor/frontend/src/components/sections/PanelSection.tsx` — modify: click sets
  the active section silently; ensure ring CSS is gated on `isRingVisibleAtom(ss)`.
- Wire `jumpToSectionAtom` callers: workspace entry (Task 6.2 calls it on load),
  add/drop (Task 3.5/4.1), and cycle (Task 4.5). This task provides the hook + the
  click path.

## Implementation details

1. **Click → silent active:** clicking anywhere in a `PanelSection` body/header calls
   `setActiveSectionAtom({subSection: ss})` (no ring pulse). A collapsed section
   can't be clicked active (it isn't rendered as a section box; expanding it is the
   path).
2. **Jump → active + ring:** `jumpToSectionAtom({subSection})` (Task 1.4) sets active
   and bumps `activeSectionRingNonceAtom`. Callers: keyboard cycle (Task 4.5),
   add-panel/drop (Task 3.5/4.1 — pulse the target), and workspace entry (Task 6.2).
3. **The fade hook** `useActiveSectionRing`: subscribe to
   `activeSectionRingNonceAtom`; on each bump, set `activeSectionRingVisibleAtom =
   true` and start a `RING_VISIBLE_MS` timer that sets it back to false; clear/reset
   the timer on a new bump. Mount this hook once at the shell level
   (`WorkspaceLayoutShell`). Because only `activeSectionRingVisibleAtom` flips and
   `isRingVisibleAtom(ss)` is per-ss, only the active section re-renders for the fade.
4. **Default on load / collapse:** active defaults to center's primary when nothing
   qualifies (Task 1.3/1.4 already reassign on collapse); confirm load sets center
   when `activeSubSection` is null.

## Testing suggestions

- SEC-10..12 e2e land in **Task 4.6** (`test_section_active_and_maximize.py`):
  clicking a section makes it active **without** a ring flash; the cycle hotkey
  pulses the ring and it fades within ~2s; a collapsed section can't be active;
  default center on load. The ring *fade visual* is screenshot-verified; the
  active-state and ring-visible attribute toggles are behavioral (assert
  `SECTION_ACTIVE_RING` visibility/`data-ring-visible`).

## Gotchas

- Keep the ring **visibility** separate from the **logical** active section, and gate
  it per-ss, or the fade timer re-renders every section.
- Click = silent (no ring); cycle/add/drop/entry = pulse. Easy to conflate.
- Rebuild the timer cleanly (single hook, reset on nonce bump) — do not copy the
  prototype's brittle setTimeout/pulse logic.
- Mount the fade hook once (not per section).

## Verification checklist

- [ ] Click sets active silently; cycle/add/drop/entry pulse the ring.
- [ ] `useActiveSectionRing` flips visibility for ~2s and resets on re-trigger; only
  the active section re-renders.
- [ ] Collapsed section can't be active; default center on load.
- [ ] `just check` passes (e2e in Task 4.6).
