import { Box, Flex, Text } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useRef, useState } from "react";

import { ElementIds, UserConfigField } from "~/api";
import { useTimedLatch } from "~/common/Hooks.ts";
import { useKeybindingHandler } from "~/common/keybindings";
import { invalidateWorkspaceGitQueries } from "~/common/queryClient.ts";
import {
  appThemeAtom,
  fileBrowserDiffViewTypeAtom,
  fileBrowserLineWrappingAtom,
} from "~/common/state/atoms/userConfig.ts";
import { useUserConfig } from "~/common/state/hooks/useUserConfig.ts";
import { invalidateWorkspaceCommitDiff, useWorkspaceCommitDiff } from "~/common/state/hooks/useWorkspaceCommitDiff.ts";
import { useForceRefreshWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import type { MarkdownRenderMode } from "~/pages/workspace/diffPanel/atoms.ts";
import {
  closeDiffTabAtom,
  isMarkdownPath,
  markdownRenderModeAtom,
  openFileViewTabAtom,
} from "~/pages/workspace/diffPanel/atoms.ts";
import { BinaryPreview } from "~/pages/workspace/diffPanel/BinaryPreview.tsx";
import { DeletedFileBanner } from "~/pages/workspace/diffPanel/DeletedFileBanner.tsx";
import { DiffErrorBanner } from "~/pages/workspace/diffPanel/DiffErrorBanner.tsx";
import { InFileSearchBar } from "~/pages/workspace/diffPanel/InFileSearchBar.tsx";
import { LargeDiffGate } from "~/pages/workspace/diffPanel/LargeDiffGate.tsx";
import { PierreDiffView } from "~/pages/workspace/diffPanel/PierreDiffView.tsx";
import { ReadOnlyPreview } from "~/pages/workspace/diffPanel/ReadOnlyPreview.tsx";
import { RenameBanner } from "~/pages/workspace/diffPanel/RenameBanner.tsx";
import type { DiffViewType } from "~/pages/workspace/diffPanel/types.ts";
import { useFileLines } from "~/pages/workspace/diffPanel/useFileLines.ts";
import { useInFileSearch } from "~/pages/workspace/diffPanel/useInFileSearch.ts";
import { useScrollPreservation } from "~/pages/workspace/diffPanel/useScrollPreservation.ts";
import { IndeterminateProgress } from "~/pages/workspace/diffViewer/IndeterminateProgress.tsx";
import { determineFileStatus } from "~/pages/workspace/panels/fileBrowser/utils.ts";
import { getLineCounts, parseDiff } from "~/pages/workspace/utils/diff.ts";

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
  /** Clear the host panel's local click selection for `filePath`, invoked
   *  alongside the shared-tab close when the deleted-file banner is dismissed.
   *  Panels whose selection can't reach a deleted file (Files / Commits) omit it. */
  onCloseFile?: (filePath: string) => void;
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
  onCloseFile,
}: DiffViewerProps): ReactElement => {
  const content = useDiffViewerContent(workspaceId, selection);
  const closeDiffTab = useSetAtom(closeDiffTabAtom);
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
  const rootRef = useRef<HTMLDivElement>(null);
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

  // A quick-opened file-view can carry an explicit "rendered" request (see the
  // DiffSelection type). It overrides the persisted global render-mode WITHOUT
  // writing it — the user's preference survives the quick look — and stays in
  // force until the user toggles the mode, which records a dismissal. A repeat
  // request (newer `openedAt`) re-applies the override.
  const [renderOverrideDismissedAt, setRenderOverrideDismissedAt] = useState<number | null>(null);
  const isQuickOpenRenderActive =
    selection?.kind === "file-view" &&
    selection.markdownMode === "rendered" &&
    (renderOverrideDismissedAt === null || (selection.openedAt ?? 0) > renderOverrideDismissedAt);
  const effectiveMarkdownMode: MarkdownRenderMode = isQuickOpenRenderActive ? "rendered" : markdownMode;

  // ReadOnlyPreview is the only path that supports rendered markdown — used for
  // file-view selections and "no diff" states. Hide the toggle elsewhere.
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
    // Flip from the EFFECTIVE mode (a quick-open override may differ from the
    // persisted preference) and dismiss any active override so the toggle
    // always visibly changes the view.
    const next = effectiveMarkdownMode === "rendered" ? "raw" : "rendered";
    setRenderOverrideDismissedAt(Date.now());
    setMarkdownMode(next);
    // Find-in-file is hidden in rendered mode; close it on the way in so the
    // search bar doesn't get stuck open with no button to dismiss it.
    if (next === "rendered") handleCloseSearch();
  }, [effectiveMarkdownMode, setMarkdownMode, handleCloseSearch]);

  // Find-in-file walks source-view DOM; rendered markdown has none.
  const isRenderedMarkdownActive = isMarkdownToggleVisible && effectiveMarkdownMode === "rendered";

  // Quick-open a rendered view of a markdown file in the Files panel — offered
  // on the diff/commit headers (the file-view header has the render toggle
  // instead). The rendered request rides on the tab (`markdownMode`) so the
  // receiving viewer renders it without this path rewriting the global
  // render-mode preference.
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const canQuickOpenRenderedMarkdown = content.filePath !== null && isMarkdownPath(content.filePath);
  const handleOpenRenderedMarkdown = useCallback((): void => {
    if (!content.filePath) return;
    openFileViewTab({ workspaceId, filePath: content.filePath, markdownMode: "rendered" });
  }, [content.filePath, openFileViewTab, workspaceId]);

  // Manual refresh from the triple-dot menu. File views resolve to git-derived
  // react-query entries, so invalidating the git subtree refetches them. Commit
  // diffs are keyed OUTSIDE that subtree (immutable by hash), so they need their
  // own key invalidated — the only recovery path when the initial fetch failed.
  // The workspace diff additionally caches on the BACKEND, so diff selections go
  // through the force_refresh fetch instead.
  const refreshWorkspaceDiff = useForceRefreshWorkspaceDiff(workspaceId);
  const handleRefresh = useCallback((): void => {
    if (content.isFileView || content.isCommitDiff) {
      invalidateWorkspaceGitQueries(workspaceId);
      if (content.isCommitDiff && content.commitHash !== null) {
        invalidateWorkspaceCommitDiff(workspaceId, content.commitHash);
      }
      return;
    }
    void refreshWorkspaceDiff();
  }, [content.isFileView, content.isCommitDiff, content.commitHash, workspaceId, refreshWorkspaceDiff]);

  // Dismiss the deleted-file banner: clear the shared diff tab by its IDENTITY
  // path (which carries a scope prefix for "All"-scope diffs, so the real path
  // would never match) and the host panel's local click selection, so the close
  // lands whichever of the two sources drove the view.
  const handleCloseDeletedFile = useCallback((): void => {
    const tabId = content.tabFilePath ?? content.filePath;
    if (tabId !== null) closeDiffTab({ workspaceId, filePath: tabId });
    if (content.filePath !== null) onCloseFile?.(content.filePath);
  }, [closeDiffTab, workspaceId, content.tabFilePath, content.filePath, onCloseFile]);

  // The find shortcut is a window-level listener, and several viewers can be
  // mounted at once (one per Files / Changes / Commits panel in the section
  // grid). Only the viewer inside the active section responds, so a single
  // keypress opens one search bar rather than every mounted viewer's at once.
  // `PanelSection` marks the active section with `data-active="true"`; a click
  // anywhere in a section (a tree row, the diff) makes it the active one.
  useKeybindingHandler("find_in_file", () => {
    if (!content.filePath || isRenderedMarkdownActive) return;
    if (rootRef.current?.closest('[data-active="true"]') == null) return;
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
    isRendered: effectiveMarkdownMode === "rendered",
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
          <DeletedFileBanner onClose={handleCloseDeletedFile} />
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
    // DIFF_PANEL (and the DIFF_FILE_HEADER / DIFF_VIEWER_EMPTY testids below) are
    // per-instance: every mounted viewer carries the same value, so more than one
    // exists at once when Files / Changes / Commits panels are open together. Tests
    // must scope these within the host panel's container (see the
    // `get_diff_viewer_in` POM helper), never page-wide.
    <Flex ref={rootRef} direction="column" height="100%" position="relative" data-testid={ElementIds.DIFF_PANEL}>
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
            addedLines={0}
            removedLines={0}
            fileStatus={null}
            isBinary={false}
            viewOptions={viewOptions}
            treeOptions={treeOptions}
            leadingControl={sidebarToggle}
            onRefresh={handleRefresh}
          />
          <Flex ref={diffContentRef} direction="column" flexGrow="1" overflow="hidden" className={styles.content}>
            <ReadOnlyPreview
              workspaceId={workspaceId}
              filePath={content.filePath}
              renderModeOverride={isQuickOpenRenderActive ? "rendered" : undefined}
            />
          </Flex>
        </>
      ) : content.isCommitDiff && content.filePath ? (
        <>
          <DiffViewerHeader
            workspaceId={workspaceId}
            filePath={content.filePath}
            recentFilesScope={recentFilesScope}
            addedLines={commitFileLineCounts.added}
            removedLines={commitFileLineCounts.removed}
            fileStatus={null}
            isBinary={false}
            viewOptions={viewOptions}
            treeOptions={treeOptions}
            leadingControl={sidebarToggle}
            onRefresh={handleRefresh}
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
            addedLines={content.addedLines}
            removedLines={content.removedLines}
            fileStatus={content.status}
            isBinary={content.isBinary}
            viewOptions={viewOptions}
            treeOptions={treeOptions}
            leadingControl={sidebarToggle}
            onRefresh={handleRefresh}
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
            <DiffViewerMenu
              workspaceId={workspaceId}
              fileContext={null}
              isBinary={false}
              treeOptions={treeOptions}
              onRefresh={handleRefresh}
            />
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
