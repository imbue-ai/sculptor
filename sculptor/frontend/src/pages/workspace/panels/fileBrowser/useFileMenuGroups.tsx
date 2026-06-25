import { useAtomValue, useSetAtom } from "jotai";
import { ChevronsDown, ChevronsUp, Copy, ExternalLink, Eye, FileText, FolderOpen, X, XCircle } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";
import {
  closeAllDiffTabsAtom,
  closeDiffTabAtom,
  closeOtherDiffTabsAtom,
  diffPanelStateAtomFamily,
  openDiffTabAtom,
  openFileViewTabAtom,
} from "~/pages/workspace/components/diffPanel/atoms.ts";
import { useWorkspaceCodePath } from "~/pages/workspace/hooks/useWorkspaceCodePath.ts";

import { expandFoldersAtom } from "./atoms.ts";
import { openInOs } from "./hooks.ts";
import type { FileContextMenuContext } from "./types.ts";

export type MenuItem = {
  key: string;
  label: string;
  icon: ReactElement;
  disabled: boolean;
  handleSelect: () => void;
};

export type MenuGroup = Array<MenuItem>;

type UseFileMenuGroupsParams = {
  context: FileContextMenuContext;
  workspaceId: string;
  allDescendantFolderPaths?: Array<string>;
  isExpanded?: boolean;
  onCollapseChildren?: (folderPath: string) => void;
};

