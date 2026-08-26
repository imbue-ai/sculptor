import { atom } from "jotai";
import { atomFamily, atomWithStorage, selectAtom } from "jotai/utils";

import { getCachedWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import { parseDiff } from "~/components/DiffUtils.ts";
import { jumpToSectionAtom, openPanelAtom } from "~/components/sections/sectionActions.ts";
import { activeWorkspaceIdAtom, workspaceLayoutFamily } from "~/components/sections/sectionAtoms.ts";
import type { DiffScope } from "~/pages/workspace/components/diffPanel/types.ts";

import type { FileBrowserState, FileStatus, ViewMode } from "./types.ts";
import { determineFileStatus } from "./utils.ts";

const FILE_BROWSER_PANEL_ID = "files";

type FolderStateKey = "expandedFolders" | "changesExpandedFolders";

const DEFAULT_FILE_BROWSER_STATE: FileBrowserState = {
  expandedFolders: [],
  changesExpandedFolders: [],
  changesAutoExpandedFolders: [],
  viewMode: "tree",
  searchQuery: "",
  searchOpen: false,
  scrollPosition: 0,
};

export const fileBrowserStateAtomFamily = atomFamily((workspaceId: string) =>
  atomWithStorage<FileBrowserState>(`fileBrowser-state-${workspaceId}`, DEFAULT_FILE_BROWSER_STATE),
);

/** Read-only per-workspace slice of the file-browser view mode (tree vs flat).
 *  Panels that only need the view mode subscribe here so the far more frequent
 *  folder-expand, scroll-position, and search writes to the full state atom don't
 *  re-render them (and their embedded viewers). */
export const fileBrowserViewModeAtomFamily = atomFamily((workspaceId: string) =>
  selectAtom(fileBrowserStateAtomFamily(workspaceId), (state) => state.viewMode),
);

/**
 * Build a path → FileStatus map from the cached uncommittedDiff for a
 * workspace. Used by the `openFileFromUiEvent` write atom for `--mode auto`
 * resolution (a one-shot read that doesn't need Jotai subscription).
 *
 * Returns an empty map if the diff hasn't been fetched yet — `--mode auto`
 * then falls back to file-view, which is the documented behavior.
 */
export const getUncommittedFileStatusMap = (
  workspaceId: string,
  targetBranch: string | null,
): Map<string, FileStatus> => {
  const diff = getCachedWorkspaceDiff(workspaceId, targetBranch);
  const map = new Map<string, FileStatus>();
  const diffString = diff?.uncommittedDiff;
  if (!diffString) {
    return map;
  }
  const parsed = parseDiff(diffString);
  for (const fileChange of parsed.fileChanges) {
    const { referenceFileName } = fileChange.fileNames;
    map.set(referenceFileName, determineFileStatus(fileChange));
  }
  return map;
};

/** Per-workspace scope for the Changes tab (independent of the Review All scope). Resets on page refresh. */
export const changesScopeAtomFamily = atomFamily((_workspaceId: string) => atom<DiffScope>("vs-target-branch"));

/** The Changes panel's clicked file selection (filePath + reported status, stamped for
 *  recency reconciliation). Held per-workspace in an atom — not React state — so the
 *  open file survives the panel unmounting when the user switches section tabs. */
export type ChangesPanelSelection = { filePath: string; status: FileStatus; at: number };
export const changesPanelSelectionAtomFamily = atomFamily((_workspaceId: string) =>
  atom<ChangesPanelSelection | null>(null),
);

/** The Files panel's clicked file selection (stamped for recency reconciliation).
 *  Held per-workspace in an atom — not React state — so the open file survives the
 *  panel remounting on a section-tab switch or a section maximize/restore. */
export type FilesPanelSelection = { filePath: string; at: number };
export const filesPanelSelectionAtomFamily = atomFamily((_workspaceId: string) =>
  atom<FilesPanelSelection | null>(null),
);

// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
const createToggleFolderAtom = (key: FolderStateKey) =>
  atom(null, (get, set, { workspaceId, folderPath }: { workspaceId: string; folderPath: string }) => {
    const stateAtom = fileBrowserStateAtomFamily(workspaceId);
    const state = get(stateAtom);
    const folders = new Set(state[key]);
    if (folders.has(folderPath)) {
      folders.delete(folderPath);
    } else {
      folders.add(folderPath);
    }
    set(stateAtom, { ...state, [key]: Array.from(folders) });
  });

// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
const createExpandFoldersAtom = (key: FolderStateKey) =>
  atom(null, (get, set, { workspaceId, paths }: { workspaceId: string; paths: Array<string> }) => {
    const stateAtom = fileBrowserStateAtomFamily(workspaceId);
    const state = get(stateAtom);
    const folders = new Set(state[key]);
    for (const path of paths) {
      folders.add(path);
    }
    set(stateAtom, { ...state, [key]: Array.from(folders) });
  });

export const toggleFolderAtom = createToggleFolderAtom("expandedFolders");
export const expandFoldersAtom = createExpandFoldersAtom("expandedFolders");

export const toggleChangesFolderAtom = createToggleFolderAtom("changesExpandedFolders");
export const expandChangesFoldersAtom = createExpandFoldersAtom("changesExpandedFolders");

export const collapseAllFoldersAtom = atom(null, (get, set, { workspaceId }: { workspaceId: string }) => {
  const stateAtom = fileBrowserStateAtomFamily(workspaceId);
  const state = get(stateAtom);
  set(stateAtom, { ...state, expandedFolders: [] });
});

export const collapseAllChangesFoldersAtom = atom(null, (get, set, { workspaceId }: { workspaceId: string }) => {
  const stateAtom = fileBrowserStateAtomFamily(workspaceId);
  const state = get(stateAtom);
  set(stateAtom, { ...state, changesExpandedFolders: [] });
});

export const toggleViewModeAtom = atom(null, (get, set, { workspaceId }: { workspaceId: string }) => {
  const stateAtom = fileBrowserStateAtomFamily(workspaceId);
  const state = get(stateAtom);
  const viewMode: ViewMode = state.viewMode === "tree" ? "flat" : "tree";
  set(stateAtom, { ...state, viewMode });
});

// Folder reveal: expand ancestors, show the file browser panel, and signal
// FileTree to scroll + briefly highlight the row. Used by @-folder mention
// chips in chat messages.

export type FocusFolderRequest = {
  workspaceId: string;
  path: string;
  nonce: number;
};

export const focusFolderAtom = atom<FocusFolderRequest | null>(null);

const computeAncestorFolderPaths = (folderPath: string): Array<string> => {
  const segments = folderPath.split("/").filter((s) => s.length > 0);
  const ancestors: Array<string> = [];
  for (let i = 0; i < segments.length; i += 1) {
    ancestors.push(segments.slice(0, i + 1).join("/"));
  }
  return ancestors;
};

export const revealFolderAtom = atom(null, (get, set, { workspaceId, path }: { workspaceId: string; path: string }) => {
  // Path-mode mentions (e.g. selected after drilling into a folder with Tab)
  // carry a "./" prefix in their chip id — the file tree's node paths are
  // workspace-relative without that prefix, so strip it before matching.
  // Absolute ("/...") and home-relative ("~/...") paths point outside the
  // workspace; they'll fail the row lookup and surface the "not viewable"
  // toast, which is the correct outcome.
  const withoutDotSlash = path.startsWith("./") ? path.slice(2) : path;
  const normalised = withoutDotSlash.replace(/\/+$/, "");
  if (normalised.length === 0) return;

  set(expandFoldersAtom, { workspaceId, paths: computeAncestorFolderPaths(normalised) });

  // Surface the Files panel (opening/expanding its section and pulsing the ring) so the
  // revealed folder is visible. openPanelAtom/jumpToSectionAtom write through the
  // active-workspace layout proxy, so only touch the layout when this workspace is the
  // active scope — otherwise the reveal would mutate the layout of the workspace being viewed.
  if (workspaceId === get(activeWorkspaceIdAtom)) {
    set(openPanelAtom, { panelId: FILE_BROWSER_PANEL_ID, in: "left" });
    // Follow the panel's actual placement: openPanelAtom activates an already-open Files
    // panel wherever it lives, so jumping to "left" would pulse the wrong section when the
    // user has moved it elsewhere. "left" is the fallback for a newly placed panel.
    const subSection = get(workspaceLayoutFamily(workspaceId)).placement[FILE_BROWSER_PANEL_ID] ?? "left";
    set(jumpToSectionAtom, { subSection });
  }

  set(focusFolderAtom, { workspaceId, path: normalised, nonce: Date.now() });
});

export const setSearchAtom = atom(
  null,
  (get, set, { workspaceId, query, open }: { workspaceId: string; query: string; open: boolean }) => {
    const stateAtom = fileBrowserStateAtomFamily(workspaceId);
    const state = get(stateAtom);
    set(stateAtom, { ...state, searchQuery: query, searchOpen: open });
  },
);
