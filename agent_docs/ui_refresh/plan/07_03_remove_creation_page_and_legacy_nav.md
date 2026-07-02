# Task 7.3: Remove the /ws/new page, closed-workspaces, and Component Gallery

## Goal

Delete the legacy creation page and navigation surfaces the redesign replaced or
dropped: the `/ws/new` page + its POM, the closed-workspaces pill/dropdown, and the
Component Gallery. **Keep the TanStack devtools panel.** Remove the file-browser-tab
and zone-icon ElementIDs that the new panels replaced.

## Stories addressed

Removal only (`goals.md` → "New workspace dialog" / "Features to deprecate";
`user_stories.md` → "Removed behaviors": the open/closed-workspace distinction).

## Background

**Project:** Sculptor frontend (TS + React) + integration harness. We rewrote the
workspace shell from `agent_docs/ui_refresh/goals.md`. The new-workspace **dialog**
(Phase 5) replaces the `/ws/new` page; the sidebar (Phase 2) shows all workspaces, so
the open/closed distinction is gone; Files/Changes/Commits are separate panels (Phase
3), so the file-browser tabs are gone.

**What is removed:**
- **The `/ws/new` page** (`src/pages/add-workspace/`) + its POM
  `pages/add_workspace_page.py` (the form getters moved into
  `elements/new_workspace_dialog.py` in Task 5.4). ElementIDs: `ADD_WORKSPACE_TAB`,
  `ADD_WORKSPACE_BUTTON`, `ADD_WORKSPACE_EMPTY_STATE`.
- **The closed-workspaces pill + dropdown** (Decision B4: the open/closed distinction
  is removed; all workspaces appear in the sidebar). POM
  `elements/closed_workspaces_dropdown.py` + `test_closed_workspaces_dropdown.py`
  deleted; the reopen paths in `test_workspace_close_vs_delete.py` dropped (the rest of
  that file is REWRITE in Task 8.1). `goals.md` already records this removal under
  "Features to deprecate" — no `goals.md` edit needed.
- **The Component Gallery** (Decision B5: dev-only, no longer used):
  `test_component_gallery_tab.py`, the gallery assertion in `test_theme_builder.py`,
  and `COMPONENT_GALLERY_TAB`.
- **File-browser tab + zone-icon ElementIDs** now replaced by panels:
  `FILE_BROWSER_TAB_ALL`/`_CHANGES`/`_HISTORY`, and any remaining `PANEL_ICON_*` not
  already removed in Task 7.1.

**What is KEPT (Decision B5):** the **TanStack devtools panel** and its
`test_tanstack_devtools_panel.py` stay — no one relies on the Component Gallery, but
the devtools panel is still wanted. Do **not** delete the devtools panel, its
ElementIDs, or its test (UPDATE it only if its navigation reach changed in the new
shell).

This task depends on **Phase 5** (the dialog/first-run replaced `/ws/new`) and the
panels (Phase 3).

## Files to modify/create

- Delete `src/pages/add-workspace/` (the `/ws/new` route + page) and remove its route
  registration in `Router.tsx`/`App.tsx`.
- Delete `sculptor/sculptor/testing/pages/add_workspace_page.py`.
- Delete the closed-workspaces pill/dropdown component + `elements/closed_workspaces_dropdown.py`
  + `test_closed_workspaces_dropdown.py`; drop the reopen paths in
  `test_workspace_close_vs_delete.py`.
- Delete the Component Gallery surface + `test_component_gallery_tab.py`; drop the
  gallery assertion in `test_theme_builder.py`. **Do not** touch the TanStack devtools
  panel or `test_tanstack_devtools_panel.py`.
- `sculptor/sculptor/constants.py` — remove `ADD_WORKSPACE_TAB`/`ADD_WORKSPACE_BUTTON`/
  `ADD_WORKSPACE_EMPTY_STATE`, `COMPONENT_GALLERY_TAB`, `FILE_BROWSER_TAB_*`, residual
  `PANEL_ICON_*`; `just generate-api`. (Leave any TanStack-devtools ids intact.)

## Implementation details

1. Remove the `/ws/new` route + page; confirm all creation now flows through the dialog
   (Phase 5). Delete `add_workspace_page.py` (its getters live in the dialog POM).
2. Remove the closed-workspaces pill/dropdown + reopen paths; ensure all workspaces
   render in the sidebar. (`goals.md` already records the removal — no edit needed.)
3. Remove the Component Gallery surface + test + the theme-builder gallery assertion
   (keep the rest of theme-builder). **Leave the TanStack devtools panel in place.**
4. Remove the file-browser-tab + residual zone-icon ElementIDs; `just generate-api`;
   fix TS fallout.
5. Confirm no importer of any deleted module remains.

## Testing suggestions

- `just check` + `just ratchets`; run the suite via `/run-integration-test`. The
  sidebar/creation migrations in Phase 8 cover the survivors; the deleted tests are for
  removed surfaces. Confirm `test_tanstack_devtools_panel.py` still passes (kept).

## Gotchas

- **Keep the TanStack devtools panel** (Decision B5) — only the Component Gallery is
  removed. Don't delete the devtools panel, its ids, or its test.
- `add_workspace_page.py`'s getters must already live in `new_workspace_dialog.py`
  (Task 5.4) before deleting it.
- `test_workspace_close_vs_delete.py` is only **partially** affected here (reopen paths
  dropped); the rest is Task 8.1.
- `goals.md` already records the closed-workspace removal — don't re-edit it.
- `just generate-api` after `constants.py`.

## Verification checklist

- [ ] `/ws/new` route + page + `add_workspace_page.py` deleted; all creation via the
  dialog.
- [ ] Closed-workspaces pill/dropdown + POM + test deleted; reopen paths dropped.
- [ ] Component Gallery surface + `test_component_gallery_tab.py` deleted; theme-builder
  gallery assertion dropped; **TanStack devtools panel + test kept**.
- [ ] `ADD_WORKSPACE_*`/`COMPONENT_GALLERY_TAB`/`FILE_BROWSER_TAB_*`/residual
  `PANEL_ICON_*` removed (devtools ids intact) + `just generate-api`.
- [ ] `just check` + `just ratchets` pass; suite green via `/run-integration-test`.
