# SCU-1746 execution plan — reconciled rulings + stage order

The three classification maps (move-map-components.md, move-map-workspace.md,
move-map-common.md) are approved with the reconciliations below. Where this file
contradicts a map, THIS FILE WINS. Stages execute sequentially; each stage is one
commit that passes `just format && just check && just test-unit`.

## Reconciliation rulings

1. **Post-dissolution targets.** move-map-components.md wrote workspace targets
   under `pages/workspace/components/...`; that dir dissolves. Corrected targets:
   - filePreview cluster → `pages/workspace/filePreview/`
   - `FileUpload.tsx`, `SendButton.tsx` → `pages/workspace/chatAlpha/` (they are
     ChatInput-only; they follow it)
   - `CapabilityGate.tsx` → `pages/workspace/chatAlpha/` (ChatInput +
     QueuedMessageBar; queuedMessages imports cross-feature — normal compose)
   - `VerticalOverlayScrollbar.tsx` → stays flat at `pages/workspace/` root
     (area-shared component used by chatAlpha + fileBrowser)
   - `IndeterminateProgress.tsx` → `pages/workspace/diffViewer/`
   - `MarkdownDiff/` → `pages/workspace/diffPanel/markdownDiff/` (subfeature of
     its only consumer — feature/subfeature/kind is within the depth cap; the
     components map's "sibling" note misread the cap)
2. **`useWorkspaceTabActions` → `common/state/hooks/`** (components map wins over
   decisions.md #6 — app/ cannot be imported by components/commandPalette, and
   the hook fronts tab state). `workspaceTabIds` → `common/utils/`.
3. **`copyImageToClipboard` follows its consumer** into
   `pages/workspace/filePreview/` (the common map's `components/` target predates
   the cluster move).
4. **Layout state split (the hairy one).** Global layout state (globalLayoutAtom,
   the sidebar width/collapse slices from components/layout/sidebarAtoms.ts, and
   whatever global-snapshot atoms they slice) → `common/state/atoms/layout.ts` —
   it is consumed by nav, commandPalette, shell, and workspace, so it is shared
   state by our own rule. Per-workspace layout atoms, transient drag/maximize
   state, dnd, and the registry stay in `pages/workspace/layout/atoms/` per the
   deterministic map. If the global/per-workspace entanglement can't be split
   mechanically (shared persistence adapter etc.), FALLBACK: keep all of it
   feature-side (sidebarAtoms → pages/workspace/layout/atoms/sidebar.ts), and the
   import-boundary lint (stage H) carries explicit temporary exceptions for the
   commandPalette/nav/shell readers, catalogued for a follow-up ticket. Do not
   force a half-split.
5. **Electron bridge types**: preload contract (`SculptorElectronAPI` et al.) →
   `electron/bridge.ts`; the renderer-domain unions (`BackendStatus*`,
   `AutoUpdateStatus`, `UpdateChannel`) → `common/types/backend.ts` so `common/`
   never imports `electron/`.
6. **`onboarding-wizard/` → `pages/onboarding/`** (it is a full-screen surface;
   pages/ = surfaces the user lands on, gate-entered or routed).
7. **`workspaceChrome/` keeps that name** (`chrome/` collides conceptually with
   the browser panel; `shell/` collides with the app shell). It absorbs
   WorkspaceLayoutShell + WorkspaceHeader per the workspace map's §6.
8. **Peek promotion approved** (workspacePeek, prButton, diffSummary,
   parseDiffStats per workspace map §7); rename the peek dot wrapper
   `PeekAgentStatusDot` to break the collision.
9. **`RepoSegment.tsx` delete approved** — executor re-verifies zero importers at
   execution time before deleting.
10. **Generic-basename fixes are NOT deferrable** (the stage-H blocklist must
    pass): diffPanel/diffViewer internal `atoms.ts`/`types.ts` and the nine
    feature `atoms.ts` files all get topic/feature names in stage F.

## Stages (one commit each)

- **A — app/ shell**: create `app/` (App, Router, EmptyFirstRunGate,
  `components/nav/` → `app/nav/`, `layouts/` → `app/` with hooks in `app/hooks/`,
  `src/hooks/` dissolved per move-map.md step 2, shell-wired components from
  move-map-components.md "app-shell" rows); `apiClient.ts` → `common/`;
  ruling 2 moves.
- **B — layout**: `components/sections/` → `pages/workspace/layout/` per
  move-map.md deterministic map + ruling 4; `components/layout/` dissolves.
- **C — workspace dissolution**: move-map-workspace.md §§1-9 with rulings 1, 3,
  8, 9.
- **D — components/ cleanup**: move-map-components.md (editor/ cluster, feature
  strays, casing renames incl. commandPalette internal anatomy, ruling 6).
- **E — common/ cleanup**: move-map-common.md with rulings 3, 5.
- **F — basename sweep**: remaining generic basenames tree-wide (feature
  `atoms.ts` files → kind-dir topic files, keybindings renames per common map §7).
- **G — stories mirror realignment** to all new paths.
- **H — lint layer**: eslint-plugin-check-file (camelCase folders, basename
  blocklist) + import/no-restricted-paths layering with an explicit, commented
  exception list; violations catalogued in decisions.md.
- **I — task → agent rename** (SCU-1736): file renames, then identifier renames.

After G: rerun the 10-prompt inferability test (prompts in the session memory
baseline) and record the delta in decisions.md.
