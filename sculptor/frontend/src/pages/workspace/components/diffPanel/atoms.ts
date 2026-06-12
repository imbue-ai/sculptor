import { atom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { expandedPanelIdAtom, zoneAssignmentsAtom } from "~/components/panels/atoms.ts";
import { getUncommittedFileStatusMap } from "~/pages/workspace/panels/fileBrowser/atoms.ts";
import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";

import type { DiffPanelTabState, DiffScope, DiffTab, SplitPosition } from "./types.ts";
import { COMBINED_REVIEW_PATH, COMMIT_DIFF_PREFIX, FILE_VIEW_PREFIX, TARGET_BRANCH_DIFF_PREFIX } from "./types.ts";

/** Transient per-workspace scope for the combined diff view. Resets on page refresh. */
export const diffScopeAtomFamily = atomFamily((_workspaceId: string) => atom<DiffScope>("uncommitted"));

/** Ratio (0–100) controlling the left/right column split in side-by-side diffs. */
export const splitDiffColumnRatioAtom = atom(50);

/** Derives the side ("left" | "right") of the chat where the diff viewer should
 *  appear based on which docking zone the file browser panel is assigned to. */
export const fileBrowserDockSideAtom = atom<SplitPosition>((get) => {
  const assignments = get(zoneAssignmentsAtom);
  const filesZone = assignments["files"];
  if (filesZone && filesZone.includes("left")) {
    return "left";
  }
  return "right";
});

const DEFAULT_DIFF_PANEL_TAB_STATE: DiffPanelTabState = {
  openTabs: [],
  activeTabPath: null,
};

/**
 * Tab list and active tab — inherently per-workspace since each workspace
 * has its own set of files.
 */
export const diffPanelStateAtomFamily = atomFamily((workspaceId: string) =>
  atomWithStorage<DiffPanelTabState>(`diffPanel-state-${workspaceId}`, DEFAULT_DIFF_PANEL_TAB_STATE),
);

/**
 * Whether the diff viewer column is visible.  Stored globally by default so
 * the panel behaves like the other docked panels (a single shared open/close
 * state across workspaces).  When the experimental "per-workspace panel
 * layout" flag is enabled, `usePerWorkspacePanelLayout` saves/restores this
 * value per workspace on switch — mirroring how zone visibility is handled.
 */
export const diffPanelOpenAtom = atomWithDebouncedStorage<boolean>("sculptor-diffPanel-open", false, 200);

/**
 * Diff/chat split ratio (0–100).  Global with optional per-workspace
 * override, parallelling `diffPanelOpenAtom`.
 */
export const diffPanelSplitRatioAtom = atomWithDebouncedStorage<number>("sculptor-diffPanel-splitRatio", 50, 200);

/** Global preference for how `.md` / `.markdown` files are shown in ReadOnlyPreview. */
type MarkdownRenderMode = "raw" | "rendered";
export const markdownRenderModeAtom = atomWithStorage<MarkdownRenderMode>("diffPanel-markdownRenderMode", "rendered");

export const isMarkdownPath = (filePath: string): boolean => /\.(md|markdown)$/i.test(filePath);

// ---------------------------------------------------------------------------
// Discriminated union payload for the unified setActiveDiffTabAtom
// ---------------------------------------------------------------------------

type SetActiveSingleDiff = {
  kind: "single";
  workspaceId: string;
  filePath: string;
  status: FileStatus;
  scope?: DiffScope;
  diffString?: string;
};

type SetActiveCombinedDiff = {
  kind: "combined";
  workspaceId: string;
  defaultScope?: DiffScope;
};

type SetActiveFileView = {
  kind: "file-view";
  workspaceId: string;
  filePath: string;
};

type SetActiveCommitDiff = {
  kind: "commit-diff";
  workspaceId: string;
  commitHash: string;
  filePath: string;
};

type SetActiveDiffPayload = SetActiveSingleDiff | SetActiveCombinedDiff | SetActiveFileView | SetActiveCommitDiff;

/**
 * Build a DiffTab and its identity key from a discriminated union payload.
 * All three tab types share the same "find-or-create, then activate" logic.
 */
const buildTabFromPayload = (payload: SetActiveDiffPayload, now: number): { tab: DiffTab; tabPath: string } => {
  switch (payload.kind) {
    case "single": {
      const tabPath =
        payload.scope === "vs-target-branch" ? TARGET_BRANCH_DIFF_PREFIX + payload.filePath : payload.filePath;
      return {
        tab: {
          kind: "single",
          filePath: tabPath,
          status: payload.status,
          scope: payload.scope,
          viewedAt: now,
          diffString: payload.diffString,
        },
        tabPath,
      };
    }
    case "combined":
      return {
        tab: {
          kind: "combined",
          filePath: COMBINED_REVIEW_PATH,
          defaultScope: payload.defaultScope,
          viewedAt: now,
        },
        tabPath: COMBINED_REVIEW_PATH,
      };
    case "file-view": {
      const tabPath = FILE_VIEW_PREFIX + payload.filePath;
      return {
        tab: { kind: "file-view", filePath: tabPath, realPath: payload.filePath, viewedAt: now },
        tabPath,
      };
    }

    case "commit-diff": {
      const tabPath = COMMIT_DIFF_PREFIX + payload.commitHash + ":" + payload.filePath;
      return {
        tab: {
          kind: "commit-diff",
          filePath: tabPath,
          commitHash: payload.commitHash,
          realPath: payload.filePath,
          viewedAt: now,
        },
        tabPath,
      };
    }
  }
};

/**
 * Unified atom that activates (or opens) a diff tab of any kind.
 * Replaces the previous `openDiffTabAtom`, `openCombinedDiffTabAtom`, and
 * `openFileViewTabAtom` — which were ~90% identical.
 */
export const setActiveDiffTabAtom = atom(null, (get, set, payload: SetActiveDiffPayload) => {
  const stateAtom = diffPanelStateAtomFamily(payload.workspaceId);
  const state = get(stateAtom);
  const now = Date.now();

  const { tab, tabPath } = buildTabFromPayload(payload, now);

  const existingIndex = state.openTabs.findIndex((t) => t.filePath === tabPath);
  if (existingIndex >= 0) {
    const updatedTabs = state.openTabs.map((t, i) => (i === existingIndex ? { ...t, viewedAt: now } : t));
    set(stateAtom, { ...state, openTabs: updatedTabs, activeTabPath: tabPath });
  } else {
    set(stateAtom, {
      ...state,
      openTabs: [...state.openTabs, tab],
      activeTabPath: tabPath,
    });
  }
  set(diffPanelOpenAtom, true);

  // When opening a combined tab with a default scope, set the scope atom.
  if (payload.kind === "combined" && payload.defaultScope) {
    set(diffScopeAtomFamily(payload.workspaceId), payload.defaultScope);
  }
});

/**
 * Receives an OpenFileUiAction from the backend WebSocket and activates the
 * right tab in the target workspace's diff panel:
 *   - mode="file" → file-view tab (always)
 *   - mode="diff" → single diff tab; status defaults to "M" if absent.
 *   - mode="auto" → single diff tab if the file has uncommitted changes,
 *     else file-view.
 *
 * Path-prefix limitation: status-map keys are git-relative (e.g.
 * "sculptor/web/app.py") while filePath in the event is absolute. For paths
 * inside the workspace clone this means auto-resolution may fall back to
 * file-view when the prefixes don't match. Acceptable for v1; spec
 * (architecture §4.2) explicitly allows the file-view fallback.
 */
export const openFileFromUiEventAtom = atom(
  null,
  (get, set, payload: { workspaceId: string; filePath: string; mode: "auto" | "file" | "diff" }) => {
    const { workspaceId, filePath, mode } = payload;

    if (mode === "file") {
      set(setActiveDiffTabAtom, { kind: "file-view", workspaceId, filePath });
      return;
    }

    const workspace = get(workspaceAtomFamily(workspaceId));
    const targetBranch = workspace?.targetBranch ?? null;
    const statusMap = getUncommittedFileStatusMap(workspaceId, targetBranch);
    const status = statusMap.get(filePath);

    if (mode === "diff") {
      set(setActiveDiffTabAtom, {
        kind: "single",
        workspaceId,
        filePath,
        status: status ?? "M",
      });
      return;
    }

    // mode === "auto"
    if (status !== undefined) {
      set(setActiveDiffTabAtom, { kind: "single", workspaceId, filePath, status });
    } else {
      set(setActiveDiffTabAtom, { kind: "file-view", workspaceId, filePath });
    }
  },
);

// Convenience aliases so callers don't need to construct the discriminated union
// when they already know the tab kind.

/** Open (or activate) a single-file diff tab. */
export const openDiffTabAtom = atom(
  null,
  (
    _get,
    set,
    params: { workspaceId: string; filePath: string; status: FileStatus; scope?: DiffScope; diffString?: string },
  ) => {
    set(setActiveDiffTabAtom, { kind: "single", ...params });
  },
);

/** Open (or activate) the combined "Review All" tab. */
export const openCombinedDiffTabAtom = atom(
  null,
  (_get, set, params: { workspaceId: string; defaultScope?: DiffScope }) => {
    set(setActiveDiffTabAtom, { kind: "combined", ...params });
  },
);

/** Open (or activate) a read-only file view tab. */
export const openFileViewTabAtom = atom(null, (_get, set, params: { workspaceId: string; filePath: string }) => {
  set(setActiveDiffTabAtom, { kind: "file-view", ...params });
});

/** Open (or activate) a commit-scoped file diff tab. */
export const openCommitDiffTabAtom = atom(
  null,
  (_get, set, params: { workspaceId: string; commitHash: string; filePath: string }) => {
    set(setActiveDiffTabAtom, { kind: "commit-diff", ...params });
  },
);

export const closeDiffTabAtom = atom(
  null,
  (
    get,
    set,
    {
      workspaceId,
      filePath,
      tabCloseBehavior,
    }: { workspaceId: string; filePath: string; tabCloseBehavior: "mru" | "adjacent" },
  ) => {
    const stateAtom = diffPanelStateAtomFamily(workspaceId);
    const state = get(stateAtom);

    const closingIndex = state.openTabs.findIndex((tab) => tab.filePath === filePath);
    if (closingIndex < 0) {
      return;
    }

    const remainingTabs = state.openTabs.filter((tab) => tab.filePath !== filePath);

    if (remainingTabs.length === 0) {
      // Leave the panel open so the user sees the empty placeholder rather
      // than the panel collapsing out from under them.  Exit expand mode
      // since a fullscreened empty placeholder is poor UX.
      set(stateAtom, { ...state, openTabs: [], activeTabPath: null });
      set(expandedPanelIdAtom, null);
      return;
    }

    let nextActiveTabPath = state.activeTabPath;
    if (state.activeTabPath === filePath) {
      if (tabCloseBehavior === "mru") {
        const sorted = [...remainingTabs].sort((a, b) => b.viewedAt - a.viewedAt);
        nextActiveTabPath = sorted[0].filePath;
      } else {
        const nextIndex = Math.min(closingIndex, remainingTabs.length - 1);
        nextActiveTabPath = remainingTabs[nextIndex].filePath;
      }
    }

    set(stateAtom, { ...state, openTabs: remainingTabs, activeTabPath: nextActiveTabPath });
  },
);

export const closeDiffPanelAtom = atom(null, (_get, set) => {
  set(diffPanelOpenAtom, false);
  set(expandedPanelIdAtom, null);
});

export const closeOtherDiffTabsAtom = atom(
  null,
  (get, set, { workspaceId, filePath }: { workspaceId: string; filePath: string }) => {
    const stateAtom = diffPanelStateAtomFamily(workspaceId);
    const state = get(stateAtom);
    const keptTab = state.openTabs.find((tab) => tab.filePath === filePath);
    if (!keptTab) return;
    set(stateAtom, { ...state, openTabs: [keptTab], activeTabPath: keptTab.filePath });
  },
);

export const closeAllDiffTabsAtom = atom(null, (get, set, { workspaceId }: { workspaceId: string }) => {
  const stateAtom = diffPanelStateAtomFamily(workspaceId);
  const state = get(stateAtom);
  // Leave the panel open and show the empty placeholder, but drop expand mode.
  set(stateAtom, { ...state, openTabs: [], activeTabPath: null });
  set(expandedPanelIdAtom, null);
});

/** Reorder tabs to match the given path order (e.g. after a drag-and-drop). */
export const reorderTabsAtom = atom(
  null,
  (get, set, { workspaceId, newOrder }: { workspaceId: string; newOrder: Array<string> }) => {
    const stateAtom = diffPanelStateAtomFamily(workspaceId);
    const state = get(stateAtom);
    const tabsByPath = new Map(state.openTabs.map((tab) => [tab.filePath, tab]));
    const reordered = newOrder.flatMap((path) => {
      const tab = tabsByPath.get(path);
      return tab ? [tab] : [];
    });
    set(stateAtom, { ...state, openTabs: reordered });
  },
);
