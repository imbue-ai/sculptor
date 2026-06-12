import { Button, Flex } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { Layers } from "lucide-react";
import type { CSSProperties, ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { ElementIds } from "~/api";
import { useTimedLatch } from "~/common/Hooks.ts";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { isReviewAllEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { useWorkspaceCommits } from "~/common/state/hooks/useWorkspaceCommits.ts";
import type { FileBrowserTab } from "~/components/panels/atoms.ts";
import { activeFileBrowserTabAtomFamily } from "~/components/panels/atoms.ts";
import { openCombinedDiffTabAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";

import { fileBrowserStateAtomFamily, setSearchAtom, toggleViewModeAtom } from "./fileBrowser/atoms.ts";
import { ChangesTabContent } from "./fileBrowser/ChangesTabContent.tsx";
import { EmptyState, SkeletonLoading } from "./fileBrowser/EmptyStates.tsx";
import { FileBrowserHeader } from "./fileBrowser/FileBrowserHeader.tsx";
import { FileSearch } from "./fileBrowser/FileSearch.tsx";
import { FileTree } from "./fileBrowser/FileTree.tsx";
import { useFileSearch, useFileStatusMap, useFileTree } from "./fileBrowser/hooks.ts";
import styles from "./FileBrowserPanel.module.scss";
import { HistoryTabContent } from "./historyPanel/HistoryTabContent.tsx";

const TAB_LABELS: ReadonlyArray<{ id: FileBrowserTab; label: string; testId: ElementIds }> = [
  { id: "all", label: "Browse", testId: ElementIds.FILE_BROWSER_TAB_ALL },
  { id: "changes", label: "Changes", testId: ElementIds.FILE_BROWSER_TAB_CHANGES },
  { id: "history", label: "Commits", testId: ElementIds.FILE_BROWSER_TAB_HISTORY },
];

/** Styles to keep a tab pane mounted but visually hidden when inactive. */
const HIDDEN_STYLE: CSSProperties = { display: "none" };
const VISIBLE_STYLE: CSSProperties = { display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden" };

// Holds the spin on long enough for the icon to complete a visible arc even
// when the underlying fetch returns very quickly.
const SPIN_MIN_HOLD_MS = 1000;

export const FileBrowserPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const setSearch = useSetAtom(setSearchAtom);
  const toggleViewMode = useSetAtom(toggleViewModeAtom);
  const openCombinedDiffTab = useSetAtom(openCombinedDiffTabAtom);
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceID ?? ""));
  const { tree, isPending, isFetching, isGenerating, refetch } = useFileTree(workspaceID ?? "", "vs-target-branch");
  const isSpinning = useTimedLatch(isFetching || isGenerating, SPIN_MIN_HOLD_MS);

  const isReviewAllEnabled = useAtomValue(isReviewAllEnabledAtom);
  const [activeTab, setActiveTab] = useAtom(activeFileBrowserTabAtomFamily(workspaceID ?? ""));
  const allChangesStatusMap = useFileStatusMap(workspaceID ?? "", "vs-target-branch");
  const changesCount = allChangesStatusMap.size;
  const { data: commits } = useWorkspaceCommits(workspaceID ?? "");
  const commitCount = commits?.commits.length ?? 0;
  const hasChangesToReview = changesCount > 0 || commitCount > 0;

  const { viewMode, searchQuery, searchOpen: isSearchOpen } = fileBrowserState;

  const { resultCount, matchingPaths } = useFileSearch(workspaceID ?? "", isSearchOpen ? searchQuery : "");

  const activeSearchFilter = useMemo(() => {
    if (!isSearchOpen || searchQuery.length === 0) return null;
    return matchingPaths;
  }, [isSearchOpen, searchQuery, matchingPaths]);

  const handleSearchOpen = useCallback((): void => {
    if (workspaceID) {
      setSearch({ workspaceId: workspaceID, query: "", open: true });
    }
  }, [workspaceID, setSearch]);

  const handleSearchClose = useCallback((): void => {
    if (workspaceID) {
      setSearch({ workspaceId: workspaceID, query: "", open: false });
    }
  }, [workspaceID, setSearch]);

  const handleSearchQueryChange = useCallback(
    (query: string): void => {
      if (workspaceID) {
        setSearch({ workspaceId: workspaceID, query, open: true });
      }
    },
    [workspaceID, setSearch],
  );

  const handleToggleViewMode = useCallback((): void => {
    if (workspaceID) {
      toggleViewMode({ workspaceId: workspaceID });
    }
  }, [workspaceID, toggleViewMode]);

  const handleTabChange = (tab: FileBrowserTab): void => {
    setActiveTab(tab);
  };

  const handleReviewAll = useCallback((): void => {
    if (workspaceID) {
      openCombinedDiffTab({ workspaceId: workspaceID, defaultScope: "vs-target-branch" });
    }
  }, [workspaceID, openCombinedDiffTab]);

  if (!workspaceID) {
    return null;
  }

  const hasFiles = tree.length > 0;

  const renderAllTab = (): ReactElement => {
    if (isPending && !hasFiles) {
      return <SkeletonLoading />;
    }

    if (!hasFiles) {
      return <EmptyState />;
    }
    return <FileTree workspaceId={workspaceID} viewMode={viewMode} searchMatchingPaths={activeSearchFilter} />;
  };

  const renderChangesTab = (): ReactElement => {
    return <ChangesTabContent workspaceId={workspaceID} viewMode={viewMode} />;
  };

  return (
    <Flex direction="column" height="100%" data-testid={ElementIds.FILE_BROWSER_PANEL}>
      {isSearchOpen ? (
        <FileSearch
          query={searchQuery}
          onQueryChange={handleSearchQueryChange}
          onClose={handleSearchClose}
          resultCount={resultCount}
        />
      ) : (
        <FileBrowserHeader
          workspaceId={workspaceID}
          viewMode={viewMode}
          activeTab={activeTab}
          isRefreshing={isSpinning}
          onToggleViewMode={handleToggleViewMode}
          onRefresh={refetch}
          onSearchOpen={handleSearchOpen}
        />
      )}
      <Flex align="center" gap="1" className={styles.tabBar}>
        {TAB_LABELS.map((tab) => (
          <Button
            key={tab.id}
            variant="ghost"
            size="1"
            color="gray"
            className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ""}`}
            onClick={() => handleTabChange(tab.id)}
            data-testid={tab.testId}
          >
            {tab.id === "changes" && changesCount > 0
              ? `${tab.label} ${changesCount}`
              : tab.id === "history" && commitCount > 0
                ? `${tab.label} ${commitCount}`
                : tab.label}
          </Button>
        ))}
        <span style={{ flex: 1 }} />
        {isReviewAllEnabled && hasChangesToReview && (
          <Button
            variant="ghost"
            size="1"
            color="gray"
            className={styles.reviewAllButton}
            onClick={handleReviewAll}
            data-testid={ElementIds.CHANGES_REVIEW_ALL_BTN}
          >
            <Layers size={12} />
            <span className={styles.reviewAllLabel}>Review all</span>
          </Button>
        )}
      </Flex>
      {/* All tabs stay mounted so switching doesn't trigger data refetches. */}
      <div style={activeTab === "all" ? VISIBLE_STYLE : HIDDEN_STYLE}>{renderAllTab()}</div>
      <div style={activeTab === "changes" ? VISIBLE_STYLE : HIDDEN_STYLE}>{renderChangesTab()}</div>
      <div style={activeTab === "history" ? VISIBLE_STYLE : HIDDEN_STYLE}>
        <HistoryTabContent workspaceId={workspaceID} viewMode={viewMode} />
      </div>
    </Flex>
  );
};
