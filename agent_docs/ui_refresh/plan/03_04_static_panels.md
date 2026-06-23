# Task 3.4: Review-all / Actions / Skills / Browser / Notes panels

## Goal

Build the remaining static single-instance panels as registered panels with **no
enable/disable machinery**. Each wraps its existing content surface.

## Stories addressed

REVIEW-01 (Review-all is its own single-instance panel with no default section, not
opened by default), REVIEW-02 (all review-all functionality preserved), PANEL-05
(the single-instance panel set), PANEL-15 (single-instance by default).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.

**The static panel set** (`supplemental/panel_registry.md` → "Static panels"):
- `review-all` — combined multi-file diff; **no default section** (not open by
  default, like Browser). Preserve all existing review-all functionality.
- `actions` — default `right`. **Slated for deprecation** (superseded by plugins) —
  minimal handling: just appear as a registered panel.
- `skills` — default `right`. Keep existing content.
- `browser` — **no default section**; webview panel; in-page state persists. The old
  opt-in/opt-out *enable* model is **removed** — it is just a registered panel.
- `notes` — default `right`. **Slated for deprecation** — minimal handling.

**No enable/disable** (`panel_registry.md`; `naming_map.md` → "Deleted"): there is
no `enabled`/`defaultEnabled`/`isBuiltin` flag and no Panels settings page. These
panels are registered statically. (The Panels settings page + machinery are deleted
in Phase 7.)

**Reuse existing content:** grep `main` for the current review-all combined-diff,
skills, browser/webview, notes, and actions surfaces and wrap them. Do not rewrite
their internals (`e2e_test_plan.md`: review-all functionality preserved; skills is
UPDATE/KEEP content; browser in-page-state-persistence survives).

This task depends on **Task 1.6** (`registerPanelComponent`; static metadata already
lists these). Browser/Notes/Actions test handling is in Phase 8 (mostly UPDATE/
minimal/REWRITE-for-removed-enable).

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/panels/ReviewAllPanel.tsx` — new wrapper.
- `sculptor/frontend/src/pages/workspace/panels/ActionsPanel.tsx` — new (minimal).
- `sculptor/frontend/src/pages/workspace/panels/SkillsPanel.tsx` — new wrapper.
- `sculptor/frontend/src/pages/workspace/panels/BrowserPanel.tsx` — new wrapper (no
  enable model).
- `sculptor/frontend/src/pages/workspace/panels/NotesPanel.tsx` — new (minimal).
- Register all five via `registerPanelComponent`.

## Implementation details

1. Each panel is a thin, shell-agnostic wrapper around the existing content surface,
   reading from existing data atoms. No layout reads.
2. **ReviewAllPanel:** wrap the existing review-all combined-diff (preserve
   auto-collapse, workspace-scoped changes — REVIEW-02). `defaultSection` undefined
   (not open by default).
3. **BrowserPanel:** wrap the existing webview; preserve isolation + in-page-state
   persistence. **Remove** the opt-in/enable concept — it's just a registered panel
   with no default section.
4. **SkillsPanel:** wrap existing skills content (`defaultSection: "right"`).
5. **ActionsPanel / NotesPanel:** minimal — register and render existing content with
   `defaultSection: "right"`. No special work (they're slated for deprecation).
6. Confirm none of these reference an enabled/built-in flag.

## Testing suggestions

- REVIEW-01/02 e2e: `test_review_all_panel.py` (Phase 8 / can be CREATEd here)
  absorbs `test_review_all_visibility`/`test_workspace_scoped_changes`/
  `test_auto_collapse_combined_diff`. Browser/Skills/Actions/Notes tests are handled
  in Phase 8 (REWRITE-for-removed-enable / UPDATE / minimal).

## Gotchas

- **No enable/disable** anywhere — the old `PANEL_ICON_*` host ids and `panelEnabled`
  machinery are gone (Phase 7 removes the remnants).
- Review-all and Browser have **no default section** (not open by default).
- Reuse existing content; don't rewrite (esp. review-all and browser in-page state).
- Actions/Notes are minimal — don't over-invest (deprecation pending).

## Verification checklist

- [ ] All five panels registered as single-instance; review-all + browser have no
  default section; actions/skills/notes default to `right`.
- [ ] Each wraps existing content with no layout reads and no enable flag.
- [ ] Review-all functionality preserved.
- [ ] `just check` passes.
