import { atom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { jumpToSectionAtom, openPanelAtom } from "~/components/sections/sectionActions.ts";
import { isEmptyLayout, workspaceLayoutFamily } from "~/components/sections/sectionAtoms.ts";
import type { PanelId, SubSectionId } from "~/components/sections/sectionTypes.ts";
import type { DiffSelection } from "~/pages/workspace/components/diffViewer/types.ts";
import { getUncommittedFileStatusMap } from "~/pages/workspace/panels/fileBrowser/atoms.ts";
import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";

import type { DiffPanelTabState, DiffScope, DiffTab, SingleFileDiffTab } from "./types.ts";
import { COMBINED_REVIEW_PATH, COMMIT_DIFF_PREFIX, FILE_VIEW_PREFIX, TARGET_BRANCH_DIFF_PREFIX } from "./types.ts";

// The single-instance panel (and its default section) that hosts the active diff/
// file-view tab in the new section shell. file-view tabs surface in the Files
// panel; single/combined diffs surface in the Changes panel; commit-scoped diffs
// surface in the Commits panel. Each panel's embedded DiffViewer renders the active
// tab (DIFF_PANEL); revealing the panel here is what makes that viewer visible.
const HOST_PANEL_BY_KIND: Record<SetActiveDiffPayload["kind"], { panelId: PanelId; section: SubSectionId }> = {
  single: { panelId: "changes", section: "left" },
  combined: { panelId: "changes", section: "left" },
  "file-view": { panelId: "files", section: "left" },
  "commit-diff": { panelId: "commits", section: "left" },
};

/** Transient per-workspace scope for the combined diff view. Resets on page refresh. */
export const diffScopeAtomFamily = atomFamily((_workspaceId: string) => atom<DiffScope>("uncommitted"));

/** Debounce (ms) before persisting panel layout preferences to localStorage. */
const STORAGE_DEBOUNCE_MS = 200;

/** Ratio (0–100) controlling the left/right column split in side-by-side diffs. */
export const splitDiffColumnRatioAtom = atom(50);

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
 * The active diff tab for a workspace (the `DiffTab` whose path is `activeTabPath`),
 * or null when no tab is active. Each host panel (Files / Changes / Commits) reads
 * this so an agent-opened file/diff — which writes the tab via `setActiveDiffTabAtom`
 * but never touches the panel's local click state — still renders in the panel's
 * single embedded DiffViewer. Local tree clicks keep driving the panel directly; the
 * panel reconciles the two by most-recent-`viewedAt` (see the host panels).
 */
export const activeDiffTabAtomFamily = atomFamily((workspaceId: string) =>
  atom<DiffTab | null>((get) => {
    const state = get(diffPanelStateAtomFamily(workspaceId));
    if (state.activeTabPath === null) {
      return null;
    }
    return state.openTabs.find((tab) => tab.filePath === state.activeTabPath) ?? null;
  }),
);

/** The real file path a single-diff tab targets (its tab id strips a scope prefix). */
const singleTabRealPath = (tab: SingleFileDiffTab): string =>
  tab.filePath.startsWith(TARGET_BRANCH_DIFF_PREFIX)
    ? tab.filePath.slice(TARGET_BRANCH_DIFF_PREFIX.length)
    : tab.filePath;

/**
 * Map the active diff tab to the {@link DiffSelection} the Files panel's embedded
 * viewer renders — only `file-view` tabs belong to the Files panel. Returns null for
 * any other kind so an agent-opened diff/commit doesn't bleed into the Files viewer.
 */
export const fileViewSelectionFromTab = (tab: DiffTab | null): DiffSelection | null => {
  if (tab === null || tab.kind !== "file-view") {
    return null;
  }
  return { kind: "file-view", filePath: tab.realPath, tabFilePath: tab.filePath };
};

/**
 * Map the active diff tab to the {@link DiffSelection} the Changes panel renders —
 * only `single` (file-vs-changes) tabs belong here. Returns null for any other kind.
 */
export const changesSelectionFromTab = (tab: DiffTab | null): DiffSelection | null => {
  if (tab === null || tab.kind !== "single") {
    return null;
  }
  return {
    kind: "diff",
    filePath: singleTabRealPath(tab),
    status: tab.status,
    scope: tab.scope,
    diffString: tab.diffString,
    tabFilePath: tab.filePath,
  };
};

/**
 * Map the active diff tab to the {@link DiffSelection} the Commits panel renders —
 * only `commit-diff` tabs belong here. Returns null for any other kind.
 */
export const commitSelectionFromTab = (tab: DiffTab | null): DiffSelection | null => {
  if (tab === null || tab.kind !== "commit-diff") {
    return null;
  }
  return { kind: "commit-diff", commitHash: tab.commitHash, filePath: tab.realPath, tabFilePath: tab.filePath };
};

/**
 * Whether the diff viewer column is visible.  Stored globally by default so
 * the panel behaves like the other docked panels (a single shared open/close
 * state across workspaces).  When the experimental "per-workspace panel
 * layout" flag is enabled, `usePerWorkspacePanelLayout` saves/restores this
 * value per workspace on switch — mirroring how zone visibility is handled.
 */
export const diffPanelOpenAtom = atomWithDebouncedStorage<boolean>(
  "sculptor-diffPanel-open",
  false,
  STORAGE_DEBOUNCE_MS,
);

/**
 * Diff/chat split ratio (0–100).  Global with optional per-workspace
 * override, parallelling `diffPanelOpenAtom`.
 */
export const diffPanelSplitRatioAtom = atomWithDebouncedStorage<number>(
  "sculptor-diffPanel-splitRatio",
  50,
  STORAGE_DEBOUNCE_MS,
);

/** Global preference for how `.md` / `.markdown` files are shown in ReadOnlyPreview. */
type MarkdownRenderMode = "raw" | "rendered";
export const markdownRenderModeAtom = atomWithStorage<MarkdownRenderMode>("diffPanel-markdownRenderMode", "rendered");

/** Cap for the viewer header's recently-viewed file dropdown. */
const MAX_RECENT_FILES = 10;

/** Which panel a viewer header belongs to — each keeps its own recents list. */
export type RecentFilesPanel = "files" | "changes" | "commits";

/**
 * A recently viewed file: the workspace-relative path, plus (for Commits-panel
 * entries) the commit the view was scoped to, so re-opening lands back in that
 * exact commit's diff.
 */
export type RecentDiffFile = { path: string; commitHash?: string };

const recentFilesKey = (workspaceId: string, panel: RecentFilesPanel): string => `${panel}-${workspaceId}`;

/**
 * Recently viewed files per workspace AND per panel — the Files / Changes /
 * Commits panels each keep an independent list (a file viewed in Changes must
 * not appear in the Files dropdown). Newest first, deduped, capped at
 * {@link MAX_RECENT_FILES}. Fed by each panel's viewer header whenever it
 * shows a file; drives that header's path dropdown.
 */
const recentDiffFilesByKeyAtomFamily = atomFamily((key: string) =>
  atomWithStorage<Array<RecentDiffFile>>(`diffPanel-recentFiles-${key}`, []),
);

// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
export const recentDiffFilesAtomFamily = (workspaceId: string, panel: RecentFilesPanel) =>
  recentDiffFilesByKeyAtomFamily(recentFilesKey(workspaceId, panel));

/** Move (or insert) a file to the front of a panel's recently-viewed list. */
export const recordRecentDiffFileAtom = atom(
  null,
  (
    get,
    set,
    { workspaceId, panel, entry }: { workspaceId: string; panel: RecentFilesPanel; entry: RecentDiffFile },
  ) => {
    const listAtom = recentDiffFilesAtomFamily(workspaceId, panel);
    const prev = get(listAtom);
    const isSameEntry = (candidate: RecentDiffFile): boolean =>
      candidate.path === entry.path && candidate.commitHash === entry.commitHash;
    if (prev[0] !== undefined && isSameEntry(prev[0])) {
      return;
    }
    set(listAtom, [entry, ...prev.filter((candidate) => !isSameEntry(candidate))].slice(0, MAX_RECENT_FILES));
  },
);

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

  // Reveal the host panel in the new section shell: open + expand its section and
  // make it active so the embedded DiffViewer (DIFF_PANEL) becomes visible. In the
  // old docking shell this was a single `diffPanelOpenAtom` flag; that atom is dead
  // in the section shell (no component consumes it), so revealing the host panel in
  // the section layout is what actually surfaces the viewer. The legacy flag is
  // still written below for backwards compatibility with code/tests that read it.
  //
  // Guard against an UNSEEDED layout: the workspace-shell bootstrap seeds the default
  // arrangement (Files/Changes/Commits in the left section, the agent in center, …)
  // on a workspace's first visit, gated on `isEmptyLayout`. If an open-file event
  // races that bootstrap (e.g. a buffered WebSocket OpenFileUiAction landing in the
  // same tick as mount), opening a single host panel here would place it ALONE in the
  // left section and flip `isEmptyLayout` to false, so the bootstrap would skip seeding
  // and Files/Changes/Commits would never appear. Skip the reveal until the layout is
  // seeded; the tab is already recorded above, so once the bootstrap seeds the default
  // and the user expands the host panel, the viewer renders the right file.
  const layout = get(workspaceLayoutFamily(payload.workspaceId));
  if (!isEmptyLayout(layout)) {
    const host = HOST_PANEL_BY_KIND[payload.kind];
    set(openPanelAtom, { panelId: host.panelId, in: host.section });
    set(jumpToSectionAtom, { subSection: host.section });
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
 * file-view when the prefixes don't match. The file-view fallback is the
 * intended behavior here, not an error path.
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
      // than the panel collapsing out from under them.
      set(stateAtom, { ...state, openTabs: [], activeTabPath: null });
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
  // Leave the panel open and show the empty placeholder.
  set(stateAtom, { ...state, openTabs: [], activeTabPath: null });
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
