import type { DiffScope, DiffViewType } from "~/pages/workspace/components/diffPanel/types.ts";
import type { FileStatus, ViewMode } from "~/pages/workspace/panels/fileBrowser/types.ts";

/**
 * What a single embedded {@link DiffViewer} instance is currently showing. Each
 * of the Files / Changes / Commits panels owns its own selection and passes it
 * as a prop — there is no shared global "active diff" singleton. `null` means
 * nothing is selected and the viewer shows its empty state.
 */
export type DiffSelection =
  | {
      /** A file's diff against the workspace's uncommitted / target-branch changes. */
      kind: "diff";
      filePath: string;
      status: FileStatus;
      /** Which diff to display. Defaults to "uncommitted". */
      scope?: DiffScope;
      /** Tool-specific diff string when opened from a chip popover. When absent,
       *  the workspace diff is used (preserves open-from-chat behavior). */
      diffString?: string;
      /** Tab identifier (may carry a scope prefix); used for file-actions menu
       *  close operations. Defaults to `filePath`. */
      tabFilePath?: string;
    }
  | {
      /** A read-only view of the current file contents (no diff). */
      kind: "file-view";
      filePath: string;
      tabFilePath?: string;
    }
  | {
      /** A single file's diff within a specific commit. */
      kind: "commit-diff";
      commitHash: string;
      filePath: string;
      tabFilePath?: string;
    };

/**
 * The diff view controls that previously lived as toolbar icons above the
 * viewer. They now hang off the file header's triple-dot menu.
 */
export type DiffViewOptions = {
  viewType: DiffViewType;
  onToggleViewType: () => void;
  lineWrapping: "wrap" | "scroll";
  onToggleLineWrapping: () => void;
  onToggleSearch: () => void;
  showRenderToggle: boolean;
  isRendered: boolean;
  /** Off => the render item renders disabled with a hint, pointing at
   *  Settings → Experimental where the flag lives. */
  isRenderToggleEnabled: boolean;
  onToggleRender: () => void;
};

/**
 * The tree (list) view controls — flat/tree and collapse-all — merged into the
 * same triple-dot menu so there is a single options menu. Omitted by
 * panels (e.g. Commits) whose list has no such controls.
 */
export type TreeViewOptions = {
  /** Tree/flat toggle — omit to hide the item (e.g. Commits). */
  viewMode?: ViewMode;
  onToggleViewMode?: () => void;
  onCollapseAll: () => void;
  collapseLabel: string;
};
