# Task 1.1: Core layout types + sub-section keyspace helpers

## Goal

Create the foundational TypeScript types and pure helpers for the section/
sub-section keyspace and splits. Everything in the new workspace shell is keyed by
these types, so they land first as a small, fully unit-tested module.

## Stories addressed

Foundation for all `SEC-*` and `SPLIT-*` stories (no behavior on its own).

## Background

**Project:** Sculptor's frontend is TypeScript + React (Electron + Vite) under
`sculptor/frontend/src`. We are rewriting the workspace shell into the
section/panel model from `agent_docs/ui_refresh/goals.md`. State uses **Jotai**.

**The new layout model** (`agent_docs/ui_refresh/state_design.md` →
"Sections and sub-sections", and `supplemental/state_atoms.md` → "Core types"):
there are four **sections** — `left | center | right | bottom`. Each section may be
split into **exactly two sub-sections**. A panel always lives inside a
*sub-section*. Sub-sections use a **flat keyspace**: when a section is unsplit its
single sub-section id *is* the section id (the "primary"); when split it gains a
"secondary" sub-section identified by suffixing `:secondary` (e.g.
`left:secondary`). This flat keyspace is deliberate — the primary and secondary
halves run through identical machinery.

**Split geometry** (`goals.md` → "Split sections"): left/right sections split
top/bottom (a horizontal divider → stacked halves); the bottom section splits
left/right (a vertical divider → side-by-side halves); the center section supports
either direction. `supplemental/state_atoms.md` encodes this as
`SplitAxis = "horizontal" | "vertical"` where *horizontal divider → stacked* and
*vertical divider → side-by-side*. So left/right allow `horizontal`, bottom allows
`vertical`, center allows both.

**Naming:** use `goals.md` vocabulary only (`supplemental/naming_map.md`). The
prototype `bryden/scu-1474-compact-workspace-layout` calls these "zones"; do **not**
carry that name. There are no `bottom-left`/`bottom-right` zones in the rewrite —
only the four sections and a single optional split per section.

## Files to modify/create

- `sculptor/frontend/src/components/sections/sectionTypes.ts` — new. The core types
  and pure helpers.
- `sculptor/frontend/src/components/sections/sectionTypes.test.ts` — new. Vitest
  unit tests (frontend unit tests live next to source).

## Implementation details

1. Define the core types exactly as in `supplemental/state_atoms.md` → "Core
   types":
   - `SectionId = "left" | "center" | "right" | "bottom"`.
   - `SubSectionId = SectionId | \`${SectionId}:secondary\``.
   - `PanelId = string` (static id like `"files"`, or dynamic like
     `"agent:<taskId>"` / `"terminal:<wsId>:<n>"`).
   - `SplitAxis = "horizontal" | "vertical"` with a comment documenting *horizontal
     divider → stacked top/bottom; vertical divider → side-by-side left/right*.
   - `SectionSplit = { axis: SplitAxis; ratio: number }` where `ratio` is the
     primary half's fraction (0..1).
2. Export an ordered constant `SECTION_IDS: readonly SectionId[] =
   ["left", "center", "right", "bottom"]` for iteration and a `isSectionId(x):
   x is SectionId` guard.
3. Implement the keyspace helpers named in `supplemental/state_atoms.md`:
   - `toSecondary(s: SectionId): SubSectionId` → `\`${s}:secondary\``.
   - `toSection(ss: SubSectionId): SectionId` → strip the `:secondary` suffix.
   - `isSecondary(ss: SubSectionId): boolean`.
   - `primaryOf(s: SectionId): SubSectionId` → returns `s` (the primary
     sub-section id is the section id) — add this for symmetry/readability.
4. Implement the split-direction rule as a pure helper:
   - `allowedSplitAxesForSection(s: SectionId): readonly SplitAxis[]` →
     `left`/`right` → `["horizontal"]`; `bottom` → `["vertical"]`; `center` →
     `["horizontal", "vertical"]`.
   - `canSplitAxis(s: SectionId, axis: SplitAxis): boolean`.
5. Keep this module **pure** (no React, no Jotai, no DOM). It is imported by the
   atoms (Task 1.3/1.4), the components (Phase 2), and the registry (Task 1.6).

## Testing suggestions

- Vitest in `sectionTypes.test.ts`:
  - `toSection(toSecondary(s)) === s` for every section; `isSecondary` true only
    for `:secondary` ids; `primaryOf(s) === s`.
  - `allowedSplitAxesForSection` returns the documented axes per section;
    `canSplitAxis("left", "vertical") === false`, `canSplitAxis("center", *) ===
    true`, etc.
- Run frontend unit tests with `just test-unit-frontend`.

## Gotchas

- The primary sub-section id **is** the section id — do not invent a `:primary`
  suffix.
- Do not add `bottom-left`/`bottom-right` or any third section id; the rewrite has
  exactly four sections, each with at most one split (`naming_map.md` → "Deleted").
- Axis semantics are easy to invert: *horizontal* means a horizontal divider
  (stacked), used by left/right (top/bottom halves). Keep the comment.

## Verification checklist

- [ ] `sectionTypes.ts` exports `SectionId`, `SubSectionId`, `PanelId`,
  `SplitAxis`, `SectionSplit`, `SECTION_IDS`, and all helpers above.
- [ ] No import of React/Jotai/DOM in this file.
- [ ] Vitest covers the keyspace round-trips and the split-axis rules.
- [ ] Unit tests: `sectionTypes.test.ts` passes via `just test-unit-frontend`.
