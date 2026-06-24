# Task 3.3: Files / Changes / Commits panels

## Goal

Build the three independent panels — Files, Changes, Commits — each embedding the
shared `ExplorerLayout` + `DiffViewer` from Task 3.2 with its own list sidebar
(file tree / changes browser / commit history). This replaces the old single
file-browser panel + diff pseudo-panel.

## Stories addressed

FCC-01 (three separate panels), FCC-02 (each renders its own viewer), FCC-03 (each
has its sidebar: file browser / changes browser / commit history), FCC-04..07 (via
the shared scaffold from Task 3.2).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`. Per
`goals.md` → "Files, Changes and Commits", files/changes/commits were one panel and
the diff/file viewer was a special pseudo-panel; the redesign makes **three
panels**, each with its own embedded viewer and its own sidebar.

**What to copy** (`design_extraction.md` → "Files / Changes / Commits & diff
viewer"): the list contents — `pages/workspace/panels/fileBrowser/FileTree.(tsx|
module.scss)` + `TreeRow.tsx` (28px pill rows, hover/active/deleted styling, line
stats, flat + tree variants); the changes browser + scope picker
(`ChangesTabContent` / `DiffScopePicker`) with discard + commit-from-changes; the
commit history (`historyPanel/HistoryTabContent.(tsx|module.scss)` + `CommitEntry.tsx`
— the commit graph dots, rows, popover, commit footer).

**Reuse existing content behavior:** the proven file-tree/diff/changes/history
behavior is preserved (`e2e_test_plan.md` §1: content is **migrated, not
rewritten**). Pull the current behavior from today's file-browser/history code on
`main` (grep `file_browser`, `historyPanel`, `ChangesTabContent`, `DiffScopePicker`)
and the prototype shape.

**Each panel is single-instance**, registered statically with `defaultSection:
"left"` (Task 1.6). They share the global explorer list width (Task 3.2).

This task depends on **Task 3.2** (`ExplorerLayout` + `DiffViewer`) and **Task
1.6** (`registerPanelComponent`).

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/panels/FilesPanel.tsx` (+ styles) — new:
  `ExplorerLayout` with the file tree as the list + `DiffViewer` as the detail.
- `sculptor/frontend/src/pages/workspace/panels/ChangesPanel.tsx` — new:
  changes browser + scope picker (All/Uncommitted) + discard + commit-from-changes +
  `DiffViewer`.
- `sculptor/frontend/src/pages/workspace/panels/CommitsPanel.tsx` — new: commit
  history list (terminus, merge spur, metadata, popover) + commit-scoped `DiffViewer`.
- Their `.module.scss` and any copied tree/history subcomponents.
- Register all three via `registerPanelComponent` (`files`/`changes`/`commits`).

## Implementation details

1. **FilesPanel:** embed `ExplorerLayout` with `FileTree` (flat + tree variants,
   from the prototype shape, reusing today's tree data) as the list and `DiffViewer`
   as the detail. Preserve path/tilde display, symlink handling, open-from-chat, and
   the open-diff-mode behavior (migrate from `test_file_browser*`/`test_path_tilde_
   display`/`test_file_browser_symlink*` content).
2. **ChangesPanel:** changes file browser + the scope picker (All / Uncommitted),
   discard-file, and commit-from-changes (clears after commit). Preserve target-branch
   behavior. (Migrate from `test_file_browser_uncommitted`/`test_commit_from_changes_
   tab`/`test_discard_*`/`test_diff_scope_switching`/`test_target_branch*` content.)
3. **CommitsPanel:** the commit graph (dots: gray / green = HEAD / amber-ring =
   uncommitted) + rows + popover + commit-scoped diffs in its own `DiffViewer`.
   (Migrate from `test_history_panel`/`test_history_panel_diffs` content.)
4. Register all three as single-instance static panels (Task 1.6 metadata already has
   them; this task supplies the components via `registerPanelComponent`).
5. The triple-dot menu in each viewer holds the relocated config options (FCC-07,
   from Task 3.2).

## Testing suggestions

- All FCC e2e + the migrated content tests land in **Tasks 3.6b–e** (POMs + open-a-panel
  helper: Task 3.6a) via the shared
  `DiffViewer`/`ExplorerLayout` POMs (`test_files_panel.py`,
  `test_changes_panel.py`, `test_commits_panel.py`, `test_diff_viewer.py`). This task
  just builds the panels so those tests have something to drive.

## Gotchas

- Three **separate** panels — do not keep a single file-browser panel with tabs (the
  old `FILE_BROWSER_TAB_*` ids are deleted in Phase 7).
- Each panel embeds **its own** viewer instance; no shared global active-diff.
- Preserve the existing content behaviors — they are migrated, not redesigned.
- The list width is shared/global (Task 3.2) — all three resize together.

## Verification checklist

- [ ] `FilesPanel`/`ChangesPanel`/`CommitsPanel` each embed `ExplorerLayout` +
  their own `DiffViewer` with the correct list (tree / changes / history).
- [ ] Changes scope picker, discard, and commit-from-changes preserved; commit graph
  + popover preserved.
- [ ] All three registered as single-instance `left`-default panels.
- [ ] `just check` passes.
