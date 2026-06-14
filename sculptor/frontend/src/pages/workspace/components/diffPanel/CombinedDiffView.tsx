import { Flex, IconButton, Text } from "@radix-ui/themes";
import { useAtom, useAtomValue } from "jotai";
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown, ChevronUp, Ellipsis } from "lucide-react";
import type { ReactElement, RefObject } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { appThemeAtom, fileBrowserLineWrappingAtom } from "~/common/state/atoms/userConfig.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import type { DiffData } from "~/components/DiffUtils.ts";
import { parseDiff } from "~/components/DiffUtils.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { CommitButton } from "~/pages/workspace/panels/fileBrowser/CommitButton.tsx";
import { FileDropdownMenu } from "~/pages/workspace/panels/fileBrowser/FileDropdownMenu.tsx";
import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { determineFileStatus, isBinaryFile } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import { diffScopeAtomFamily } from "./atoms.ts";
import styles from "./CombinedDiffView.module.scss";
import { DiffScopePicker } from "./DiffScopePicker.tsx";
import { LargeDiffGate } from "./LargeDiffGate.tsx";
import { PierreDiffView } from "./PierreDiffView.tsx";
import type { DiffScope, DiffViewType } from "./types.ts";
import { useFileLines } from "./useFileLines.ts";

type FileChangeEntry = DiffData["fileChanges"][number];

