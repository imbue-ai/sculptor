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
  /** When set, this open explicitly requested rendered markdown (the viewer
   *  header's quick-open icon). The viewer honors it for THIS open only —
   *  without rewriting the user's global render-mode preference — until the
   *  user toggles the mode. */
  markdownMode?: "rendered";
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

/**
 * Which pane a spotlight was captured from. Drives both the diff side semantics
 * and the shape of the agent-facing system-reminder (a file-view spotlight has
 * no diff context; a commit-diff spotlight carries a `git show <hash>` hint).
 */
export type SpotlightScope = "file-view" | "uncommitted-diff" | "target-branch-diff" | "commit-diff";

/**
 * A line-level reference the user "spotlights" on a diff or file pane. It is a
 * pure pointer + a snapshot of what was there at capture time — any prose the
 * user types around the resulting chip is just their prompt, not owned by the
 * spotlight. One schema, two consumers: the front-end renders the chip from it,
 * and the send path expands it into a `<system-reminder>` for the agent.
 */
export type SpotlightData = {
  /** Repo-relative file path. */
  file: string;
  /** First selected line (1-based). */
  lineStart: number;
  /** Last selected line (equals `lineStart` for a single-line spotlight). */
  lineEnd: number;
  /** Diff side; `null` for a plain file view (no old/new distinction). */
  side: "old" | "new" | null;
  /** Literal line content captured at click time — the anchor-drift defense. */
  snippet: string;
  /** ISO 8601 timestamp of the capture moment. */
  snippetCapturedAt: string;
  /** Which pane the capture came from. */
  scope: SpotlightScope;
  /** Commit hash — set only when `scope === "commit-diff"`. */
  commitRef?: string;
};
