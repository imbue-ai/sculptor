import { useSetAtom } from "jotai";
import { ChevronsDownUp, List, ListTree, RefreshCw, Search } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { ElementIds } from "~/api";
import type { FileBrowserTab } from "~/components/panels/atoms.ts";
import { PanelHeader } from "~/components/panels/PanelHeader";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";

import { collapseAllCommitsAtom } from "../historyPanel/atoms.ts";
import { collapseAllChangesFoldersAtom, collapseAllFoldersAtom } from "./atoms.ts";
import styles from "./FileBrowserHeader.module.scss";
import type { ViewMode } from "./types.ts";

type FileBrowserHeaderProps = {
  workspaceId: string;
  viewMode: ViewMode;
  activeTab: FileBrowserTab;
  isRefreshing: boolean;
  onToggleViewMode: () => void;
  onRefresh: () => void;
  onSearchOpen: () => void;
};

export const FileBrowserHeader = ({
  workspaceId,
  viewMode,
  activeTab,
  isRefreshing,
  onToggleViewMode,
  onRefresh,
  onSearchOpen,
}: FileBrowserHeaderProps): ReactElement => {
  const collapseAllFolders = useSetAtom(collapseAllFoldersAtom);
  const collapseAllChangesFolders = useSetAtom(collapseAllChangesFoldersAtom);
  const collapseAllCommits = useSetAtom(collapseAllCommitsAtom);

  const handleCollapse = useCallback((): void => {
    if (activeTab === "changes") {
      collapseAllChangesFolders({ workspaceId });
    } else if (activeTab === "history") {
      collapseAllCommits({ workspaceId });
    } else {
      collapseAllFolders({ workspaceId });
    }
  }, [activeTab, collapseAllFolders, collapseAllChangesFolders, collapseAllCommits, workspaceId]);

  return (
    <PanelHeader
      title="File browser"
      actions={
        <>
          <TooltipIconButton
            tooltipText={viewMode === "tree" ? "Switch to flat list" : "Switch to tree view"}
            onClick={onToggleViewMode}
          >
            {viewMode === "tree" ? <List size={14} /> : <ListTree size={14} />}
          </TooltipIconButton>
          <TooltipIconButton
            tooltipText={activeTab === "history" ? "Collapse commits" : "Collapse folders"}
            onClick={handleCollapse}
            data-testid={ElementIds.FILE_BROWSER_COLLAPSE_FOLDERS_BTN}
          >
            <ChevronsDownUp size={14} />
          </TooltipIconButton>
          <TooltipIconButton
            tooltipText="Refresh"
            onClick={onRefresh}
            data-testid={ElementIds.FILE_BROWSER_REFRESH_BTN}
          >
            <RefreshCw size={14} className={`${styles.refreshIcon} ${isRefreshing ? styles.refreshSpinning : ""}`} />
          </TooltipIconButton>
          <TooltipIconButton
            tooltipText="Search files"
            onClick={onSearchOpen}
            data-testid={ElementIds.FILE_BROWSER_SEARCH_FILES_BTN}
          >
            <Search size={14} />
          </TooltipIconButton>
        </>
      }
    />
  );
};
