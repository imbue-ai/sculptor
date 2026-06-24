# Task 4.5: Keyboard shortcuts + keybindings-settings integration

## Goal

Wire the workspace keyboard shortcuts for the new shell — section collapse/expand,
cycle sections (incl. split halves), cycle panels within a section, maximize/restore,
sidebar toggle, new agent (center), new workspace — and register all panel/section
shortcuts on the keybindings settings page.

## Stories addressed

SEC-05/06/07 (collapse/expand left/right/bottom via hotkey), SEC-08 (center can't
collapse), SEC-12 (cycle sections incl. split sub-sections), SEC-15 (maximize/restore
active section), SEC-20 (cycle panels within a section; wraps; no-op in empty/single),
SIDE-15 (toggle sidebar), PANEL-06 (new-agent binding Cmd+Shift+T creates the agent
in center), PANEL-13 (`[unit]` — panels expose their own shortcuts + a focus binding,
configured on the keybindings settings page), WSC-02 (Cmd/Meta+T opens the
new-workspace dialog — handler here; dialog in Task 5.1).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**Shortcuts + keybindings settings** (`goals.md` → "Sections"/"Panels"/"Adding a
panel"/"Active section"; `state_design.md` → "Panel registry"): the
collapse/expand/cycle/maximize/sidebar/new-agent/new-workspace bindings are
keyboard-driven. All panel shortcuts (panel-specific actions and focus bindings) are
configured on the **keybindings settings page** — **not** the deprecated Panels
settings page. The new-agent binding (Cmd+Shift+T) and Cmd+K-add-agent always create
the agent in **center** (PANEL-06).

**Reuse the existing keybindings infrastructure:** today's shell has
`src/layouts/hooks/usePageLayoutKeyboardShortcuts.ts` and a keybindings settings page
+ registry. Build a **new** shortcuts hook for the new shell that registers through
the **existing keybindings registry/settings** (grep for the keybindings registry,
the settings page, and how shortcuts are declared today) so the bindings show up and
are configurable. Do not extend the old `usePageLayoutKeyboardShortcuts` (it belongs
to the docking shell deleted in Phase 7).

**Empty first-run disables shortcuts** (FIRST-03): in the no-workspaces state, Cmd+K
and the global shortcuts are disabled (handled in Task 5.3; this hook must respect
that flag).

This task depends on the action atoms (Task 1.4: `toggleSectionAtom`,
`jumpToSectionAtom`, maximize via `maximizedSectionAtom`), the sidebar atoms (Task
1.3), the panel/agent/terminal creation flows (Task 3.5), and the dialog opener (Task
5.1, for Cmd/Meta+T).

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/hooks/useWorkspaceShortcuts.ts` — new: the
  new-shell shortcut handlers, registered via the existing keybindings registry.
- Keybindings settings registration: extend the existing registry/settings so the new
  bindings (section collapse/expand/cycle, panel cycle, maximize, sidebar toggle,
  new-agent focus, panel focus) appear and are configurable.
- `sculptor/sculptor/constants.py` — only if new testids are needed for the
  keybindings settings rows; `just generate-api`.

## Implementation details

1. Register handlers (default bindings) via the keybindings registry:
   - collapse/expand left/right/bottom (`toggleSectionAtom`); center is a no-op
     (SEC-08).
   - cycle sections incl. split sub-sections (`jumpToSectionAtom`, stepping through
     the `SubSectionId` sequence of expanded sections + their split halves) (SEC-12).
   - cycle panels within the active section (advance `activePanel` in the active
     sub-section; wrap at ends; no-op in empty/single) (SEC-20).
   - maximize/restore the active section (toggle `maximizedSectionAtom`) (SEC-15).
   - toggle sidebar (`sidebarCollapsedAtom`) (SIDE-15).
   - **new agent (Cmd+Shift+T)** → create an agent in **center** regardless of active
     section (PANEL-06); reuse the create-agent flow.
   - **new workspace (Cmd/Meta+T)** → open the new-workspace dialog (Task 5.1) (WSC-02).
2. Mount the hook in `WorkspaceLayoutShell`; respect the FIRST-03 disabled flag.
3. Panel focus bindings + panel-specific shortcuts (PANEL-13): expose per-panel
   shortcuts via the registry; a focus binding focuses a single-instance panel or the
   last-active multi-instance panel. Configure all on the keybindings settings page.
4. Default bindings should match `goals.md` where stated (Cmd+Shift+T new agent,
   Cmd/Meta+T new workspace); others reuse the prototype's bindings where reasonable
   (don't invent conflicting ones).

## Testing suggestions

- SEC-05..08/12/15/20, SIDE-15 e2e land in **Task 4.6**
  (`test_section_collapse_expand.py`, `test_section_active_and_maximize.py`,
  `test_sidebar_collapse_resize.py`); PANEL-06 (center-targeting) is asserted in
  `test_panel_add_dropdown.py` (**Task 3.7**). WSC-02 is in Task
  5.4. PANEL-13 is `[unit]` (test the binding registration + focus logic) plus a
  "binding visible" check in `test_keybindings.py` (Phase 8 UPDATE).
- The keybindings settings integration is testable by asserting the new bindings
  appear on the settings page (reuse existing keybindings test patterns).

## Gotchas

- New agent (Cmd+Shift+T) always targets **center** (PANEL-06), not the active
  section.
- Center can't collapse (SEC-08) — the collapse handler ignores it.
- Cycle steps through **split sub-sections** too (SEC-12), not just sections.
- Register on the **keybindings** settings page, not the deprecated Panels page.
- Respect the FIRST-03 disabled-shortcuts flag in the empty state.
- Build a new hook; don't extend the old docking-shell `usePageLayoutKeyboardShortcuts`
  (deleted in Phase 7).

## Verification checklist

- [ ] Collapse/expand, cycle sections (incl. splits), cycle panels, maximize, sidebar
  toggle, new-agent (center), new-workspace bindings all work.
- [ ] All bindings registered + configurable on the keybindings settings page.
- [ ] Shortcuts respect the empty-first-run disabled flag.
- [ ] `just check` passes (e2e in Task 4.6 / 5.4).
