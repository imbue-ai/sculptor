import { Box, Flex, Text } from "@radix-ui/themes";
import { useAtom, useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds, UserConfigField } from "~/api";
import { useTimedLatch } from "~/common/Hooks.ts";
import { useKeybindingHandler } from "~/common/keybindings";
import {
  appThemeAtom,
  fileBrowserDiffViewTypeAtom,
  fileBrowserLineWrappingAtom,
  isRichMarkdownRenderingEnabledAtom,
} from "~/common/state/atoms/userConfig.ts";
import { useUserConfig } from "~/common/state/hooks/useUserConfig.ts";
import { useWorkspaceCommitDiff } from "~/common/state/hooks/useWorkspaceCommitDiff.ts";
import { getLineCounts, parseDiff } from "~/components/DiffUtils.ts";
import { IndeterminateProgress } from "~/components/IndeterminateProgress.tsx";
import { determineFileStatus } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import { isMarkdownPath, markdownRenderModeAtom } from "./atoms.ts";
import { BinaryPreview } from "./BinaryPreview.tsx";
import { CombinedDiffView } from "./CombinedDiffView.tsx";
import { DeletedFileBanner } from "./DeletedFileBanner.tsx";
import { DiffErrorBanner } from "./DiffErrorBanner.tsx";
import { DiffFileHeader, type DiffViewOptions } from "./DiffFileHeader.tsx";
import styles from "./DiffPanel.module.scss";
import { DiffSkeleton } from "./DiffSkeleton.tsx";
import { useActiveFileDiff } from "./hooks.ts";
import { InFileSearchBar } from "./InFileSearchBar.tsx";
import { LARGE_DIFF_LINE_THRESHOLD, LargeDiffGate } from "./LargeDiffGate.tsx";
import { PierreDiffView } from "./PierreDiffView.tsx";
import { ReadOnlyPreview } from "./ReadOnlyPreview.tsx";
import { RenameBanner } from "./RenameBanner.tsx";
import type { DiffViewType } from "./types.ts";
import { useFileLines } from "./useFileLines.ts";
import { useInFileSearch } from "./useInFileSearch.ts";
import { useScrollPreservation } from "./useScrollPreservation.ts";

type DiffPanelProps = {
  workspaceId: string;
  /**
   * The per-panel diff-state scope key (REQ-DIFF-1..3). Defaults to the
   * workspaceId (the Changes/default scope). Files and Commits pass distinct
   * keys so each panel tracks its own selected file.
   */
  stateKey?: string;
  /**
   * Compact single-file mode (REQ-DIFF-3): hide the multi-file tab/scope row and
   * the always-mounted combined view. Only one file is shown at a time, with a
   * minimal control row. Always true in the in-panel master-detail viewer.
   */
  singleFile?: boolean;
};

// Wait this long before showing the top progress bar; fetches that finish
// faster than this never flash it, which avoids flicker on quick diffs.
const PROGRESS_START_DELAY_MS = 120;
// Once shown, hold the progress bar visible long enough to register even when
// the underlying fetch returns in under a frame.
const PROGRESS_MIN_HOLD_MS = 500;

// Longest we wait for hunk-expansion file contents before rendering the diff
// without them (see the hold effect in DiffPanel).
const FILE_LINES_HOLD_MS = 1200;

const renderDiffContent = ({
  diffString,
  viewType,
  overflow,
  themeType,
  oldLines,
  newLines,
}: {
  diffString: string;
  viewType: DiffViewType;
  overflow: "wrap" | "scroll";
  themeType: "light" | "dark" | "system";
  oldLines?: Array<string>;
  newLines?: Array<string>;
}): ReactElement => {
  return (
    <LargeDiffGate diffString={diffString}>
      {(visibleDiff, isTruncated) => (
        <PierreDiffView
          diffString={visibleDiff}
          viewType={viewType}
          overflow={overflow}
          themeType={themeType}
          oldLines={isTruncated ? undefined : oldLines}
          newLines={isTruncated ? undefined : newLines}
        />
      )}
    </LargeDiffGate>
  );
};

