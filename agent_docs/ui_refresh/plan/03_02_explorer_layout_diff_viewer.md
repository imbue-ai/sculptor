# Task 3.2: Shared ExplorerLayout + embeddable DiffViewer (triple-dot menu)

## Goal

Build the two shared building blocks the Files/Changes/Commits panels embed: a
resizable `ExplorerLayout` (list sidebar + viewer + empty state, with a
globally-shared list width) and an embeddable `DiffViewer` whose configuration
options now live under a triple-dot menu. Building these once avoids triplicating
the explorer shape across three panels.

## Stories addressed

FCC-02 (each panel renders its own diff/file viewer), FCC-04 (resizable list
sidebar, min size, **shared global width**), FCC-05 (toggle sidebar visibility from
the viewer header), FCC-06 (viewer always visible, empty state when no file),
FCC-07 (all previous config icons/options moved into the triple-dot menu in the
viewer header).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`. Per
`goals.md` → "Files, Changes and Commits", the old single file-browser panel + diff
pseudo-panel becomes three panels, each with its **own** embedded viewer and its own
sidebar (file tree / changes browser / commit history). The list-sidebar width is
**shared** across the three and **global** across workspaces.

**What to copy** (`design_extraction.md` → "Files / Changes / Commits & diff
viewer"):
- `pages/workspace/panels/MasterDetailPanel.(tsx|module.scss)` (→ `ExplorerLayout`) — resizable
  explorer (200px min list, 280px min detail) + the empty `EmptyDetail`.
- `pages/workspace/panels/MasterDetailTreeHeader.(tsx|module.scss)` (→ `ExplorerTreeHeader`) — 41px header
  with search box + tree-options menu.
- `pages/workspace/components/diffPanel/` set: `DiffPanel.(tsx|module.scss)`,
  `DiffFileHeader.(tsx|module.scss)`, `DiffSkeleton.(tsx|module.scss)` (static, no
  shimmer), `InFileSearchBar.(tsx|module.scss)`, `DiffScopePicker.(tsx|module.scss)`.
  The **three-dot menu** is assembled from `DiffViewMenuItems` (split/unified, wrap,
  find, markdown) + the tree options (flat/tree, collapse) — this is where the
  relocated icons live (FCC-07).

**State:** the shared list width is `explorerListWidthAtom`
(`supplemental/state_atoms.md` / `persistence_interface.md` →
`GlobalLayoutState.explorerListWidthPx`) — a writable **global** slice (Task
1.3). Sidebar-visibility toggle can be a per-panel UI atom or global pref
(`design_extraction.md` lists diff view-mode/tree-flat as candidate global prefs).

**Preserve today's behavior** (FCC-01..07 note + `e2e_test_plan.md` §1): the
diff/file **content assertions are migrated, not rewritten** — the viewer's
behavior (file/diff tabs, split/unified + wrap + render toggles, find-in-file, line
numbers/expansion, moved-file rendering, loading bar only when a file is open, GFM +
sanitization, open-from-chat) is the same; only the **toggles' location** moves into
the triple-dot menu. The per-diff **expand/fullscreen toggle is deprecated** — do
**not** carry it forward (`get_expand_toggle`/`DIFF_EXPAND_TOGGLE`/`expandedPanelIdAtom`
are deleted; users maximize the section instead).

This task depends on **Task 1.3** (`explorerListWidthAtom`) and **Task 2.1**
(tokens). The three panels that embed these are **Task 3.3**; the POMs + tests are
**Task 3.6**.

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/panels/ExplorerLayout.tsx` +
  `.module.scss` — new (shared scaffold: list + viewer + empty + resizable shared
  width + sidebar toggle).
- `sculptor/frontend/src/pages/workspace/components/diffViewer/` — new embeddable
  `DiffViewer` assembled from the copied diff-panel pieces, with the config options
  under the triple-dot menu.
- `sculptor/sculptor/constants.py` — add/keep `DIFF_FILE_HEADER_MENU_TRIGGER` and
  the menu-item ids; **do not** add an expand-toggle id. (`just generate-api`.)

## Implementation details

1. `ExplorerLayout`: a generic scaffold taking a `list` slot and a `detail`
   (viewer) slot. Resizable splitter writing `explorerListWidthAtom` (shared
   global), min list 200px / min detail 280px; a sidebar-visibility toggle rendered
   in the **viewer header** (FCC-05); the viewer is always visible and shows the
   `EmptyDetail` empty state when nothing is selected (FCC-06).
2. `DiffViewer`: assemble from the copied `DiffPanel`/`DiffFileHeader`/`DiffSkeleton`/
   `InFileSearchBar`/`DiffScopePicker`. Move the toggle controls
   (`get_split_view_toggle`, `get_line_wrap_toggle`, `get_render_toggle`,
   `get_find_in_file_button` equivalents) **under the triple-dot menu**
   (`DIFF_FILE_HEADER_MENU_TRIGGER`) per FCC-07 + `harness_migration.md` §1. Keep the
   static (no-shimmer) skeleton; loading bar only when a file is open.
3. **Delete the expand/fullscreen toggle** — no `expand` control in the viewer
   header; do not add an `expand → maximize` alias (`harness_migration.md` §4;
   `naming_map.md`).
4. Keep the viewer **embeddable per panel** (each of Files/Changes/Commits embeds its
   own instance in Task 3.3) — no shared global "active diff" singleton.

## Testing suggestions

- The shared viewer is exercised once in `test_diff_viewer.py` and the explorer
  shape in the three panel tests — all in **Task 3.6**, which migrates the proven
  assertions from today's `test_file_browser*`/`test_history_panel*`/`test_diff_*`/
  `test_markdown_*` via the shared `DiffViewer`/`ExplorerLayout` POMs.
- Visual aspects (skeleton, empty state) are screenshot-verified, not asserted.

## Gotchas

- The list width is **global + shared** across all three panels — use the global
  slice, not per-panel state (FCC-04).
- The config toggles move **into the triple-dot menu** (FCC-07); selectors re-anchor
  under `DIFF_FILE_HEADER_MENU_TRIGGER`.
- The per-diff expand/fullscreen is **deprecated** — remove it, don't re-home it.
- Don't rewrite diff content behavior — only relocate the toggles and make the viewer
  embeddable.

## Verification checklist

- [ ] `ExplorerLayout`: resizable list (min 200px) + always-visible viewer (min
  280px) + empty state + sidebar toggle in the viewer header; width is the global
  shared atom.
- [ ] `DiffViewer` embeddable; config options under the triple-dot menu (FCC-07).
- [ ] No expand/fullscreen toggle anywhere.
- [ ] `DIFF_FILE_HEADER_MENU_TRIGGER` + menu-item ids present; `just generate-api`.
- [ ] `just check` passes.
