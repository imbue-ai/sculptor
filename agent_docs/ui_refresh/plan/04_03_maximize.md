# Task 4.3: Maximize / restore + maximized presentation

## Goal

Finish the maximize feature: maximizing the active section makes it cover the whole
workspace content, hides the workspace header, keeps the section header, applies OS
window-control padding + a show-sidebar icon when the sidebar is collapsed, and (for
a split section) shows only one sub-section.

## Stories addressed

SEC-13 (maximize the active section to cover the content; one at a time), SEC-14
(maximized section keeps its header but hides the workspace header; expanded sidebar
stays visible), SEC-15 (hotkey maximize/restore — the binding is wired in Task 4.5;
the action lives here), SEC-16 (sidebar collapsed → show-sidebar icon at the left of
the section header with OS-control padding), SEC-21 (maximize is transient; reload
clears it), SPLIT-06 (maximized split shows one sub-section).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**Maximize behavior** (`goals.md` → "Maximized section"; `state_design.md` →
"Maximized section (transient)"; `component_hierarchy.md`): a maximized section
covers the entire workspace page content (the `SectionGrid` short-circuit from Task
2.3); only one at a time; the workspace header is hidden (gated in Task 2.6's
`WorkspaceLayoutShell`); the section still shows its own header; the expanded sidebar
stays visible; when the sidebar is **collapsed**, the show-sidebar icon appears at
the **left of the section header** with the OS window-control padding (close/
minimize/zoom). A split maximized section shows only **one** sub-section. Maximize is
**transient** — `maximizedSectionAtom` is a non-persisted atom (Task 1.5), so reload
returns to the normal layout.

**What to copy** (`design_extraction.md` → "Maximized presentation"): `.maximized` in
`PanelSection.module.scss` (absolute inset:0, `--z-sticky`) + the
`getTitleBarLeftPadding()` helper for OS controls.

This task depends on **Task 1.5** (`maximizedSectionAtom`), **Task 2.3**
(`SectionGrid` maximized short-circuit), **Task 2.4** (`PanelSection`/`SectionHeader`),
**Task 2.6** (header-hide gate), and the sidebar collapsed state (Task 2.2).

## Files to modify/create

- `sculptor/frontend/src/components/sections/PanelSection.tsx` + `.module.scss` —
  modify: maximized styling (`.maximized` absolute inset:0, `--z-sticky`); when
  maximized + sidebar collapsed, render the show-sidebar icon at the left of the
  section header with `getTitleBarLeftPadding()`.
- `sculptor/frontend/src/components/sections/SectionGrid.tsx` — confirm the maximized
  short-circuit renders only the maximized section (from Task 2.3) and, for a split,
  only one sub-section (SPLIT-06).
- `sculptor/frontend/src/components/sections/SectionHeader.tsx` — modify: the
  maximize toggle reflects/sets `maximizedSectionAtom`; show the show-sidebar icon
  slot.
- `sculptor/sculptor/constants.py` — a show-sidebar-in-maximized-header id if not
  reusing `SIDEBAR_EXPAND_ICON`; `just generate-api`.

## Implementation details

1. The maximize toggle in `SectionHeader` sets `maximizedSectionAtom` to this section
   (or clears it to restore). Only the active section can be maximized via hotkey
   (SEC-15, Task 4.5); the toggle works on its own section.
2. `SectionGrid` renders only the maximized section full-bleed (Task 2.3). For a
   **split** maximized section, render only **one** sub-section (SPLIT-06) — the
   primary by default.
3. `WorkspaceLayoutShell` hides `WorkspaceHeader` while maximized (Task 2.6 gate).
   The section keeps its own header (SEC-14).
4. When maximized **and** the sidebar is collapsed (SEC-16): render the show-sidebar
   icon at the left of the section header and apply `getTitleBarLeftPadding()` so it
   clears the OS window controls. When the sidebar is expanded, it stays visible and
   no extra padding is needed.
5. Maximize is transient (SEC-21) — `maximizedSectionAtom` is non-persisted (Task
   1.5); confirm reload clears it. Do not persist it.

## Testing suggestions

- SEC-13..16/21 + SPLIT-06 e2e land in **Task 4.6**
  (`test_section_active_and_maximize.py`): maximize covers content; only one at a
  time; section header shown / workspace header hidden; sidebar-collapsed → padded
  show-sidebar icon; split shows one sub-section; reload restores normal layout
  (SEC-21).
- The OS-padding visual is screenshot-verified; the presence of the show-sidebar icon
  is behavioral.

## Gotchas

- Maximize is **transient** — never route it through the persistence adapter (a stale
  persisted flag could strand the app maximized).
- Keep the **section** header but hide the **workspace** header (SEC-14) — don't
  confuse the two.
- Use `getTitleBarLeftPadding()` (helper, not inlined numbers) for OS-control padding.
- A maximized split shows **one** sub-section (SPLIT-06), not both.

## Verification checklist

- [ ] Maximize covers the content area; one section at a time; restore works.
- [ ] Workspace header hidden while maximized; section header retained.
- [ ] Sidebar-collapsed → show-sidebar icon + OS-control padding in the section
  header; expanded sidebar stays visible.
- [ ] Maximized split shows one sub-section; reload clears maximize (transient).
- [ ] `just check` passes.
