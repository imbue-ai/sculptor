import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";

export const COMBINED_REVIEW_PATH = "__combined_review__";
export const FILE_VIEW_PREFIX = "__file_view__:";
export const COMMIT_DIFF_PREFIX = "__commit_diff__:";
export const TARGET_BRANCH_DIFF_PREFIX = "__target_branch_diff__:";

export type SingleFileDiffTab = {
  kind: "single";
  filePath: string;
  status: FileStatus;
  /** Which diff to display. Defaults to "uncommitted" for backwards compat. */
  scope?: DiffScope;
  viewedAt: number;
  /** Tool-specific diff string when opened from a chip popover. When absent, the workspace diff is used. */
  diffString?: string;
};

export type CombinedDiffTab = {
  kind: "combined";
  filePath: typeof COMBINED_REVIEW_PATH;
  defaultScope?: DiffScope;
  viewedAt: number;
};

export type FileViewTab = {
  kind: "file-view";
  /** Prefixed path used as the tab identity key (`FILE_VIEW_PREFIX + realPath`). */
  filePath: string;
  /** Actual file path used for fetching content. */
  realPath: string;
  viewedAt: number;
};

export type CommitFileDiffTab = {
  kind: "commit-diff";
  /** Prefixed path used as the tab identity key (`COMMIT_DIFF_PREFIX + commitHash + ":" + realPath`). */
  filePath: string;
  commitHash: string;
  /** Actual file path within the commit. */
  realPath: string;
  viewedAt: number;
};

export type DiffTab = SingleFileDiffTab | CombinedDiffTab | FileViewTab | CommitFileDiffTab;

export const isCombinedTab = (tab: DiffTab): tab is CombinedDiffTab => tab.kind === "combined";

export const isFileViewTab = (tab: DiffTab): tab is FileViewTab => tab.kind === "file-view";

export const isCommitDiffTab = (tab: DiffTab): tab is CommitFileDiffTab => tab.kind === "commit-diff";

export type SplitPosition = "left" | "right";

/**
 * Per-workspace diff-panel state persisted to localStorage.
 *
 * The visibility flag (`diffPanelOpenAtom`) and split ratio
 * (`diffPanelSplitRatioAtom`) are intentionally *not* stored here.  They
 * live in global atoms so the diff panel behaves like other docked panels:
 * shared across workspaces by default, with optional per-workspace
 * persistence via the experimental "per-workspace panel layout" flag.
 *
 * Dock position is derived from `fileBrowserDockSideAtom` — the diff
 * viewer always snaps to the same side as the file browser panel.
 */
export type DiffPanelTabState = {
  openTabs: Array<DiffTab>;
  activeTabPath: string | null;
};

export type DiffViewType = "unified" | "split";

export type DiffScope = "uncommitted" | "vs-target-branch";
