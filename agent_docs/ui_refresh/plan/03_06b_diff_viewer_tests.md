# Task 3.6b: test_diff_viewer.py — shared viewer (migrate diff/markdown)

## Goal

Build `test_diff_viewer.py`, exercising the shared embeddable `DiffViewer` once via
the 3.6a POMs + open-a-panel helper, migrating the proven diff/markdown assertions
**unchanged**. Delete this slice's migrated sources after it runs green.

## Stories addressed

FCC-02 (each panel renders its own viewer), FCC-06 (viewer always visible + empty
state), FCC-07 (config in the triple-dot menu).

## Background

**Project:** Sculptor integration tests; run via `/run-integration-test`. The viewer
behavior is **migrated, not rewritten** (`e2e_test_plan.md` §1): file/diff tabs,
split/unified + wrap + render toggles (now under the menu), find-in-file, line
numbers/expansion, moved-file (R) rendering, loading bar only when a file is open,
GFM + sanitization, open-from-chat. Use the 3.6a open-a-panel helper (clicks the add-panel dropdown) to open a panel and a
file, then assert via the `DiffViewer` POM.

Depends on **Task 3.6a** (POMs + open-a-panel helper). Not on 6.1.

## Migration sources (delete after green)

`test_diff_refresh_on_branch_change.py`, `test_diff_tab_close_others.py`,
`test_diff_loading_bar_no_file.py`, `test_markdown_render_toggle.py`,
`test_markdown_gfm.py`, `test_open_in_viewer.py`.

(The fullscreen half of `test_diff_scope_and_fullscreen.py` is **dropped** —
deprecated; `test_expand_escape.py` is DELETEd in Phase 7. Neither is migrated here.)

## Files to modify/create

- `sculptor/tests/integration/frontend/test_diff_viewer.py` — new (migrated content).
- Remove the migration sources listed above once their assertions land.

## Implementation details

1. Open a panel via the 3.6a helper (clicks the add-panel dropdown); open a file; drive
   the `DiffViewer` POM.
2. Move the assertions across **unchanged**; only re-anchor toggle selectors under
   `DIFF_FILE_HEADER_MENU_TRIGGER` (FCC-07) and drop expand/fullscreen assertions.
3. Skip purely-visual assertions (screenshot-verify per `.sculptor/testing.md`).

## Gotchas

- Don't rewrite content behavior — relocate selectors only.
- **Per-slice deletion:** remove **only** this slice's sources, and only after green —
  no orphan asserting a removed surface, and no source another slice still needs.

## Verification checklist

- [ ] `test_diff_viewer.py` passes via `/run-integration-test`.
- [ ] All listed sources removed; nothing else.
- [ ] FCC-02/06/07 covered; no expand/fullscreen; no layout-only visual assertions.
