import { ContextMenu, Flex } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { Eye, Maximize2, Minimize2, Search, SplitSquareHorizontal, WrapText, X, XCircle } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { fileBrowserTabCloseBehaviorAtom } from "~/common/state/atoms/userConfig.ts";
import { expandedPanelIdAtom } from "~/components/panels/atoms.ts";
import { TabBar } from "~/components/tabs/TabBar.tsx";
import type { TabDefinition } from "~/components/tabs/types.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { FileContextMenu } from "~/pages/workspace/panels/fileBrowser/FileContextMenu.tsx";
import type { FileContextMenuContext } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { isBinaryFile } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import {
  closeAllDiffTabsAtom,
  closeDiffPanelAtom,
  closeDiffTabAtom,
  closeOtherDiffTabsAtom,
  diffPanelStateAtomFamily,
  openCombinedDiffTabAtom,
  openCommitDiffTabAtom,
  openDiffTabAtom,
  openFileViewTabAtom,
  reorderTabsAtom,
} from "./atoms.ts";
import styles from "./DiffTabBar.module.scss";
import type { DiffTab, DiffViewType } from "./types.ts";
import { isCombinedTab, isCommitDiffTab, isFileViewTab, TARGET_BRANCH_DIFF_PREFIX } from "./types.ts";

type TabCloseContextMenuProps = {
  children: ReactNode;
  filePath: string;
  workspaceId: string;
};

const TabCloseContextMenu = ({ children, filePath, workspaceId }: TabCloseContextMenuProps): ReactElement => {
  const closeDiffTab = useSetAtom(closeDiffTabAtom);
  const closeOtherDiffTabs = useSetAtom(closeOtherDiffTabsAtom);
  const closeAllDiffTabs = useSetAtom(closeAllDiffTabsAtom);
  const diffPanelState = useAtomValue(diffPanelStateAtomFamily(workspaceId));

  const handleCloseTab = useCallback((): void => {
    closeDiffTab({ workspaceId, filePath, tabCloseBehavior: "mru" });
  }, [closeDiffTab, workspaceId, filePath]);

  const handleCloseOtherTabs = useCallback((): void => {
    closeOtherDiffTabs({ workspaceId, filePath });
  }, [closeOtherDiffTabs, workspaceId, filePath]);

  const handleCloseAllTabs = useCallback((): void => {
    closeAllDiffTabs({ workspaceId });
  }, [closeAllDiffTabs, workspaceId]);

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content size="1" className={styles.tabContextMenu}>
        <ContextMenu.Item onSelect={handleCloseTab}>
          <X size={14} />
          Close tab
        </ContextMenu.Item>
        <ContextMenu.Item disabled={diffPanelState.openTabs.length <= 1} onSelect={handleCloseOtherTabs}>
          <XCircle size={14} />
          Close other tabs
        </ContextMenu.Item>
        <ContextMenu.Item onSelect={handleCloseAllTabs}>
          <XCircle size={14} />
          Close all
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};

const diffTabToDefinition = (tab: DiffTab, workspaceId: string): TabDefinition => {
  if (isCombinedTab(tab)) {
    return {
      id: tab.filePath,
      label: "Review All",
      dataTestId: ElementIds.DIFF_TAB,
      contextMenu: (children) => (
        <TabCloseContextMenu filePath={tab.filePath} workspaceId={workspaceId}>
          {children}
        </TabCloseContextMenu>
      ),
    };
  }

  if (isFileViewTab(tab)) {
    const fileName = tab.realPath.split("/").pop() ?? tab.realPath;
    return {
      id: tab.filePath,
      label: fileName,
      // labelContent overrides the default text rendering — put the hidden
      // marker inside the existing label span (not the `icon` slot, whose
      // wrapper would add a left-margin gap visible only on file-view tabs).
      labelContent: (
        <>
          {fileName}
          <span data-testid={ElementIds.FILE_VIEW_TAB_MARKER} hidden />
        </>
      ),
      dataTestId: ElementIds.DIFF_TAB,
      contextMenu: (children) => (
        <TabCloseContextMenu filePath={tab.filePath} workspaceId={workspaceId}>
          {children}
        </TabCloseContextMenu>
      ),
    };
  }

  if (isCommitDiffTab(tab)) {
    const fileName = tab.realPath.split("/").pop() ?? tab.realPath;
    const shortHash = tab.commitHash.slice(0, 7);
    return {
      id: tab.filePath,
      label: `${fileName} (${shortHash})`,
      dataTestId: ElementIds.DIFF_TAB,
      contextMenu: (children) => (
        <TabCloseContextMenu filePath={tab.filePath} workspaceId={workspaceId}>
          {children}
        </TabCloseContextMenu>
      ),
    };
  }

  const realPath = tab.filePath.startsWith(TARGET_BRANCH_DIFF_PREFIX)
    ? tab.filePath.slice(TARGET_BRANCH_DIFF_PREFIX.length)
    : tab.filePath;
  const fileName = realPath.split("/").pop() ?? realPath;
  const menuContext: FileContextMenuContext = {
    filePath: realPath,
    isFolder: false,
    fileStatus: tab.status,
    isBinary: isBinaryFile(fileName),
    source: "diff-tab",
    tabFilePath: tab.filePath,
  };
  return {
    id: tab.filePath,
    label: fileName,
    dataTestId: ElementIds.DIFF_TAB,
    contextMenu: (children) => (
      <FileContextMenu context={menuContext} workspaceId={workspaceId} contentClassName={styles.tabContextMenu}>
        {children}
      </FileContextMenu>
    ),
  };
};

