# Task 7.1: Remove the docking shell — layout, top bar, tabs, zones, side-toggle

## Goal

Delete the old docking layout and its chrome — the page shell/top bar, the workspace/
home/settings tab strip, the panel-zone/docking model, and the side-toggle bar — now
that the new shell owns the workspace route. No dead code, no stale files.

## Stories addressed

Removal only (`user_stories.md` → "Removed behaviors"; `goals.md` → "Features to
deprecate"). Clears the path for SEC/PANEL/SIDE to be the only layout model.

## Background

**Project:** Sculptor frontend (TS + React) + integration harness. We rewrote the
workspace shell into the section/panel model from `agent_docs/ui_refresh/goals.md`
using the strangler strategy: the new shell is the live route (Phase 2 cutover), so
the old docking shell is now unreferenced and is deleted here.

**What is removed** (`user_stories.md` → "Removed behaviors"; `naming_map.md`;
`e2e_test_plan.md` §2; the audits' §5 "Remove" lists):
- The **old page shell / top bar / bottom bar** and the **tab strip** (home/settings/
  workspace/add-workspace tabs) — replaced by the sidebar + workspace header.
- The **docking / panel-zone** model (top-right / bottom-right zones, "Move to zone",
  zone persistence) — replaced by sections.
- The **side-toggle bar** — replaced by section collapse/expand.

**Confirm nothing references them first.** The new shell (Phases 2–6) should already
be the only workspace route. Grep for imports of the old `layouts/PageLayout`, the
top-bar/tab components, the zone components, and the side-toggle before deleting.

**ElementIDs to remove** (`harness_migration.md` §2; `sidebar_nav.md` §5;
`sections_panel_layout.md` §4): `TOP_BAR`, `BOTTOM_BAR`, `HOME_TAB`, `SETTINGS_TAB`,
`WORKSPACE_TAB`, `ADD_WORKSPACE_TAB`, `TAB_CLOSE_BUTTON` (if no longer used),
`PANEL_TOP_RIGHT`, `PANEL_BOTTOM_RIGHT`, `PANEL_RIGHT_AREA`, `PANEL_RIGHT_RESIZE_HANDLE`,
`SIDE_TOGGLE_LEFT`/`SIDE_TOGGLE_RIGHT`/`SIDE_TOGGLE_BOTTOM`, `PANEL_ICON_*` (the zone
sidebar-icon set), `PANEL_CONTEXT_MENU_MOVE_TO`, `PANEL_CONTEXT_MENU_ZONE_OPTION`, and
the old agent/terminal tab-bar ids superseded by `PANEL_TAB`/`ADD_PANEL_*` — `AGENT_TAB`,
`TERMINAL_TAB`, `ADD_AGENT_BUTTON`, `ADD_AGENT_CHEVRON_BUTTON`, `AGENT_TYPE_MENU*` (Task
3.7 re-keyed the POMs but left these rendering on the not-yet-removed shell). Run
`just generate-api` after.

**Tests to delete** (`e2e_test_plan.md` §2): `test_panel_zones.py`,
`test_side_toggle.py`. **POM to delete:** `elements/panel_zones.py`. (The
`test_zen_mode.py` `get_bottom_bar`/`get_top_bar_locator` usage is handled with the
Zen removal in Task 7.2.)

This task depends on **all of Phases 2–6** (the new shell must fully own the route).

## Files to modify/create

- Delete the old `src/layouts/PageLayout.tsx` (+ scss + `hooks/usePageLayoutKeyboardShortcuts.ts`)
  **iff** unreferenced (the new shell replaced it; the new shortcuts hook is Task 4.5).
- Delete the top-bar/bottom-bar/tab-strip components, the panel-zone/docking
  components, the side-toggle bar, and the old agent/terminal **tab-bar** components
  (the agent tab strip + add-agent button — superseded by panel tabs) (grep to find
  them under `src/components` / `src/pages/workspace`).
- Delete `sculptor/sculptor/testing/elements/panel_zones.py`.
- Delete `sculptor/tests/integration/frontend/test_panel_zones.py`,
  `test_side_toggle.py`.
- `sculptor/sculptor/constants.py` — remove the ElementIDs above; `just generate-api`.

## Implementation details

1. Grep for every importer of the old shell/top-bar/tab/zone/side-toggle modules.
   Confirm there are none (the new shell replaced them). If something still imports
   them, it was missed in Phases 2–6 — fix the reference, don't keep the dead module.
2. Delete the modules, their `.module.scss`, and their stories if any.
3. Delete the now-dead ElementIDs and run `just generate-api`. Fix any remaining TS
   references the generated types surface.
4. Delete `panel_zones.py` and the two test files.
5. Remove any localStorage reads of the old zone keys (the new adapter ignores them;
   ensure no stray reader remains).

## Testing suggestions

- After deletion, run `just check` (lint/types/ratchets) — broken imports surface
  here. Run the integration suite via `/run-integration-test` to confirm nothing
  regressed (the migrations in Phase 8 handle the legacy suite; the deleted tests are
  for removed features).
- `just ratchets-broken` to confirm no ratchet regressions from the deletions.

## Gotchas

- Delete **only after** confirming zero references — a missed importer means a Phase
  2–6 task left a seam.
- Don't remove ElementIDs that the **new** shell reused (e.g. `INLINE_RENAME_INPUT`,
  `DELETE_CONFIRMATION_*`, `WORKSPACE_ROW*`) — only the zone/tab/top-bar set.
- `just generate-api` after `constants.py` edits, then fix TS fallout.
- `TAB_CLOSE_BUTTON` may still be used by the panel-tab POM (Task 3.7 kept it) — check
  before removing.

## Verification checklist

- [ ] Old page shell / top bar / bottom bar / tab strip / panel zones / side-toggle
  deleted; no importers remain.
- [ ] `panel_zones.py`, `test_panel_zones.py`, `test_side_toggle.py` deleted.
- [ ] Zone/tab/top-bar + agent/terminal tab-bar (`AGENT_TAB`/`ADD_AGENT_*`/…)
  ElementIDs removed + `just generate-api`; TS fallout fixed.
- [ ] `just check` + `just ratchets` pass; integration suite green via
  `/run-integration-test`.
