import { Box, Flex, Text } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useRef, useState } from "react";

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
import {
  isMarkdownPath,
  markdownRenderModeAtom,
  openFileViewTabAtom,
} from "~/pages/workspace/components/diffPanel/atoms.ts";
import { BinaryPreview } from "~/pages/workspace/components/diffPanel/BinaryPreview.tsx";
import { DeletedFileBanner } from "~/pages/workspace/components/diffPanel/DeletedFileBanner.tsx";
import { DiffErrorBanner } from "~/pages/workspace/components/diffPanel/DiffErrorBanner.tsx";
import { InFileSearchBar } from "~/pages/workspace/components/diffPanel/InFileSearchBar.tsx";
import { LargeDiffGate } from "~/pages/workspace/components/diffPanel/LargeDiffGate.tsx";
import { PierreDiffView } from "~/pages/workspace/components/diffPanel/PierreDiffView.tsx";
import { ReadOnlyPreview } from "~/pages/workspace/components/diffPanel/ReadOnlyPreview.tsx";
import { RenameBanner } from "~/pages/workspace/components/diffPanel/RenameBanner.tsx";
import type { DiffViewType } from "~/pages/workspace/components/diffPanel/types.ts";
import { useFileLines } from "~/pages/workspace/components/diffPanel/useFileLines.ts";
import { useInFileSearch } from "~/pages/workspace/components/diffPanel/useInFileSearch.ts";
import { useScrollPreservation } from "~/pages/workspace/components/diffPanel/useScrollPreservation.ts";
import { determineFileStatus } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import styles from "./DiffViewer.module.scss";
import { DiffViewerHeader } from "./DiffViewerHeader.tsx";
import { DiffViewerMenu } from "./DiffViewerMenu.tsx";
import type { RecentFilesScope } from "./FilePathSelect.tsx";
import type { DiffSelection, DiffViewOptions, TreeViewOptions } from "./types.ts";
import { useDiffViewerContent } from "./useDiffViewerContent.ts";

