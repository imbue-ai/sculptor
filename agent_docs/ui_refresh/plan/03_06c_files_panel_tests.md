# Task 3.6c: test_files_panel.py — Files panel (migrate file-browser)

## Goal

Build `test_files_panel.py` — the Files panel's file tree + its own embedded viewer,
shared-width sidebar resize/toggle, always-visible viewer + empty state — migrating
the proven file-browser assertions **unchanged** via the 3.6a POMs + open-a-panel helper.
Delete this slice's migrated sources after it runs green.

## Stories addressed

FCC-01 (Files is a separate panel), FCC-03 (its sidebar is the file browser), FCC-04
(shared-width sidebar resize + min size), FCC-05 (toggle sidebar from the viewer
header).

## Background

**Project:** Sculptor integration tests; run via `/run-integration-test`. Content is
**migrated, not rewritten** (`e2e_test_plan.md` §1/§4e). Open the Files panel via the
3.6a open-a-panel helper (clicks the add-panel dropdown); drive the `ExplorerLayout` +
`DiffViewer` POMs.

Depends on **Task 3.6a** (POMs + open-a-panel helper). Not on 6.1.

## Migration sources (delete after green)

`test_file_browser.py`, `test_file_browser_tabs.py`,
`test_file_browser_symlink_replaces_directory.py`, `test_file_open_diff_modes.py`,
`test_path_tilde_display.py`.

> Note: `test_file_browser_tabs.py` tested the old All/Changes/History **tab**
> switching, which is gone (three separate panels; `FILE_BROWSER_TAB_*` deleted).
> Migrate only its residual file-tree content; drop the tab-switching assertions.

## Files to modify/create

- `sculptor/tests/integration/frontend/test_files_panel.py` — new (migrated content).
- Remove the migration sources listed above once their assertions land.

## Implementation details

1. Open Files via the 3.6a helper (add-panel dropdown); assert the tree (flat + tree variants),
   path/tilde display, symlink handling, open-from-chat, and open-diff-mode behavior.
2. Shared-width sidebar: resize + min size (FCC-04), toggle from the viewer header
   (FCC-05), always-visible viewer + empty state (FCC-06).
3. Move assertions across **unchanged**; skip purely-visual assertions.

## Gotchas

- Three **separate** panels — no `FILE_BROWSER_TAB_*` and no single-panel tab model.
- **Per-slice deletion:** remove **only** this slice's sources, after green.
- The shared list width is global (FCC-04) — assert via the `ExplorerLayout` POM, not
  a Files-local width.

## Verification checklist

- [ ] `test_files_panel.py` passes via `/run-integration-test`.
- [ ] All listed sources removed; nothing else; smoke check from 3.6a folded in or
  removed.
- [ ] FCC-01/03/04/05 covered; no layout-only visual assertions.
