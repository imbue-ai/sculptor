# Task 7.2: Remove Zen/Focus, /btw, Panels settings, share-sizes, tab-strip-position, expand toggle

## Goal

Delete the remaining deprecated features and their state: Zen mode, Focus mode, the
`/btw` popup, the Panels settings page + the panel enable/disable machinery, the
experimental "share panel sizes" setting, the tab-strip-position setting, and the
per-diff expand/fullscreen toggle.

## Stories addressed

Removal only (`goals.md` → "Features to deprecate"; `user_stories.md` → "Removed
behaviors"; `state_design.md` → "Removed state"; `naming_map.md` → "Deleted").

## Background

**Project:** Sculptor frontend (TS + React + Jotai) + integration harness. We rewrote
the workspace shell into the section/panel model from `agent_docs/ui_refresh/goals.md`.
These features have no place in the new model and are deleted with no dead code.

**What is removed:**
- **Zen mode + Focus mode** (`goals.md` → "Features to deprecate"): chrome + state +
  POM. The active section + maximize replace any "focus" need.
- **The `/btw` popup**.
- **The Panels settings page** + the **panel enable/disable machinery** (the
  `panelEnabledAtom`/`defaultEnabled`/`isBuiltin` flags) — panels are registered
  statically with no user enable/disable (`panel_registry.md`).
- **The "share panel sizes between workspaces" experimental setting**
  (`sectionSizesSharedAtom`) — sizes are always global now (SEC-18).
- **The tab-strip-position setting** (`tabStripPositionAtom`).
- **The per-diff expand/fullscreen toggle** (`DIFF_EXPAND_TOGGLE` + `expandedPanelIdAtom`)
  — there is no diff-specific fullscreen; users maximize the section (SEC-13/15). Do
  **not** add an `expand → maximize` alias.

**Atoms to delete** (`naming_map.md` → "Deleted"): `expandedPanelIdAtom`,
`sectionSizesSharedAtom`, `tabStripPositionAtom`, `panelEnabledAtom`/`defaultEnabled`/
`isBuiltin`, plus the Zen/Focus/`/btw` atoms. (The rewrite never created these; this
task removes the **old** ones still on `main`.)

**ElementIDs to remove** (`harness_migration.md` §2): `EXIT_ZEN_MODE_BUTTON`,
`FOCUS_MODE_BUTTON`, `BTW_POPUP*` (all 6), `SETTINGS_PANELS_*` + `SETTINGS_NAV_PANELS`,
`DIFF_EXPAND_TOGGLE`. Run `just generate-api`.

**POMs to delete:** `elements/zen_mode.py`, `elements/btw_popup.py`,
`elements/settings_panels.py`. **Tests to delete** (`e2e_test_plan.md` §2):
`test_zen_mode.py`, `test_btw.py`, `test_panels_settings.py`, `test_expand_escape.py`,
and the fullscreen half of `test_diff_scope_and_fullscreen.py`. **Note:**
`test_alpha_chat_tool_density.py` imports the `zen_mode` POM only incidentally — it is
**UPDATE** (swap to a section-collapse helper), not delete.

This task depends on **Phases 2–6** (the replacements — maximize, sections, static
registry — must exist).

## Files to modify/create

- Delete the Zen/Focus chrome + state, the `/btw` popup, the Panels settings page +
  enable/disable machinery, the share-sizes + tab-strip-position settings, and the
  diff expand toggle (grep each by name).
- Delete `elements/zen_mode.py`, `elements/btw_popup.py`, `elements/settings_panels.py`.
- Delete `test_zen_mode.py`, `test_btw.py`, `test_panels_settings.py`,
  `test_expand_escape.py`; drop the fullscreen half of `test_diff_scope_and_fullscreen.py`
  (rename the file to drop "fullscreen"; keep the scope-picker-defaults-to-All half as
  an UPDATE).
- Update `test_alpha_chat_tool_density.py` to use a section-collapse helper instead of
  the `zen_mode` POM.
- `sculptor/sculptor/constants.py` — remove the ElementIDs above; `just generate-api`.

## Implementation details

1. Grep for and delete each feature's components, state atoms, settings entries, and
   keybindings. Confirm no remaining importers (the new shell doesn't use them).
2. Remove the panel enable/disable machinery end-to-end: the Panels settings page +
   nav entry, the `panelEnabled`/`defaultEnabled`/`isBuiltin` flags, and any code that
   read them (the registry is static now — Task 1.6).
3. Delete the share-sizes + tab-strip-position settings + their atoms/UI.
4. Delete the diff expand/fullscreen toggle + `expandedPanelIdAtom` + `DIFF_EXPAND_TOGGLE`;
   do not add a maximize alias.
5. Delete the POMs + tests above; UPDATE `test_alpha_chat_tool_density.py`.
6. `just generate-api`; fix TS fallout.

## Testing suggestions

- `just check` (broken imports) + `just ratchets`. Run the suite via
  `/run-integration-test` to confirm the UPDATE (`test_alpha_chat_tool_density.py`)
  passes and nothing else regressed.

## Gotchas

- `test_alpha_chat_tool_density.py` is **UPDATE, not delete** (incidental zen POM use).
- Remove the panel enable/disable machinery **completely** — the registry assumes no
  `enabled` flag (Task 1.6).
- No `expand → maximize` alias; the expand toggle is gone, not renamed.
- Don't remove the scope-picker-defaults-to-All assertion (that half of
  `test_diff_scope_and_fullscreen.py` is a surviving UPDATE).
- `just generate-api` after `constants.py`.

## Verification checklist

- [ ] Zen/Focus, `/btw`, Panels settings + enable/disable machinery, share-sizes,
  tab-strip-position, and the diff expand toggle all deleted (code + state + ids).
- [ ] `zen_mode.py`/`btw_popup.py`/`settings_panels.py` + the four test files deleted;
  the fullscreen half of `test_diff_scope_and_fullscreen` dropped.
- [ ] `test_alpha_chat_tool_density.py` UPDATEd to a section-collapse helper.
- [ ] ElementIDs removed + `just generate-api`; `just check` + `just ratchets` pass.