// Wait this long before showing the top progress bar; fetches that finish
// faster than this never flash it, which avoids flicker on quick diffs.
const PROGRESS_START_DELAY_MS = 120;
// Once shown, hold the progress bar visible long enough to register even when
// the underlying fetch returns in under a frame.
const PROGRESS_MIN_HOLD_MS = 500;

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
      {({ visibleDiff, isTruncated }) => (
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

type DiffViewerProps = {
  workspaceId: string;
  /** What this viewer instance currently shows. Owned by the embedding panel;
   *  `null` renders the empty state. There is no shared "active diff" singleton —
   *  each Files / Changes / Commits panel passes its own selection. */
  selection: DiffSelection | null;
  /** The list view controls merged into the triple-dot menu. */
  treeOptions?: TreeViewOptions;
  /** The sidebar-visibility toggle rendered before the breadcrumb. */
  sidebarToggle?: ReactElement;
  /** Extra header actions (e.g. refresh) rendered before the menu. */
  headerActions?: ReactElement;
};

/**
 * An embeddable single-file diff/file viewer. It resolves its
 * {@link DiffSelection} prop into content, preserves the in-panel viewer's
 * behavior (split/unified, wrap, find-in-file, render markdown, line numbers /
 * expansion, moved-file rendering, GFM + sanitization, loading bar only when a
 * file is open), and relocates every config toggle into the header's triple-dot
 * menu. It carries no multi-file tab bar, no combined "review all" view, and no
 * expand/fullscreen control.
 */
export const DiffViewer = ({
  workspaceId,
  selection,
  treeOptions,
  sidebarToggle,
  headerActions,
}: DiffViewerProps): ReactElement => {
  const content = useDiffViewerContent(workspaceId, selection);
  // Only surface the loading bar when a file is open: the bar means "the diff
  // you're looking at is loading," which is meaningless over the empty
  // placeholder. `isFetching` alone is a workspace-level signal that also fires
  // for background/forced diff fetches while no file is open.
  const isProgressVisible = useTimedLatch(
    content.isFetching && content.filePath !== null,
    PROGRESS_MIN_HOLD_MS,
    PROGRESS_START_DELAY_MS,
  );
  const viewType = useAtomValue(fileBrowserDiffViewTypeAtom);
  const overflow = useAtomValue(fileBrowserLineWrappingAtom);
  const appTheme = useAtomValue(appThemeAtom);
  const { updateField } = useUserConfig();

  // Skip file line fetching for file-view and commit-diff selections — they
  // don't need hunk expansion data.
  const shouldSkipFileLines = content.isFileView || content.isCommitDiff;
  const { data: commitDiffString, isPending: isCommitDiffPending } = useWorkspaceCommitDiff(
    workspaceId,
    content.isCommitDiff ? content.commitHash : null,
  );

  // Extract the single file's diff, rename info, and status from the full commit diff.
  const { commitFileDiffString, commitFilePreviousPath, commitFileStatus } = useMemo(() => {
    if (!commitDiffString || !content.filePath)
      return { commitFileDiffString: null, commitFilePreviousPath: null, commitFileStatus: null };
    const parsed = parseDiff(commitDiffString);
    const fileChange = parsed.fileChanges.find((fc) => fc.fileNames.referenceFileName === content.filePath);
    if (!fileChange) return { commitFileDiffString: null, commitFilePreviousPath: null, commitFileStatus: null };
    const { previousFileName, newFileName } = fileChange.fileNames;
    const previousPath = previousFileName && previousFileName !== newFileName ? previousFileName : null;
    return {
      commitFileDiffString: fileChange.diffString,
      commitFilePreviousPath: previousPath,
      commitFileStatus: determineFileStatus(fileChange),
    };
  }, [commitDiffString, content.filePath]);

  const commitFileLineCounts = useMemo(
    () => (commitFileDiffString ? getLineCounts(commitFileDiffString) : { added: 0, removed: 0 }),
    [commitFileDiffString],
  );

  const { oldLines, newLines } = useFileLines(
    workspaceId,
    shouldSkipFileLines ? null : content.filePath,
    shouldSkipFileLines ? null : content.previousFilePath,
    shouldSkipFileLines ? null : content.status,
    // The vs-target-branch diff is computed against merge-base(target, HEAD), so
    // its old-side line numbers reference the merge-base — fetch oldLines from
    // that exact commit. Fall back to undefined (→ target branch) only when the
    // merge-base is unknown. The uncommitted scope diffs against HEAD.
    content.isTargetBranchDiff ? (content.targetBranchMergeBase ?? undefined) : "HEAD",
  );

  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocusRequest, setSearchFocusRequest] = useState(0);
  const diffContentRef = useRef<HTMLDivElement>(null);

  const { currentMatch, totalMatches, goToNextMatch, goToPrevMatch, clearHighlights } = useInFileSearch({
    diffContentRef,
    query: searchQuery,
    isActive: isSearchOpen,
    activeFilePath: content.filePath,
  });

  useScrollPreservation({
    containerRef: diffContentRef,
    diffString: content.diffString,
    filePath: content.filePath,
  });

  const handleToggleViewType = useCallback((): void => {
    updateField(UserConfigField.FILE_BROWSER_DIFF_VIEW_TYPE, viewType === "unified" ? "split" : "unified");
  }, [viewType, updateField]);

  const handleToggleLineWrapping = useCallback((): void => {
    updateField(UserConfigField.FILE_BROWSER_LINE_WRAPPING, overflow === "wrap" ? "scroll" : "wrap");
  }, [overflow, updateField]);

  const [markdownMode, setMarkdownMode] = useAtom(markdownRenderModeAtom);
  const isRichMarkdownRenderingEnabled = useAtomValue(isRichMarkdownRenderingEnabledAtom);

  // ReadOnlyPreview is the only path that supports rendered markdown — used for
  // file-view selections and "no diff" states. Hide the toggle elsewhere. Even
  // when visible, the toggle is shown disabled (with a hint) until the
  // experimental `enable_rich_markdown_rendering` flag is enabled.
  const isMarkdownToggleVisible = useMemo((): boolean => {
    const fp = content.filePath;
    if (!fp || !isMarkdownPath(fp)) return false;
    if (content.isBinary || content.errorMessage) return false;
    if (content.isCommitDiff) return false;
    if (content.isFileView) return true;
    return !content.diffString;
  }, [
    content.filePath,
    content.isBinary,
    content.errorMessage,
    content.isCommitDiff,
    content.isFileView,
    content.diffString,
  ]);

  const handleToggleSearch = useCallback((): void => {
    setIsSearchOpen((prev) => {
      if (prev) clearHighlights();
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
      // Find-in-file is hidden in rendered mode; close it on the way in so the
      // search bar doesn't get stuck open with no button to dismiss it.
      if (next === "rendered") handleCloseSearch();
      return next;
    });
  }, [setMarkdownMode, handleCloseSearch]);

  // Find-in-file walks source-view DOM; rendered markdown has none. The rendered
  // path only mounts when the experimental flag is on, so the persisted
  // "rendered" preference doesn't suppress find-in-file when the flag is off.
  const isRenderedMarkdownActive =
    isMarkdownToggleVisible && markdownMode === "rendered" && isRichMarkdownRenderingEnabled;

  // Quick-open a rendered view of a markdown file in the Files panel — offered
  // on the diff/commit headers (the file-view header has the render toggle
  // instead). Hidden while the experimental rendering flag is off, since the
  // opened view would just be source.
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const canQuickOpenRenderedMarkdown =
    content.filePath !== null && isMarkdownPath(content.filePath) && isRichMarkdownRenderingEnabled;
  const handleOpenRenderedMarkdown = useCallback((): void => {
    if (!content.filePath) return;
    setMarkdownMode("rendered");
    openFileViewTab({ workspaceId, filePath: content.filePath });
  }, [content.filePath, setMarkdownMode, openFileViewTab, workspaceId]);

  useKeybindingHandler("find_in_file", () => {
    if (!content.filePath || isRenderedMarkdownActive) return;
    setIsSearchOpen(true);
    setSearchFocusRequest((n) => n + 1);
  });

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

  // Which panel's recents the header's path dropdown feeds and re-opens into —
  // derived from the selection kind, which by construction matches the panel
  // embedding this viewer (Files shows file-views, Commits shows commit diffs,
  // Changes shows everything else).
  const recentFilesScope: RecentFilesScope = useMemo(() => {
    if (content.isFileView) return { panel: "files" };
    if (content.isCommitDiff && content.commitHash !== null) {
      return { panel: "commits", commitHash: content.commitHash };
    }
    return {
      panel: "changes",
      status: content.status,
      scope: content.isTargetBranchDiff ? "vs-target-branch" : "uncommitted",
    };
  }, [content.isFileView, content.isCommitDiff, content.commitHash, content.status, content.isTargetBranchDiff]);

  const renderDiffBody = (): ReactElement => {
    const { filePath, errorMessage, isBinary, status, diffString, previousFilePath } = content;

    if (!filePath) return <EmptyBody />;
    if (errorMessage) return <DiffErrorBanner errorMessage={errorMessage} />;
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
    if (!diffString) return <ReadOnlyPreview workspaceId={workspaceId} filePath={filePath} />;

    // Added or deleted files have only one side, so a side-by-side split is meaningless.
    const effectiveViewType = status === "A" || status === "D" ? "unified" : viewType;
    const diffProps = { diffString, viewType: effectiveViewType, overflow, themeType: appTheme, oldLines, newLines };

    if (status === "D") {
      return (
        <>
          <DeletedFileBanner workspaceId={workspaceId} filePath={filePath} />
          {renderDiffContent(diffProps)}
        </>
      );
    }

    if (status === "R" && previousFilePath) {
      return (
        <>
          <RenameBanner oldPath={previousFilePath} newPath={filePath} />
          {renderDiffContent(diffProps)}
        </>
      );
    }
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

      {content.isFileView && content.filePath ? (
        <>
          <DiffViewerHeader
            workspaceId={workspaceId}
            filePath={content.filePath}
            recentFilesScope={recentFilesScope}
            tabFilePath={content.tabFilePath ?? undefined}
            addedLines={0}
            removedLines={0}
            fileStatus={null}
            isBinary={false}
            viewOptions={viewOptions}
            treeOptions={treeOptions}
            leadingControl={sidebarToggle}
            trailingActions={headerActions}
          />
          <Flex ref={diffContentRef} direction="column" flexGrow="1" overflow="hidden" className={styles.content}>
            <ReadOnlyPreview workspaceId={workspaceId} filePath={content.filePath} />
          </Flex>
        </>
      ) : content.isCommitDiff && content.filePath ? (
        <>
          <DiffViewerHeader
            workspaceId={workspaceId}
            filePath={content.filePath}
            recentFilesScope={recentFilesScope}
            tabFilePath={content.tabFilePath ?? undefined}
            addedLines={commitFileLineCounts.added}
            removedLines={commitFileLineCounts.removed}
            fileStatus={null}
            isBinary={false}
            viewOptions={viewOptions}
            treeOptions={treeOptions}
            leadingControl={sidebarToggle}
            trailingActions={headerActions}
            onOpenRenderedMarkdown={
              canQuickOpenRenderedMarkdown && commitFileStatus !== "D" ? handleOpenRenderedMarkdown : undefined
            }
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
                {commitFilePreviousPath && <RenameBanner oldPath={commitFilePreviousPath} newPath={content.filePath} />}
                {renderDiffContent({
                  diffString: commitFileDiffString,
                  // Added or deleted files have only one side; a split is meaningless.
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
      ) : content.filePath ? (
        <>
          <DiffViewerHeader
            workspaceId={workspaceId}
            filePath={content.filePath}
            recentFilesScope={recentFilesScope}
            tabFilePath={content.tabFilePath ?? undefined}
            addedLines={content.addedLines}
            removedLines={content.removedLines}
            fileStatus={content.status}
            isBinary={content.isBinary}
            viewOptions={viewOptions}
            treeOptions={treeOptions}
            leadingControl={sidebarToggle}
            trailingActions={headerActions}
            onOpenRenderedMarkdown={
              canQuickOpenRenderedMarkdown && !content.isBinary && content.status !== "D"
                ? handleOpenRenderedMarkdown
                : undefined
            }
          />
          <Flex ref={diffContentRef} direction="column" flexGrow="1" overflow="hidden" className={styles.content}>
            {renderDiffBody()}
          </Flex>
        </>
      ) : (
        <>
          {/* No file selected: still show a minimal header so the sidebar toggle
              and the list's tree options stay reachable, plus the
              always-visible empty body. */}
          <Flex
            align="center"
            justify="between"
            gap="2"
            px="3"
            flexShrink="0"
            className={styles.emptyHeader}
            data-testid={ElementIds.DIFF_FILE_HEADER}
          >
            {sidebarToggle ?? <span />}
            <DiffViewerMenu workspaceId={workspaceId} fileContext={null} isBinary={false} treeOptions={treeOptions} />
          </Flex>
          {renderDiffBody()}
        </>
      )}
    </Flex>
  );
};

/** The viewer body when no file is selected. */
const EmptyBody = (): ReactElement => (
  <Flex align="center" justify="center" flexGrow="1" data-testid={ElementIds.DIFF_VIEWER_EMPTY}>
    <Text size="2" color="gray">
      Open a file to view it
    </Text>
  </Flex>
);