type DiffTabBarProps = {
  workspaceId: string;
  viewType: DiffViewType;
  onToggleViewType: () => void;
  lineWrapping: "wrap" | "scroll";
  onToggleLineWrapping: () => void;
  isSearchOpen: boolean;
  onToggleSearch: () => void;
  isBinaryFile: boolean;
  showRenderToggle: boolean;
  isRendered: boolean;
  /** Off => the eye icon renders disabled with a hint tooltip pointing at
   * Settings → Experimental, where the flag lives. */
  isRenderToggleEnabled: boolean;
  onToggleRender: () => void;
};

export const DiffTabBar = ({
  workspaceId,
  viewType,
  onToggleViewType,
  lineWrapping,
  onToggleLineWrapping,
  isSearchOpen,
  onToggleSearch,
  isBinaryFile,
  showRenderToggle,
  isRendered,
  isRenderToggleEnabled,
  onToggleRender,
}: DiffTabBarProps): ReactElement => {
  const diffPanelState = useAtomValue(diffPanelStateAtomFamily(workspaceId));
  const openDiffTab = useSetAtom(openDiffTabAtom);
  const openCombinedTab = useSetAtom(openCombinedDiffTabAtom);
  const openCommitDiffTab = useSetAtom(openCommitDiffTabAtom);
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const closeDiffTab = useSetAtom(closeDiffTabAtom);
  const reorderTabs = useSetAtom(reorderTabsAtom);
  const closeDiffPanel = useSetAtom(closeDiffPanelAtom);
  const [expandedPanelId, setExpandedPanelId] = useAtom(expandedPanelIdAtom);
  const isExpanded = expandedPanelId != null;
  const tabCloseBehavior = useAtomValue(fileBrowserTabCloseBehaviorAtom);

  const { openTabs, activeTabPath } = diffPanelState;

  // Counter incremented when exiting expand mode so TabBar re-scrolls the active tab.
  const [scrollTrigger, setScrollTrigger] = useState(0);

  const tabDefinitions = useMemo(
    (): Array<TabDefinition> => openTabs.map((tab) => diffTabToDefinition(tab, workspaceId)),
    [openTabs, workspaceId],
  );

  const openTabIds = useMemo((): Array<string> => openTabs.map((t) => t.filePath), [openTabs]);

  const handleActivateTab = useCallback(
    (filePath: string): void => {
      const tab = openTabs.find((t) => t.filePath === filePath);
      if (!tab) return;
      if (isCombinedTab(tab)) {
        openCombinedTab({ workspaceId });
      } else if (isFileViewTab(tab)) {
        openFileViewTab({ workspaceId, filePath: tab.realPath });
      } else if (isCommitDiffTab(tab)) {
        openCommitDiffTab({ workspaceId, commitHash: tab.commitHash, filePath: tab.realPath });
      } else {
        const realPath = filePath.startsWith(TARGET_BRANCH_DIFF_PREFIX)
          ? filePath.slice(TARGET_BRANCH_DIFF_PREFIX.length)
          : filePath;
        openDiffTab({ workspaceId, filePath: realPath, status: tab.status, scope: tab.scope });
      }
    },
    [openDiffTab, openCombinedTab, openCommitDiffTab, openFileViewTab, workspaceId, openTabs],
  );

  const handleCloseTab = useCallback(
    (filePath: string): void => {
      closeDiffTab({ workspaceId, filePath, tabCloseBehavior });
    },
    [closeDiffTab, workspaceId, tabCloseBehavior],
  );

  const handleReorder = useCallback(
    (newOrder: Array<string>): void => {
      reorderTabs({ workspaceId, newOrder });
    },
    [reorderTabs, workspaceId],
  );

  const handleToggleExpand = useCallback((): void => {
    // Toggle expand mode: when expanded, set the "files" panel as the expanded panel
    // so DockingLayout knows to keep the file browser zone visible.
    if (isExpanded) {
      setExpandedPanelId(null);
      // Re-scroll the active tab into view after collapsing.
      setScrollTrigger((n) => n + 1);
    } else {
      setExpandedPanelId("files");
    }
  }, [setExpandedPanelId, isExpanded]);

  const handleClosePanel = useCallback((): void => {
    if (isExpanded) {
      setExpandedPanelId(null);
    }
    closeDiffPanel();
  }, [closeDiffPanel, isExpanded, setExpandedPanelId]);

  return (
    <TabBar
      tabs={tabDefinitions}
      openTabIds={openTabIds}
      activeTabId={activeTabPath ?? ""}
      onActivate={handleActivateTab}
      onClose={handleCloseTab}
      onReorder={handleReorder}
      variant="compact"
      alwaysCloseable
      scrollTrigger={scrollTrigger}
      rightContent={
        <Flex align="center" gap="2" flexShrink="0" className={styles.windowControls}>
          <TooltipIconButton
            tooltipText={isExpanded ? "Exit review mode" : "Expand"}
            size="1"
            onClick={handleToggleExpand}
            data-testid={ElementIds.DIFF_EXPAND_TOGGLE}
          >
            {isExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </TooltipIconButton>

          <TooltipIconButton
            tooltipText="Close diff panel"
            size="1"
            onClick={handleClosePanel}
            data-testid={ElementIds.DIFF_CLOSE_PANEL_BUTTON}
          >
            <X size={14} />
          </TooltipIconButton>
        </Flex>
      }
    >
      <Flex align="center" gap="2" flexShrink="0" className={styles.controls}>
        {/* Find-in-file walks the source-view DOM (Pierre shadow root or
            ReadOnlyPreview text). The rendered-markdown view has neither, so
            we hide the button rather than show a control that does nothing. */}
        {!(showRenderToggle && isRendered) && (
          <TooltipIconButton
            tooltipText="Find in file"
            size="1"
            onClick={onToggleSearch}
            disabled={isBinaryFile}
            className={isSearchOpen ? styles.activeControl : undefined}
            data-testid={ElementIds.DIFF_FIND_IN_FILE_BTN}
          >
            <Search size={14} />
          </TooltipIconButton>
        )}

        <TooltipIconButton
          tooltipText={viewType === "unified" ? "Switch to split view" : "Switch to unified view"}
          size="1"
          onClick={onToggleViewType}
          className={viewType === "split" ? styles.activeControl : undefined}
          data-testid={ElementIds.DIFF_SPLIT_VIEW_TOGGLE}
          data-state={viewType}
        >
          <SplitSquareHorizontal size={14} />
        </TooltipIconButton>

        <TooltipIconButton
          tooltipText={lineWrapping === "wrap" ? "Switch to scroll" : "Switch to wrap"}
          size="1"
          onClick={onToggleLineWrapping}
          className={lineWrapping === "wrap" ? styles.activeControl : undefined}
          data-testid={ElementIds.DIFF_LINE_WRAP_TOGGLE}
        >
          <WrapText size={14} />
        </TooltipIconButton>

        {showRenderToggle && (
          <TooltipIconButton
            tooltipText={
              isRenderToggleEnabled
                ? isRendered
                  ? "Show source"
                  : "Show rendered"
                : "Markdown rendering is an experimental feature that you have to enable in settings first."
            }
            size="1"
            onClick={onToggleRender}
            disabled={!isRenderToggleEnabled}
            className={isRendered ? styles.activeControl : undefined}
            data-testid={ElementIds.DIFF_RENDER_TOGGLE}
            data-state={isRendered ? "rendered" : "source"}
          >
            <Eye size={14} />
          </TooltipIconButton>
        )}
      </Flex>
    </TabBar>
  );
};
