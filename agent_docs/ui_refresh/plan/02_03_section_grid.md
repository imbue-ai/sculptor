# Task 2.3: SectionGrid + ResizeHandle (geometry, percent→pixel, clamps)

## Goal

Build `SectionGrid` — the four-section frame that owns the geometry — and the
`ResizeHandle`. It reads the global section sizes and the per-section expanded
flags, resolves percentages to pixels (protecting the center's larger minimum by
shrinking the sides first), renders only expanded sections, and short-circuits to a
single section when one is maximized.

## Stories addressed

SEC-17 (resize by the appropriate border, single-axis), SEC-22 (resize clamps:
sides have a minimum, center keeps a larger minimum, sides give way first), and the
frame for SEC-01..04 (the four-section layout). SEC-18 (sizes are global) is
satisfied by reading the global atom.

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**What to copy** (`design_extraction.md` → "Layout shell & workspace header
(scu-1474)" and "Sections… ResizeHandle"):
- `components/panels/CompactLayout.tsx` + `.module.scss` → rename to
  `components/sections/SectionGrid.tsx`. The four-section shell with the
  **percent→pixel resolver**: center min 400px / sides floor 150px.
- `components/panels/ResizeHandle.tsx` + `.module.scss` → `components/sections/
  ResizeHandle.tsx`: 1px divider, ±4px hit-area, hover `--gray-a7`, active
  `--accent-9`.

**Geometry rules** (`goals.md` → "Sections" + `state_design.md` → "Section sizes
(global)"): global sizes are the left/right widths and the bottom height as
**percentages** of the content area; the center fills the remainder. Resolve to
pixels with floors: center keeps a **larger** minimum width, the sides have a
floor, and the **sides give way before the center shrinks** (SEC-22). Each section
resizes on the appropriate border only and single-axis (left by its right border,
x-only; bottom by its top border, y-only; etc. — SEC-17).

**State:** read `sectionSizesAtom` (global) and `isSectionExpandedAtom(s)` (Task
1.3), and `maximizedSectionAtom` (Task 1.5). Resize writes the global section sizes
(via `globalLayoutAtom`/a `setSectionSizeAtom` helper) so a resize in one workspace
changes the size everywhere (SEC-18). Render **only expanded** sections.

**Memoization** (`component_hierarchy.md` memo table → `SectionGrid`): `SectionGrid`
re-renders on size or expand/collapse change; its children
(`SplittableSection`, Task 2.4) must be memoized with **primitive props** (section
id) so a per-pointer-move resize does not cascade into them.

This task depends on **Task 1.3** (size/expanded slices), **Task 1.5**
(`maximizedSectionAtom`), and **Task 2.1** (tokens). It renders
`SplittableSection` (Task 2.4) for each expanded section.

## Files to modify/create

- `sculptor/frontend/src/components/sections/SectionGrid.tsx` + `.module.scss` — new
  (from `CompactLayout`).
- `sculptor/frontend/src/components/sections/ResizeHandle.tsx` + `.module.scss` —
  new.
- `sculptor/sculptor/constants.py` — add section frame `ElementIDs` (then
  `just generate-api`).

## Implementation details

1. Copy the `CompactLayout` percent→pixel resolver into `SectionGrid`. Keep the
   floors (center min 400px, sides floor 150px) but expose them as named constants
   (don't inline magic numbers in JSX). Implement the SEC-22 rule: when the
   container shrinks, reduce the sides toward their floor before reducing the
   center below its larger minimum.
2. Render the frame: left, center (always present), right across the top row;
   bottom across the full width beneath. Render a section's box only when
   `isSectionExpandedAtom(s)` is true (center always true). Place `ResizeHandle`s on
   the inter-section borders (x-axis handle between left|center, center|right;
   y-axis handle above bottom).
3. Each `ResizeHandle` drags one border and writes the corresponding global size
   percentage (clamped). Apply `body.sculptor-resizing` during the drag (Task 2.1
   token) to suppress webview pointer events.
4. **Maximized short-circuit** (`component_hierarchy.md` → "The workspace layout
   shell"): when `maximizedSectionAtom` is set, render only that section filling the
   content area (the header-hide + OS padding is Task 4.3; here just render the
   single section full-bleed).
5. Render `<SplittableSection section={s} />` (Task 2.4) for each expanded section;
   `SplittableSection` is `memo`'d so resize churn stops at this boundary.
6. **ElementIDs** to add (`sections_panel_layout.md` §5): `SECTION_LEFT`,
   `SECTION_CENTER`, `SECTION_RIGHT`, `SECTION_BOTTOM`, `SECTION_RESIZE_HANDLE`. Set
   as `data-testid`s (handles can suffix the border they control). Run
   `just generate-api`.

## Testing suggestions

- SEC-17/SEC-22 e2e land in Task 4.6 (`test_section_resize.py`): drag a border →
  size changes and clamps; resize is pure-geometry (does not change the active panel
  or collapse state). The "size restored across workspaces" aspect of SEC-18 is e2e;
  the zero-reflow aspect is `[perf]` (Task 9.1).
- The percent→pixel resolver + SEC-22 clamp logic is a good unit-test target
  (extract it as a pure function and test with Vitest: shrinking the container
  pushes the sides to their floor before the center).

## Gotchas

- Sizes are **percentages** and **global** — write the global atom, not
  per-workspace state (SEC-18/PERSIST-02).
- Resize must be **single-axis** per border (SEC-17) and **pure geometry** — it must
  not touch active panel or expand/collapse state.
- Keep `SplittableSection` children `memo`'d with primitive props or resize will
  cascade re-renders (the SWITCH-05 boundary).
- Don't render collapsed sections at all (they show as the section toggle in the
  header, not an empty box).

## Verification checklist

- [ ] `SectionGrid` resolves percent→pixel with the documented floors and the
  SEC-22 "sides give way first" rule (unit-tested resolver).
- [ ] Renders only expanded sections; center always present; bottom spans full
  width.
- [ ] `ResizeHandle` drags one border, writes the global size, clamps, single-axis.
- [ ] Maximized short-circuit renders a single full-bleed section.
- [ ] Children memoized with primitive props.
- [ ] Section `ElementIDs` added + `just generate-api`; `just check` passes.
