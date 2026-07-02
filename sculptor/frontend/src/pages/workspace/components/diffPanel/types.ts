import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";

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

export type DiffTab = SingleFileDiffTab | FileViewTab | CommitFileDiffTab;

export type SplitPosition = "left" | "right";

/**
 * Per-workspace diff-panel state persisted to localStorage. Only the active
 * tab is stored: there is no tab bar to display a list, so keeping more than
 * the active tab would grow the persisted state with entries nothing reads.
 */
export type DiffPanelTabState = {
  activeTab: DiffTab | null;
};

export type DiffViewType = "unified" | "split";

export type DiffScope = "uncommitted" | "vs-target-branch";