export const DiffPanel = ({ workspaceId, stateKey, singleFile = false }: DiffPanelProps): ReactElement => {
  const activeFileDiff = useActiveFileDiff(workspaceId, stateKey);
  // Only surface the loading bar when a file is open: the bar means "the diff
  // you're looking at is loading," which is meaningless over the empty "Open a
  // file to view it" placeholder. `isFetching` alone is a workspace-level
  // signal that also fires for background/forced diff fetches while no file is
  // open, which used to flash the bar over the placeholder (SCU-1329).
  const isProgressVisible = useTimedLatch(
    activeFileDiff.isFetching && activeFileDiff.filePath !== null,
    PROGRESS_MIN_HOLD_MS,
    PROGRESS_START_DELAY_MS,
  );
  const viewType = useAtomValue(fileBrowserDiffViewTypeAtom);
  const overflow = useAtomValue(fileBrowserLineWrappingAtom);
  const appTheme = useAtomValue(appThemeAtom);
  // Expand mode is handled at the DockingLayout level; DiffPanel just renders normally.
  const { updateField } = useUserConfig();
  // Skip file line fetching for combined, file-view, and commit-diff tabs —
  // they don't need hunk expansion data.
  const shouldSkipFileLines = activeFileDiff.isCombined || activeFileDiff.isFileView || activeFileDiff.isCommitDiff;
  const { data: commitDiffString, isPending: isCommitDiffPending } = useWorkspaceCommitDiff(
    workspaceId,
    activeFileDiff.isCommitDiff ? activeFileDiff.commitHash : null,
  );

  // Extract the single file's diff, rename info, and status from the full commit diff.
  const { commitFileDiffString, commitFilePreviousPath, commitFileStatus } = useMemo(() => {
    if (!commitDiffString || !activeFileDiff.filePath)
      return { commitFileDiffString: null, commitFilePreviousPath: null, commitFileStatus: null };
    const parsed = parseDiff(commitDiffString);
    const fileChange = parsed.fileChanges.find((fc) => fc.fileNames.referenceFileName === activeFileDiff.filePath);
    if (!fileChange) return { commitFileDiffString: null, commitFilePreviousPath: null, commitFileStatus: null };
    const { previousFileName, newFileName } = fileChange.fileNames;
    const previousPath = previousFileName && previousFileName !== newFileName ? previousFileName : null;
    return {
      commitFileDiffString: fileChange.diffString,
      commitFilePreviousPath: previousPath,
      commitFileStatus: determineFileStatus(fileChange),
    };
  }, [commitDiffString, activeFileDiff.filePath]);

  const commitFileLineCounts = useMemo(
    () => (commitFileDiffString ? getLineCounts(commitFileDiffString) : { added: 0, removed: 0 }),
    [commitFileDiffString],
  );

  const {
    oldLines,
    newLines,
    isLoading: areFileLinesLoading,
  } = useFileLines(
    workspaceId,
    shouldSkipFileLines ? null : activeFileDiff.filePath,
    shouldSkipFileLines ? null : activeFileDiff.previousFilePath,
    shouldSkipFileLines ? null : activeFileDiff.status,
    shouldSkipFileLines ? null : activeFileDiff.diffString,
    // The vs-target-branch diff is computed against merge-base(target, HEAD), so
    // its old-side line numbers reference the merge-base — fetch oldLines from
    // that exact commit, not the target-branch tip (which may have diverged and
    // be shorter, causing a Pierre renderHunks crash).  Fall back to undefined
    // (→ getBaseRef → target branch) only when the merge-base is unknown.  The
    // uncommitted scope diffs against HEAD, so oldLines come from HEAD.
    activeFileDiff.isTargetBranchDiff ? (activeFileDiff.targetBranchMergeBase ?? undefined) : "HEAD",
  );
  // Hold the diff briefly while its expansion data (full file contents) is
  // loading, so it paints once, fully formed — without the hold it paints
  // immediately without expansion data and then fully re-renders (a new diff
  // web component) when the contents land. After the timeout, render without
  // expansion rather than blocking on a slow fetch. With the workspace
  // prefetch warming changed files' contents, the hold rarely engages.
  const [hasFileLinesHoldExpired, setHasFileLinesHoldExpired] = useState(false);
  useEffect(() => {
    setHasFileLinesHoldExpired(false);
    if (!areFileLinesLoading) return;
    const timeout = setTimeout(() => setHasFileLinesHoldExpired(true), FILE_LINES_HOLD_MS);
    return (): void => clearTimeout(timeout);
  }, [areFileLinesLoading, activeFileDiff.filePath]);

  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocusRequest, setSearchFocusRequest] = useState(0);
  const diffContentRef = useRef<HTMLDivElement>(null);
  const combinedContentRef = useRef<HTMLDivElement>(null);

  const { currentMatch, totalMatches, goToNextMatch, goToPrevMatch, clearHighlights } = useInFileSearch({
    diffContentRef: activeFileDiff.isCombined ? combinedContentRef : diffContentRef,
    query: searchQuery,
    isActive: isSearchOpen,
    activeFilePath: activeFileDiff.filePath,
  });

  useScrollPreservation({
    containerRef: diffContentRef,
    diffString: activeFileDiff.diffString,
    filePath: activeFileDiff.filePath,
  });

  const handleToggleViewType = useCallback((): void => {
    const newViewType = viewType === "unified" ? "split" : "unified";
    updateField(UserConfigField.FILE_BROWSER_DIFF_VIEW_TYPE, newViewType);
  }, [viewType, updateField]);

  const handleToggleLineWrapping = useCallback((): void => {
    const newOverflow = overflow === "wrap" ? "scroll" : "wrap";
    updateField(UserConfigField.FILE_BROWSER_LINE_WRAPPING, newOverflow);
  }, [overflow, updateField]);

  const [markdownMode, setMarkdownMode] = useAtom(markdownRenderModeAtom);
  const isRichMarkdownRenderingEnabled = useAtomValue(isRichMarkdownRenderingEnabledAtom);

  // ReadOnlyPreview is the only path that supports rendered markdown — used
  // for file-view tabs and "no diff" states. Hide the toggle elsewhere. Even
  // when visible, the toggle is shown disabled (with a hint tooltip) until the
  // experimental `enable_rich_markdown_rendering` flag is enabled.
  const isMarkdownToggleVisible = useMemo((): boolean => {
    const fp = activeFileDiff.filePath;
    if (!fp || !isMarkdownPath(fp)) return false;
    if (activeFileDiff.isBinary || activeFileDiff.errorMessage) return false;
    if (activeFileDiff.isCombined || activeFileDiff.isCommitDiff) return false;
    if (activeFileDiff.isFileView) return true;
    return !activeFileDiff.diffString;
  }, [
    activeFileDiff.filePath,
    activeFileDiff.isBinary,
    activeFileDiff.errorMessage,
    activeFileDiff.isCombined,
    activeFileDiff.isCommitDiff,
    activeFileDiff.isFileView,
    activeFileDiff.diffString,
  ]);

  const handleToggleSearch = useCallback((): void => {
    setIsSearchOpen((prev) => {
      if (prev) {
        clearHighlights();
      }
      return !prev;
    });
  }, [clearHighlights]);

  const handleCloseSearch = useCallback((): void => {
    setIsSearchOpen(false);
    clearHighlights();
  }, [clearHighlights]);

  const handleToggleMarkdownRender = useCallback((): void => {
    setMarkdownMode((m) => {
      const next = m === "rendered" ? "raw" : "rendered";
      // Find-in-file is hidden in rendered mode; close it on the way in so
      // the search bar doesn't get stuck open with no button to dismiss it.
      if (next === "rendered") handleCloseSearch();
      return next;
    });
  }, [setMarkdownMode, handleCloseSearch]);

  // Find-in-file walks source-view DOM; rendered markdown has none. Treat the
  // button visibility and the Cmd+F keybinding consistently. The rendered
  // path only mounts when the experimental flag is on, so the persisted
  // "rendered" preference doesn't suppress find-in-file when the flag is off.
  const isRenderedMarkdownActive =
    isMarkdownToggleVisible && markdownMode === "rendered" && isRichMarkdownRenderingEnabled;

  useKeybindingHandler("find_in_file", () => {
    if (!activeFileDiff.filePath || isRenderedMarkdownActive) return;
    setIsSearchOpen(true);
    setSearchFocusRequest((n) => n + 1);
  });

  // The file's view controls — moved out of the old toolbar into the header "…"
  // menu (REQ-DIFF polish).
  const viewOptions: DiffViewOptions = {
    viewType,
    onToggleViewType: handleToggleViewType,
    lineWrapping: overflow,
    onToggleLineWrapping: handleToggleLineWrapping,
    onToggleSearch: handleToggleSearch,
    showRenderToggle: isMarkdownToggleVisible,
    isRendered: markdownMode === "rendered" && isRichMarkdownRenderingEnabled,
    isRenderToggleEnabled: isRichMarkdownRenderingEnabled,
    onToggleRender: handleToggleMarkdownRender,
  };

  const renderContent = (): ReactElement => {
    const { filePath, errorMessage, isBinary, status, diffString, previousFilePath } = activeFileDiff;

    if (!filePath) {
      return (
        <Flex align="center" justify="center" flexGrow="1">
          <Text size="2" color="gray">
            Open a file to view it
          </Text>
        </Flex>
      );
    }

    // Error takes priority
    if (errorMessage) {
      return <DiffErrorBanner errorMessage={errorMessage} />;
    }

    // Binary files
    if (isBinary) {
      return (
        <BinaryPreview
          workspaceId={workspaceId}
          filePath={filePath}
          fileStatus={status}
          previousFilePath={previousFilePath}
        />
      );
    }

    // Read-only preview for files with no diff
    if (!diffString) {
      return <ReadOnlyPreview workspaceId={workspaceId} filePath={filePath} />;
    }

    // Hold for the expansion data unless the diff is large enough that the
    // LargeDiffGate truncates it (truncated diffs don't use the line arrays).
    const isWithinExpansionThreshold = diffString.split("\n").length <= LARGE_DIFF_LINE_THRESHOLD;
    if (areFileLinesLoading && !hasFileLinesHoldExpired && isWithinExpansionThreshold) {
      return <DiffSkeleton />;
    }

    // Added or deleted files have only one side, so a side-by-side split is meaningless.
    const effectiveViewType = status === "A" || status === "D" ? "unified" : viewType;
    const diffProps = { diffString, viewType: effectiveViewType, overflow, themeType: appTheme, oldLines, newLines };

    // Deleted files: banner + deletion diff
    if (status === "D") {
      return (
        <>
          <DeletedFileBanner workspaceId={workspaceId} filePath={filePath} />
          {renderDiffContent(diffProps)}
        </>
      );
    }

    // Renamed files: banner + diff (may be empty diff if rename-only)
    if (status === "R" && previousFilePath) {
      return (
        <>
          <RenameBanner oldPath={previousFilePath} newPath={filePath} />
          {renderDiffContent(diffProps)}
        </>
      );
    }

    // Normal diff
    return renderDiffContent(diffProps);
  };

  return (
    <Flex direction="column" height="100%" position="relative" data-testid={ElementIds.DIFF_PANEL}>
      {isProgressVisible && (
        <Box position="absolute" top="0" left="0" right="0" className={styles.progressOverlay}>
          <IndeterminateProgress size="1" />
        </Box>
      )}
      {isSearchOpen && (
        <InFileSearchBar
          query={searchQuery}
          onQueryChange={setSearchQuery}
          currentMatch={currentMatch}
          totalMatches={totalMatches}
          onNextMatch={goToNextMatch}
          onPrevMatch={goToPrevMatch}
          onClose={handleCloseSearch}
          focusRequest={searchFocusRequest}
        />
      )}

      {/* Always mounted so the toolbar DOM is ready before the tab activates.
          Skipped in single-file mode — Review All is its own panel now. */}
      {!singleFile && (
        <CombinedDiffView
          workspaceId={workspaceId}
          viewType={viewType}
          isActive={activeFileDiff.isCombined}
          contentRef={combinedContentRef}
          searchQuery={isSearchOpen ? searchQuery : ""}
        />
      )}

      {!activeFileDiff.isCombined &&
        (activeFileDiff.isFileView ? (
          <>
            <DiffFileHeader
              workspaceId={workspaceId}
              filePath={activeFileDiff.filePath!}
              tabFilePath={activeFileDiff.tabFilePath ?? undefined}
              addedLines={0}
              removedLines={0}
              fileStatus={null}
              isBinary={false}
              viewOptions={viewOptions}
            />
            <Flex ref={diffContentRef} direction="column" flexGrow="1" overflow="hidden" className={styles.content}>
              <ReadOnlyPreview workspaceId={workspaceId} filePath={activeFileDiff.filePath!} />
            </Flex>
          </>
        ) : activeFileDiff.isCommitDiff && activeFileDiff.filePath ? (
          <>
            <DiffFileHeader
              workspaceId={workspaceId}
              filePath={activeFileDiff.filePath}
              tabFilePath={activeFileDiff.tabFilePath ?? undefined}
              addedLines={commitFileLineCounts.added}
              removedLines={commitFileLineCounts.removed}
              fileStatus={null}
              isBinary={false}
              viewOptions={viewOptions}
            />
            <Flex ref={diffContentRef} direction="column" flexGrow="1" overflow="hidden" className={styles.content}>
              {isCommitDiffPending ? (
                <Flex align="center" justify="center" flexGrow="1">
                  <Text size="2" color="gray">
                    Loading commit diff…
                  </Text>
                </Flex>
              ) : commitFileDiffString ? (
                <>
                  {commitFilePreviousPath && (
                    <RenameBanner oldPath={commitFilePreviousPath} newPath={activeFileDiff.filePath} />
                  )}
                  {renderDiffContent({
                    diffString: commitFileDiffString,
                    // Added or deleted files have only one side, so a side-by-side split is meaningless.
                    viewType: commitFileStatus === "A" || commitFileStatus === "D" ? "unified" : viewType,
                    overflow,
                    themeType: appTheme,
                  })}
                </>
              ) : (
                <Flex align="center" justify="center" flexGrow="1">
                  <Text size="2" color="gray">
                    No diff available
                  </Text>
                </Flex>
              )}
            </Flex>
          </>
        ) : activeFileDiff.filePath ? (
          <>
            <DiffFileHeader
              workspaceId={workspaceId}
              filePath={activeFileDiff.filePath}
              tabFilePath={activeFileDiff.tabFilePath ?? undefined}
              addedLines={activeFileDiff.addedLines}
              removedLines={activeFileDiff.removedLines}
              fileStatus={activeFileDiff.status}
              isBinary={activeFileDiff.isBinary}
              viewOptions={viewOptions}
            />
            <Flex ref={diffContentRef} direction="column" flexGrow="1" overflow="hidden" className={styles.content}>
              {renderContent()}
            </Flex>
          </>
        ) : (
          renderContent()
        ))}
    </Flex>
  );
};