export const useFileMenuGroups = ({
  context,
  workspaceId,
  allDescendantFolderPaths,
  isExpanded,
  onCollapseChildren,
}: UseFileMenuGroupsParams): Array<MenuGroup> => {
  const openDiffTab = useSetAtom(openDiffTabAtom);
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const closeDiffTab = useSetAtom(closeDiffTabAtom);
  const closeOtherDiffTabs = useSetAtom(closeOtherDiffTabsAtom);
  const closeAllDiffTabs = useSetAtom(closeAllDiffTabsAtom);
  const expandFolders = useSetAtom(expandFoldersAtom);
  const diffPanelState = useAtomValue(diffPanelStateAtomFamily(workspaceId));
  const codePath = useWorkspaceCodePath(workspaceId);

  const isDeleted = context.fileStatus === "D";
  const isFile = !context.isFolder;
  const isDiffSource = context.source === "diff-header" || context.source === "diff-tab";
  const isCombinedDiffSource = context.source === "combined-diff-header";

  const handleOpenDiffView = useCallback((): void => {
    openDiffTab({ workspaceId, filePath: context.filePath, status: context.fileStatus ?? "M" });
  }, [openDiffTab, workspaceId, context.filePath, context.fileStatus]);

  const handleOpenFileView = useCallback((): void => {
    openFileViewTab({ workspaceId, filePath: context.filePath });
  }, [openFileViewTab, workspaceId, context.filePath]);

  const handleCopyFilePath = useCallback((): void => {
    const isAlreadyAbsolute = context.filePath.startsWith("/");
    const absolutePath = codePath && !isAlreadyAbsolute ? `${codePath}/${context.filePath}` : context.filePath;
    navigator.clipboard.writeText(absolutePath);
  }, [context.filePath, codePath]);

  const handleCopyRelativePath = useCallback((): void => {
    navigator.clipboard.writeText(context.filePath);
  }, [context.filePath]);

  const handleOpenInDefaultApp = useCallback((): void => {
    openInOs({ workspaceId, path: context.filePath, action: "open_file" });
  }, [workspaceId, context.filePath]);

  const handleOpenContainingFolder = useCallback((): void => {
    openInOs({ workspaceId, path: context.filePath, action: "open_containing_folder" });
  }, [workspaceId, context.filePath]);

  const handleExpandAllChildren = useCallback((): void => {
    if (allDescendantFolderPaths && allDescendantFolderPaths.length > 0) {
      expandFolders({ workspaceId, paths: [context.filePath, ...allDescendantFolderPaths] });
    }
  }, [expandFolders, workspaceId, context.filePath, allDescendantFolderPaths]);

  const handleCollapseAllChildren = useCallback((): void => {
    onCollapseChildren?.(context.filePath);
  }, [onCollapseChildren, context.filePath]);

  const tabId = context.tabFilePath ?? context.filePath;

  const handleCloseTab = useCallback((): void => {
    closeDiffTab({ workspaceId, filePath: tabId, tabCloseBehavior: "mru" });
  }, [closeDiffTab, workspaceId, tabId]);

  const handleCloseOtherTabs = useCallback((): void => {
    closeOtherDiffTabs({ workspaceId, filePath: tabId });
  }, [closeOtherDiffTabs, workspaceId, tabId]);

  const handleCloseAllTabs = useCallback((): void => {
    closeAllDiffTabs({ workspaceId });
  }, [closeAllDiffTabs, workspaceId]);

  return useMemo(() => {
    const groups: Array<MenuGroup> = [];

    // Group 1: Open diff view / View file
    const group1: MenuGroup = [];
    if (isFile && !isDiffSource && !isCombinedDiffSource) {
      group1.push({
        key: "open-diff",
        label: "Open diff view",
        icon: <Eye size={14} />,
        disabled: false,
        handleSelect: handleOpenDiffView,
      });
    }

    if (isFile && !isDeleted && !isCombinedDiffSource) {
      group1.push({
        key: "view-file",
        label: "View file",
        icon: <FileText size={14} />,
        disabled: false,
        handleSelect: handleOpenFileView,
      });
    }
    if (group1.length > 0) groups.push(group1);

    // Group 2: Copy paths
    const group2: MenuGroup = [
      {
        key: "copy-path",
        label: "Copy file path",
        icon: <Copy size={14} />,
        disabled: false,
        handleSelect: handleCopyFilePath,
      },
      {
        key: "copy-rel-path",
        label: "Copy relative path",
        icon: <Copy size={14} />,
        disabled: false,
        handleSelect: handleCopyRelativePath,
      },
    ];
    groups.push(group2);

    // Group 3: Open in OS (hidden when backend cannot access the host filesystem)
    if (getBackendCapabilities().canOpenInOS) {
      const group3: MenuGroup = [
        {
          key: "open-default",
          label: "Open in default app",
          icon: <ExternalLink size={14} />,
          disabled: isDeleted,
          handleSelect: handleOpenInDefaultApp,
        },
        {
          key: "open-folder",
          label: "Open containing folder",
          icon: <FolderOpen size={14} />,
          disabled: isDeleted,
          handleSelect: handleOpenContainingFolder,
        },
      ];
      groups.push(group3);
    }

    // Group 4: Folder actions
    if (context.isFolder) {
      const group4: MenuGroup = [];
      if (!isExpanded) {
        group4.push({
          key: "expand-children",
          label: "Expand all children",
          icon: <ChevronsDown size={14} />,
          disabled: false,
          handleSelect: handleExpandAllChildren,
        });
      } else {
        group4.push({
          key: "collapse-children",
          label: "Collapse all children",
          icon: <ChevronsUp size={14} />,
          disabled: false,
          handleSelect: handleCollapseAllChildren,
        });
      }
      groups.push(group4);
    }

    // Group 5: Tab actions (diff header and diff tabs)
    if (isDiffSource) {
      const group5: MenuGroup = [
        {
          key: "close-tab",
          label: "Close tab",
          icon: <X size={14} />,
          disabled: false,
          handleSelect: handleCloseTab,
        },
        {
          key: "close-other-tabs",
          label: "Close other tabs",
          icon: <XCircle size={14} />,
          disabled: diffPanelState.openTabs.length <= 1,
          handleSelect: handleCloseOtherTabs,
        },
        {
          key: "close-all-tabs",
          label: "Close all",
          icon: <XCircle size={14} />,
          disabled: false,
          handleSelect: handleCloseAllTabs,
        },
      ];
      groups.push(group5);
    }

    return groups;
  }, [
    isFile,
    isDiffSource,
    isCombinedDiffSource,
    context.isFolder,
    isDeleted,
    isExpanded,
    diffPanelState.openTabs.length,
    handleOpenDiffView,
    handleOpenFileView,
    handleCopyFilePath,
    handleCopyRelativePath,
    handleOpenInDefaultApp,
    handleOpenContainingFolder,
    handleExpandAllChildren,
    handleCollapseAllChildren,
    handleCloseTab,
    handleCloseOtherTabs,
    handleCloseAllTabs,
  ]);
};
