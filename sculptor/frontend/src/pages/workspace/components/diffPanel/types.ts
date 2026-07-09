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
  /** When set, this open explicitly requested a specific markdown render mode
   *  (`"rendered"` from the viewer's quick-open icon; `"raw"` from a spotlight
   *  line-reference click, which wants the source view so line numbers line up).
   *  The viewer honors it for THIS open only — without rewriting the user's
   *  global render-mode preference — until the user toggles the mode. */
  markdownMode?: "rendered" | "raw";
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
 * A spotlight splits into a navigational half (`SpotlightAnchor` — WHERE it
 * points) and an evidentiary half (the snapshot — WHAT-WAS-THERE at capture).
 * See the representational theory in the goal file for the full rationale.
 */

/** An inclusive run of line numbers within one version of a file. */
export type LineRange = { firstLine: number; lastLine: number };

/**
 * Where a spotlight was captured, and thus where clicking it navigates back to.
 * A discriminated union so the commit hash exists exactly when — and only when —
 * the origin is a commit diff; an impossible pairing is unconstructable.
 */
export type SpotlightScope =
  | { kind: "file-view" }
  | { kind: "uncommitted-diff" }
  | { kind: "target-branch-diff" }
  | { kind: "commit-diff"; commitHash: string };

/** The bare `kind` discriminant, handy for serialization and switch dispatch. */
export type SpotlightScopeKind = SpotlightScope["kind"];

/**
 * A line-level anchor into a file — the navigational half of a spotlight,
 * re-resolved against the live DOM to highlight and scroll.
 *
 * A diff line lives in up to two coordinate systems: a *modified* line is a red
 * row (previous file) and a green row (current file) whose numbers diverge with
 * any net insert/delete above them. Carrying BOTH ranges is non-lossy; the
 * old/new/changed label is a pure derivation of which are present.
 */
export type SpotlightAnchor = {
  file: string;
  /** Red rows the selection covered — deletions + change-deletions. `null` when none. */
  previousFileLines: LineRange | null;
  /** Green rows — additions + change-additions — AND the sole range for a plain file view. `null` when none. */
  currentFileLines: LineRange | null;
  scope: SpotlightScope;
};

/**
 * A line-level reference the user "spotlights" — the anchor plus a frozen
 * snapshot of what was there at capture time (the drift witness) and the git
 * world-state at that moment (for the agent). Any prose around the resulting
 * chip is just the user's prompt, not owned by the spotlight. One schema, two
 * consumers: the front-end renders the chip; the backend expands it into a
 * `<system-reminder>` for the agent.
 */
export type SpotlightData = SpotlightAnchor & {
  /** Old-file reading of the selected lines (deletions + shared context). */
  previousSnippet: string;
  /** New-file reading of the selected lines (additions + shared context) — and the sole text captured in a file view. */
  currentSnippet: string;
  /** ISO 8601 timestamp of the capture moment. */
  snippetCapturedAt: string;
  /** Branch checked out at capture — the agent's world-snapshot. */
  capturedBranch: string;
  /** HEAD commit at capture — the agent's world-snapshot. */
  capturedHeadCommit: string;
};

/** old|new|changed for the chip label; `null` for a plain file view (no diff axis). */
export type SpotlightVersionLabel = "old" | "new" | "changed";

/**
 * Derive the chip's parenthetical from which ranges are present:
 * previous-only → old; current-only → new; both → changed; neither → null.
 * Never stored, so it can't drift from the ranges.
 */
export const spotlightVersionLabel = (anchor: SpotlightAnchor): SpotlightVersionLabel | null => {
  const hasPrevious = anchor.previousFileLines !== null;
  const hasCurrent = anchor.currentFileLines !== null;
  if (hasPrevious && hasCurrent) return "changed";
  if (hasCurrent) return "new";
  if (hasPrevious) return "old";
  return null;
};

/**
 * The range that drives the chip's displayed number and its click-to-scroll
 * target. The CURRENT file is the source of truth — that's where the line lives
 * now and where the agent edits — falling back to the previous file only for a
 * pure deletion. For a commit spotlight, "current" means the file as of that
 * commit. (This is the deliberate current-file-is-truth trade-off.)
 */
export const spotlightPrimaryRange = (anchor: SpotlightAnchor): LineRange | null =>
  anchor.currentFileLines ?? anchor.previousFileLines;

/**
 * Rebuild a line range from serialized start/end strings (the `data-spotlight-*`
 * round-trip). Absent/empty start → `null` range; a missing end defaults to the
 * start (single line).
 */
export const lineRangeFromStrings = (
  start: string | null | undefined,
  end: string | null | undefined,
): LineRange | null => {
  if (start === null || start === undefined || start === "") return null;
  const firstLine = parseInt(start, 10);
  if (Number.isNaN(firstLine)) return null;
  const parsedEnd = end !== null && end !== undefined && end !== "" ? parseInt(end, 10) : firstLine;
  return { firstLine, lastLine: Number.isNaN(parsedEnd) ? firstLine : parsedEnd };
};

/**
 * Rebuild a scope union from serialized strings — the single parse boundary
 * where untrusted attributes become a `SpotlightScope`. A `commit-diff` kind
 * arriving with no hash (corrupt / hand-edited message) coerces to `file-view`
 * (best-effort: still shows file + line) rather than fabricating a hash.
 */
export const spotlightScopeFromStrings = (
  kind: string | null | undefined,
  commitHash: string | null | undefined,
): SpotlightScope => {
  if (kind === "commit-diff") {
    if (commitHash) return { kind: "commit-diff", commitHash };
    console.warn("spotlight chip claimed a commit but carried no hash; degrading to file view");
    return { kind: "file-view" };
  }
  if (kind === "uncommitted-diff") return { kind: "uncommitted-diff" };
  if (kind === "target-branch-diff") return { kind: "target-branch-diff" };
  return { kind: "file-view" };
};
