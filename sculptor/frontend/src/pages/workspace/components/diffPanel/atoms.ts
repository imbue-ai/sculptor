import { atom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { jumpToSectionAtom, openPanelAtom } from "~/components/sections/sectionActions.ts";
import { activeWorkspaceIdAtom, isEmptyLayout, workspaceLayoutFamily } from "~/components/sections/sectionAtoms.ts";
import type { PanelId, SubSectionId } from "~/components/sections/sectionTypes.ts";
import type { DiffSelection } from "~/pages/workspace/components/diffViewer/types.ts";
import { getUncommittedFileStatusMap } from "~/pages/workspace/panels/fileBrowser/atoms.ts";
import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";

import type { DiffPanelTabState, DiffScope, DiffTab, SingleFileDiffTab } from "./types.ts";
import { COMMIT_DIFF_PREFIX, FILE_VIEW_PREFIX, TARGET_BRANCH_DIFF_PREFIX } from "./types.ts";

// The single-instance panel (and its default section) that hosts the active diff/
// file-view tab in the section shell. file-view tabs surface in the Files panel;
// single diffs surface in the Changes panel; commit-scoped diffs surface in the
// Commits panel. Each panel's embedded DiffViewer renders the active tab
// (DIFF_PANEL); revealing the panel here is what makes that viewer visible.
const HOST_PANEL_BY_KIND: Record<SetActiveDiffPayload["kind"], { panelId: PanelId; section: SubSectionId }> = {
  single: { panelId: "changes", section: "left" },
  "file-view": { panelId: "files", section: "left" },
  "commit-diff": { panelId: "commits", section: "left" },
};

/** Transient per-workspace scope for the combined diff view. Resets on page refresh. */
export const diffScopeAtomFamily = atomFamily((_workspaceId: string) => atom<DiffScope>("uncommitted"));

/** Ratio (0–100) controlling the left/right column split in side-by-side diffs. */
export const splitDiffColumnRatioAtom = atom(50);

const DEFAULT_DIFF_PANEL_TAB_STATE: DiffPanelTabState = {
  activeTab: null,
};

/**
 * The active diff/file-view tab — inherently per-workspace since each workspace
 * has its own set of files. Only the active tab is stored (there is no tab bar),
 * so the persisted state stays bounded.
 */
export const diffPanelStateAtomFamily = atomFamily((workspaceId: string) =>
  atomWithStorage<DiffPanelTabState>(`diffPanel-state-${workspaceId}`, DEFAULT_DIFF_PANEL_TAB_STATE),
);

/**
 * The active diff tab for a workspace, or null when no tab is active. Each host
 * panel (Files / Changes / Commits) reads this so an agent-opened file/diff —
 * which writes the tab via `setActiveDiffTabAtom` but never touches the panel's
 * local click state — still renders in the panel's single embedded DiffViewer.
 * Local tree clicks keep driving the panel directly; the panel reconciles the
 * two by most-recent-`viewedAt` (see the host panels).
 */
export const activeDiffTabAtomFamily = atomFamily((workspaceId: string) =>
  atom<DiffTab | null>((get) => {
    // `?? null` guards against persisted state written before `activeTab`
    // existed (older shapes stored a tab list instead).
    return get(diffPanelStateAtomFamily(workspaceId)).activeTab ?? null;
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
  return {
    kind: "file-view",
    filePath: tab.realPath,
    tabFilePath: tab.filePath,
    markdownMode: tab.markdownMode,
    // `viewedAt` rides along so a repeat quick-open of the same file (a new
    // timestamp, same paths) re-applies a render-mode request the user had
    // dismissed for the previous open.
    openedAt: tab.viewedAt,
  };
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

/** Global preference for how `.md` / `.markdown` files are shown in ReadOnlyPreview. */
export type MarkdownRenderMode = "raw" | "rendered";
export const markdownRenderModeAtom = atomWithStorage<MarkdownRenderMode>("diffPanel-markdownRenderMode", "rendered");

/** Cap for the viewer header's recently-viewed file dropdown. */
const MAX_RECENT_FILES = 10;

/** Which panel a viewer header belongs to — each keeps its own recents list. */
export type RecentFilesPanel = "files" | "changes" | "commits";

/**
 * A recently viewed file: the workspace-relative path, plus what is needed to
 * re-open the same view — the commit the view was scoped to for Commits-panel
 * entries, and the diff's status/scope for Changes-panel entries (without
 * these, a committed-only file viewed under the "All" scope would re-open as
 * a plain file view instead of its diff).
 */
export type RecentDiffFile = { path: string; commitHash?: string; status?: FileStatus; scope?: DiffScope };

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
export const getRecentDiffFilesAtom = (workspaceId: string, panel: RecentFilesPanel) =>
  recentDiffFilesByKeyAtomFamily(recentFilesKey(workspaceId, panel));

/** Move (or insert) a file to the front of a panel's recently-viewed list. */
export const recordRecentDiffFileAtom = atom(
  null,
  (
    get,
    set,
    { workspaceId, panel, entry }: { workspaceId: string; panel: RecentFilesPanel; entry: RecentDiffFile },
  ) => {
    const listAtom = getRecentDiffFilesAtom(workspaceId, panel);
    const prev = get(listAtom);
    // Entries are deduped by file identity (path + commit); a re-record of the
    // same file replaces it so the status/scope stay current.
    const isSameFile = (candidate: RecentDiffFile): boolean =>
      candidate.path === entry.path && candidate.commitHash === entry.commitHash;
    const front = prev[0];
    if (front !== undefined && isSameFile(front) && front.status === entry.status && front.scope === entry.scope) {
      return;
    }
    set(listAtom, [entry, ...prev.filter((candidate) => !isSameFile(candidate))].slice(0, MAX_RECENT_FILES));
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

type SetActiveFileView = {
  kind: "file-view";
  workspaceId: string;
  filePath: string;
  /** Set by the quick-open-rendered-markdown path; see {@link FileViewTab}. */
  markdownMode?: "rendered";
};

type SetActiveCommitDiff = {
  kind: "commit-diff";
  workspaceId: string;
  commitHash: string;
  filePath: string;
};

type SetActiveDiffPayload = SetActiveSingleDiff | SetActiveFileView | SetActiveCommitDiff;

/**
 * Build a DiffTab from a discriminated union payload. The tab's `filePath` is its
 * identity key (a scope prefix + the real path for prefixed kinds).
 */
const buildTabFromPayload = (payload: SetActiveDiffPayload, now: number): DiffTab => {
  switch (payload.kind) {
    case "single": {
      const tabPath =
        payload.scope === "vs-target-branch" ? TARGET_BRANCH_DIFF_PREFIX + payload.filePath : payload.filePath;
      return {
        kind: "single",
        filePath: tabPath,
        status: payload.status,
        scope: payload.scope,
        viewedAt: now,
        diffString: payload.diffString,
      };
    }
    case "file-view":
      return {
        kind: "file-view",
        filePath: FILE_VIEW_PREFIX + payload.filePath,
        realPath: payload.filePath,
        viewedAt: now,
        markdownMode: payload.markdownMode,
      };
    case "commit-diff":
      return {
        kind: "commit-diff",
        filePath: COMMIT_DIFF_PREFIX + payload.commitHash + ":" + payload.filePath,
        commitHash: payload.commitHash,
        realPath: payload.filePath,
        viewedAt: now,
      };
  }
};

/**
 * Unified atom that activates a diff tab of any kind (replacing whatever tab
 * was active before — only the active tab is kept).
 */
export const setActiveDiffTabAtom = atom(null, (get, set, payload: SetActiveDiffPayload) => {
  set(diffPanelStateAtomFamily(payload.workspaceId), { activeTab: buildTabFromPayload(payload, Date.now()) });

  // Reveal the host panel in the section shell: open + expand its section and
  // make it active so the embedded DiffViewer (DIFF_PANEL) becomes visible.
  //
  // The reveal is skipped in two cases (the tab is already recorded above either way,
  // so the viewer renders the right file once the host panel is visible):
  //
  // 1. A NON-ACTIVE workspace: open-file events arrive over the unified stream for
  //    ANY workspace, but `openPanelAtom`/`jumpToSectionAtom` write through the
  //    active-workspace layout proxy — revealing here would open/expand the host
  //    panel and pulse the ring in the workspace the user is currently VIEWING (and
  //    persist that layout change). The target workspace keeps its recorded tab and
  //    surfaces it on the next visit.
  //
  // 2. An UNSEEDED layout: the workspace-shell bootstrap seeds the default
  //    arrangement (Files/Changes/Commits in the left section, the agent in center, …)
  //    on a workspace's first visit, gated on `isEmptyLayout`. If an open-file event
  //    races that bootstrap (e.g. a buffered WebSocket OpenFileUiAction landing in the
  //    same tick as mount), opening a single host panel here would place it ALONE in the
  //    left section and flip `isEmptyLayout` to false, so the bootstrap would skip
  //    seeding and Files/Changes/Commits would never appear.
  const isActiveWorkspace = payload.workspaceId === get(activeWorkspaceIdAtom);
  const layout = get(workspaceLayoutFamily(payload.workspaceId));
  if (isActiveWorkspace && !isEmptyLayout(layout)) {
    const host = HOST_PANEL_BY_KIND[payload.kind];
    set(openPanelAtom, { panelId: host.panelId, in: host.section });
    set(jumpToSectionAtom, { subSection: host.section });
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

/**
 * Reset the active workspace's combined "Review All" scope to its default —
 * "All" (vs the target branch), the full branch review the surface is named for.
 * The add-panel open path fires this only when the Review All panel is NEWLY
 * placed, so a scope the user picked while the panel is open is never stomped;
 * merely re-activating or revealing the already-open panel keeps their choice.
 */
export const resetReviewAllScopeAtom = atom(null, (get, set) => {
  const workspaceId = get(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return;
  }
  set(diffScopeAtomFamily(workspaceId), "vs-target-branch");
});

/** Open (or activate) a read-only file view tab. */
export const openFileViewTabAtom = atom(
  null,
  (_get, set, params: { workspaceId: string; filePath: string; markdownMode?: "rendered" }) => {
    set(setActiveDiffTabAtom, { kind: "file-view", ...params });
  },
);

/** Open (or activate) a commit-scoped file diff tab. */
export const openCommitDiffTabAtom = atom(
  null,
  (_get, set, params: { workspaceId: string; commitHash: string; filePath: string }) => {
    set(setActiveDiffTabAtom, { kind: "commit-diff", ...params });
  },
);

/**
 * Close the tab identified by `filePath` (a no-op when it is not the active
 * tab). The host panel stays put so the user sees its empty placeholder
 * rather than the panel collapsing out from under them.
 */
export const closeDiffTabAtom = atom(
  null,
  (get, set, { workspaceId, filePath }: { workspaceId: string; filePath: string }) => {
    const stateAtom = diffPanelStateAtomFamily(workspaceId);
    if (get(stateAtom).activeTab?.filePath !== filePath) {
      return;
    }
    set(stateAtom, { activeTab: null });
  },
);