/** A single file section in the combined diff view (header + expandable diff body). */
const FileSection = ({
  fc,
  workspaceId,
  isCollapsed,
  viewType,
  overflow,
  themeType,
  scope,
  mergeBaseRef,
  onToggleCollapse,
}: {
  fc: FileChangeEntry;
  workspaceId: string;
  isCollapsed: boolean;
  viewType: DiffViewType;
  overflow: "wrap" | "scroll";
  themeType: "light" | "dark" | "system";
  scope: DiffScope;
  /** Commit SHA of merge-base(target, HEAD) for the vs-target-branch scope. */
  mergeBaseRef?: string;
  onToggleCollapse: (filePath: string) => void;
}): ReactElement => {
  const filePath = fc.fileNames.referenceFileName;
  const fileName = filePath.split("/").pop() ?? filePath;
  const fileStatus = determineFileStatus(fc);

  return (
    <div className={`${styles.fileSection} ${isCollapsed ? styles.fileSectionCollapsed : ""}`}>
      <div
        className={styles.fileSectionHeader}
        data-testid={ElementIds.COMBINED_DIFF_FILE_SECTION}
        data-filepath={filePath}
        onClick={() => onToggleCollapse(filePath)}
      >
        <ChevronRight size={14} className={`${styles.chevron} ${isCollapsed ? "" : styles.chevronExpanded}`} />
        <span className={`${styles.filePath} ${fileStatus === "D" ? styles.filePathDeleted : ""}`}>
          {filePath.includes("/") && (
            <span className={styles.filePathDir}>{filePath.slice(0, filePath.lastIndexOf("/"))}/</span>
          )}
          <span className={styles.filePathName}>{fileName}</span>
        </span>
        <span className={styles.spacer} />
        <span className={styles.lineStats}>
          <span className={styles.lineStatsAdded}>+{fc.changes.added}</span>
          <span className={styles.lineStatsRemoved}>-{fc.changes.removed}</span>
        </span>
        {/* Stop pointer/click events so the dropdown doesn't toggle collapse. */}
        <span
          className={styles.menuTriggerWrapper}
          onClick={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <FileDropdownMenu
            context={{
              filePath,
              isFolder: false,
              fileStatus,
              isBinary: isBinaryFile(fileName),
              source: "combined-diff-header",
            }}
            workspaceId={workspaceId}
          >
            <IconButton size="1" variant="ghost" color="gray" className={styles.menuTrigger}>
              <Ellipsis size={14} />
            </IconButton>
          </FileDropdownMenu>
        </span>
      </div>
      {!isCollapsed && fc.diffString && (
        <ExpandableFileDiff
          workspaceId={workspaceId}
          diffString={fc.diffString}
          filePath={filePath}
          previousFilePath={fc.fileNames.previousFileName !== filePath ? fc.fileNames.previousFileName : null}
          fileStatus={fileStatus}
          viewType={fileStatus === "A" || fileStatus === "D" ? "unified" : viewType}
          overflow={overflow}
          themeType={themeType}
          scope={scope}
          mergeBaseRef={mergeBaseRef}
          className={styles.embeddedDiff}
        />
      )}
    </div>
  );
};

/** When there are many files, default to all collapsed for performance. */
const AUTO_COLLAPSE_THRESHOLD = 5;

/** Wraps a single file's diff so we can call useFileLines per file. */
const ExpandableFileDiff = ({
  workspaceId,
  diffString,
  filePath,
  previousFilePath,
  fileStatus,
  viewType,
  overflow,
  themeType,
  scope,
  mergeBaseRef,
  className,
}: {
  workspaceId: string;
  diffString: string;
  filePath: string;
  previousFilePath: string | null;
  fileStatus: FileStatus;
  viewType: DiffViewType;
  overflow: "wrap" | "scroll";
  themeType: "light" | "dark" | "system";
  scope: DiffScope;
  /** Commit SHA of merge-base(target, HEAD) for the vs-target-branch scope. */
  mergeBaseRef?: string;
  className?: string;
}): ReactElement => {
  // The active diff has two possible base refs depending on the scope picker:
  //   - "uncommitted"      → HEAD..workdir, so oldLines must come from HEAD
  //   - "vs-target-branch" → merge-base(target, HEAD)..workdir, so oldLines must
  //     come from the merge-base commit — NOT the target-branch tip, which may
  //     have diverged since the merge-base and be shorter.
  // A mismatch between the diff's old-side line numbers and the fetched
  // oldLines causes Pierre's renderHunks to crash (and Shiki "Invalid
  // decoration position" errors).  Mirrors the per-scope handling in the
  // single-file DiffPanel view.  Falls back to the target branch (undefined →
  // getBaseRef) only when the merge-base is unknown.
  const baseRefOverride = scope === "vs-target-branch" ? mergeBaseRef : "HEAD";
  const { oldLines, newLines } = useFileLines(
    workspaceId,
    filePath,
    previousFilePath,
    fileStatus,
    diffString,
    baseRefOverride,
  );
  return (
    <LargeDiffGate diffString={diffString}>
      {(visibleDiff, isTruncated) => (
        <PierreDiffView
          diffString={visibleDiff}
          viewType={viewType}
          overflow={overflow}
          themeType={themeType}
          className={className}
          oldLines={isTruncated ? undefined : oldLines}
          newLines={isTruncated ? undefined : newLines}
          hideHandle
        />
      )}
    </LargeDiffGate>
  );
};

type CombinedDiffViewProps = {
  workspaceId: string;
  viewType: DiffViewType;
  /** When false the component stays mounted but hidden via CSS, keeping the toolbar DOM ready. */
  isActive: boolean;
  /** Optional ref exposed to the parent for features like in-file search. */
  contentRef?: RefObject<HTMLDivElement>;
  /** Active search query — collapsed files matching this query are auto-expanded. */
  searchQuery?: string;
  /** Called after the commit button sends its message. */
  onCommit?: () => void;
  /**
   * Override the code theme (Shiki syntax + diff surface) instead of following
   * the global app appearance. The mobile shell forces "light" so the diff body
   * matches its light "sand" surface — its scoped CSS-var theme re-colors the
   * surface, but Pierre's Shiki syntax colors come from a JS atom keyed off the
   * global appearance, which would otherwise stay dark. Desktop omits this.
   */
  forceThemeType?: "light" | "dark";
};

export const CombinedDiffView = ({
  workspaceId,
  viewType,
  isActive,
  contentRef,
  searchQuery = "",
  onCommit,
  forceThemeType,
}: CombinedDiffViewProps): ReactElement => {
  const workspace = useWorkspace(workspaceId);
  const hasTargetBranch = workspace?.targetBranch != null;
  const { data: diff } = useWorkspaceDiff(workspaceId);
  const [scope, setScope] = useAtom(diffScopeAtomFamily(workspaceId));
  const overflow = useAtomValue(fileBrowserLineWrappingAtom);
  const appTheme = useAtomValue(appThemeAtom);
  const effectiveThemeType = forceThemeType ?? appTheme;
  const containerRef = useRef<HTMLDivElement>(null);

  const activeDiffString = scope === "vs-target-branch" ? diff?.targetBranchDiff : diff?.uncommittedDiff;
  // Old-side content ref for the vs-target-branch scope: the merge-base commit
  // the targetBranchDiff was computed against.  Empty when unavailable, in which
  // case ExpandableFileDiff falls back to the target branch tip.
  const mergeBaseRef = diff?.targetBranchMergeBase || undefined;

  const fileChanges = useMemo(() => {
    if (!activeDiffString) return [];
    const parsed = parseDiff(activeDiffString);
    return parsed.fileChanges;
  }, [activeDiffString]);

  // Toolbar buttons are disabled until file data is available.
  const isReady = fileChanges.length > 0;

  const [collapsedFiles, setCollapsedFiles] = useState<Set<string>>(new Set());

  // During-render state adjustment: auto-collapse when file count changes and
  // exceeds the threshold. This avoids the stale intermediate render that the
  // useEffect approach would show.
  const [prevFileCount, setPrevFileCount] = useState(0);
  if (fileChanges.length !== prevFileCount) {
    setPrevFileCount(fileChanges.length);
    if (fileChanges.length > AUTO_COLLAPSE_THRESHOLD) {
      setCollapsedFiles(new Set(fileChanges.map((fc) => fc.fileNames.referenceFileName)));
    }
  }

  const toggleCollapse = useCallback((filePath: string): void => {
    setCollapsedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(filePath)) {
        next.delete(filePath);
      } else {
        next.add(filePath);
      }
      return next;
    });
  }, []);

  // Auto-expand collapsed files whose diff content matches the search query.
  useEffect(() => {
    if (!searchQuery) return;
    const lowerQuery = searchQuery.toLowerCase();
    const matchingPaths = new Set(
      fileChanges
        .filter((fc) => fc.diffString.toLowerCase().includes(lowerQuery))
        .map((fc) => fc.fileNames.referenceFileName),
    );
    if (matchingPaths.size === 0) return;

    setCollapsedFiles((prev) => {
      let hasChanges = false;
      const next = new Set(prev);
      for (const path of matchingPaths) {
        if (next.has(path)) {
          next.delete(path);
          hasChanges = true;
        }
      }
      return hasChanges ? next : prev;
    });
  }, [searchQuery, fileChanges]);

  /** Index of the file we last navigated to (or 0 for the first file). */
  const navigatedIndexRef = useRef(0);

  const handleNavigate = useCallback((direction: "up" | "down"): void => {
    const container = containerRef.current;
    if (!container) return;

    const headers = container.querySelectorAll<HTMLElement>("[data-filepath]");
    if (headers.length === 0) return;

    const targetIndex =
      direction === "down"
        ? Math.min(navigatedIndexRef.current + 1, headers.length - 1)
        : Math.max(navigatedIndexRef.current - 1, 0);

    if (targetIndex === navigatedIndexRef.current) return;

    navigatedIndexRef.current = targetIndex;
    headers[targetIndex].scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const areAllCollapsed = collapsedFiles.size === fileChanges.length && fileChanges.length > 0;

  const handleToggleCollapseAll = useCallback((): void => {
    if (areAllCollapsed) {
      setCollapsedFiles(new Set());
    } else {
      setCollapsedFiles(new Set(fileChanges.map((fc) => fc.fileNames.referenceFileName)));
    }
  }, [areAllCollapsed, fileChanges]);

  return (
    <div ref={contentRef} className={isActive ? styles.wrapper : styles.wrapperHidden}>
      <div className={styles.toolbar}>
        <TooltipIconButton
          tooltipText="Previous file"
          size="1"
          onClick={() => handleNavigate("up")}
          disabled={!isReady || fileChanges.length <= 1}
        >
          <ChevronUp size={14} />
        </TooltipIconButton>
        <TooltipIconButton
          tooltipText="Next file"
          size="1"
          onClick={() => handleNavigate("down")}
          disabled={!isReady || fileChanges.length <= 1}
        >
          <ChevronDown size={14} />
        </TooltipIconButton>
        <TooltipIconButton
          tooltipText={areAllCollapsed ? "Expand all files" : "Collapse all files"}
          size="1"
          onClick={handleToggleCollapseAll}
          disabled={!isReady}
        >
          {areAllCollapsed ? <ChevronsUpDown size={14} /> : <ChevronsDownUp size={14} />}
        </TooltipIconButton>
        <DiffScopePicker scope={scope} onScopeChange={setScope} hasTargetBranch={hasTargetBranch} />
        <span className={styles.toolbarSpacer} />
        {scope === "uncommitted" && (
          <CommitButton changesCount={isReady ? fileChanges.length : 0} onCommit={onCommit} />
        )}
      </div>
      {isActive &&
        (fileChanges.length === 0 ? (
          <Flex align="center" justify="center" flexGrow="1">
            <Text size="2" color="gray">
              {scope === "vs-target-branch" && !diff?.targetBranchDiff
                ? "No target branch diff available"
                : "No changes to review"}
            </Text>
          </Flex>
        ) : (
          <div className={styles.splitWrapper}>
            <div ref={containerRef} className={styles.container}>
              {fileChanges.map((fc) => (
                <FileSection
                  key={fc.fileNames.referenceFileName}
                  fc={fc}
                  workspaceId={workspaceId}
                  isCollapsed={collapsedFiles.has(fc.fileNames.referenceFileName)}
                  viewType={viewType}
                  overflow={overflow}
                  themeType={effectiveThemeType}
                  scope={scope}
                  mergeBaseRef={mergeBaseRef}
                  onToggleCollapse={toggleCollapse}
                />
              ))}
            </div>
          </div>
        ))}
    </div>
  );
};
