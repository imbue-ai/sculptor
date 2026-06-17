import { Flex, Text } from "@radix-ui/themes";
import { useAtom, useAtomValue } from "jotai";
import { FileText, FolderTree, RefreshCw } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { invalidateWorkspaceGitQueries } from "~/common/queryClient.ts";
import { ResizeHandle } from "~/components/panels/ResizeHandle.tsx";
import {
  MASTER_DETAIL_MIN_LIST_PX,
  masterDetailListWidthAtomFamily,
  masterDetailTreeHiddenAtomFamily,
} from "~/components/panels/sectionLayoutAtoms.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { diffPanelStateAtomFamily } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { DiffPanel } from "~/pages/workspace/components/diffPanel/DiffPanel.tsx";

import styles from "./MasterDetailPanel.module.scss";
import type { MasterDetailHeaderConfig } from "./MasterDetailTreeHeader.tsx";
import { MasterDetailTreeHeader, TreeOptionsItems, TreeOptionsMenu } from "./MasterDetailTreeHeader.tsx";

const MIN_DETAIL_PX = 280;
const HANDLE_PX = 1;
const REFRESH_SPIN_MS = 700;

type MasterDetailPanelProps = {
  workspaceId: string;
  /** The per-(workspace, panel) diff-state key — also the per-workspace
   *  persistence key for the tree-collapsed state. */
  stateKey: string;
  /** Stable panel scope ("files" / "changes" / "commits"). The tree width is
   *  persisted by this, so it carries across workspaces while each panel keeps
   *  its own value. */
  scope: string;
  /** Tree-side header config (search, view-mode toggle, collapse-all). */
  header: MasterDetailHeaderConfig;
  /** The master list (file tree / changes / commits). */
  children: ReactNode;
};

/**
 * Side-by-side master-detail layout shared by the Files / Changes / Commits
 * panels (REQ-DIFF-1/2/3). The tree (list) on the left keeps a FIXED pixel width
 * and the selected file's diff (detail) on the right flexes to absorb panel
 * resizes; the user can still drag the divider to resize the tree.
 *
 * The tree side carries only the search box; the controls live in the diff
 * header: the folder-tree toggle sits to the left of the breadcrumb (solid when
 * the tree is shown, dim when collapsed), and the tree view-options are merged
 * into the diff "…" menu.
 */
export const MasterDetailPanel = ({
  workspaceId,
  stateKey,
  scope,
  header,
  children,
}: MasterDetailPanelProps): ReactElement => {
  const diffState = useAtomValue(diffPanelStateAtomFamily(stateKey));
  // Width persists by panel scope (global across workspaces); collapsed state
  // stays per-workspace via stateKey.
  const [listWidth, setListWidth] = useAtom(masterDetailListWidthAtomFamily(scope));
  const [isTreeHidden, setTreeHidden] = useAtom(masterDetailTreeHiddenAtomFamily(stateKey));

  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  // Measure synchronously on mount (pre-paint) so the first painted frame sizes
  // the panes correctly instead of flashing from containerWidth=0.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    setContainerWidth(el.offsetWidth);
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setContainerWidth(rect.width);
    });
    observer.observe(el);
    return (): void => observer.disconnect();
  }, []);

  const hasDetail = diffState.activeTabPath != null;

  // The detail (diff/file viewer) is ALWAYS rendered — it is never hidden, with
  // or without a file open (it shows a placeholder when empty). The tree is shown
  // unless the user collapses it with the toggle; when the panel is too small to
  // fit both comfortably, the viewer flexes down rather than dropping out, and
  // the user can collapse the tree (the toggle) to reclaim its space.
  const maxList = Math.max(MASTER_DETAIL_MIN_LIST_PX, containerWidth - MIN_DETAIL_PX - HANDLE_PX);
  const clampedListWidth = Math.min(Math.max(listWidth, MASTER_DETAIL_MIN_LIST_PX), maxList);

  const getListSize = useCallback(() => clampedListWidth, [clampedListWidth]);
  const onResizeList = useCallback(
    (nextPx: number): void => {
      if (containerWidth <= 0) return;
      const clamped = Math.min(
        Math.max(nextPx, MASTER_DETAIL_MIN_LIST_PX),
        Math.max(MASTER_DETAIL_MIN_LIST_PX, containerWidth - MIN_DETAIL_PX - HANDLE_PX),
      );
      setListWidth(clamped);
    },
    [containerWidth, setListWidth],
  );

  const toggleTree = useCallback((): void => setTreeHidden((hidden) => !hidden), [setTreeHidden]);

  // Brief one-shot spin so the refresh click registers even when the refetch
  // returns instantly.
  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleRefresh = useCallback((): void => {
    invalidateWorkspaceGitQueries(workspaceId);
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), REFRESH_SPIN_MS);
  }, [workspaceId]);

  // The tree toggle lives at the left of the diff header in both states: solid
  // white while the tree is visible, dim while collapsed (REQ polish).
  const treeToggle = (
    <TooltipIconButton
      tooltipText={isTreeHidden ? "Show file tree" : "Hide file tree"}
      onClick={toggleTree}
      data-testid={isTreeHidden ? ElementIds.DIFF_HEADER_SHOW_TREE_BTN : ElementIds.FILE_BROWSER_HIDE_TREE_BTN}
    >
      <FolderTree size={14} className={isTreeHidden ? styles.toggleOff : styles.toggleOn} />
    </TooltipIconButton>
  );

  const refreshButton = (
    <TooltipIconButton tooltipText="Refresh" onClick={handleRefresh} data-testid={ElementIds.FILE_BROWSER_REFRESH_BTN}>
      <RefreshCw size={14} className={isRefreshing ? styles.refreshSpinning : undefined} />
    </TooltipIconButton>
  );

  const treeOptions = {
    viewMode: header.viewMode,
    onToggleViewMode: header.onToggleViewMode,
    onCollapseAll: header.onCollapseAll,
    collapseLabel: header.collapseLabel,
  };

  return (
    <div ref={containerRef} className={styles.row}>
      {!isTreeHidden && (
        <>
          <div className={styles.list} style={{ width: clampedListWidth }}>
            {header.hasSearch && <MasterDetailTreeHeader workspaceId={workspaceId} />}
            {children}
          </div>
          <ResizeHandle axis="x" getSize={getListSize} onResize={onResizeList} ariaLabel="Resize file tree" />
        </>
      )}
      <div className={styles.detail}>
        {hasDetail ? (
          <DiffPanel
            workspaceId={workspaceId}
            stateKey={stateKey}
            singleFile
            headerLeading={treeToggle}
            headerActions={refreshButton}
            headerMenuItems={<TreeOptionsItems {...treeOptions} />}
          />
        ) : (
          <EmptyDetail toggle={treeToggle} refresh={refreshButton} menu={<TreeOptionsMenu {...treeOptions} />} />
        )}
      </div>
    </div>
  );
};

/** Placeholder shown in the detail pane when no file/diff is selected. It keeps
 *  the same control header as the diff viewer (toggle + refresh + "…") so the
 *  tree stays toggleable and the options stay reachable with no file open. */
const EmptyDetail = ({
  toggle,
  refresh,
  menu,
}: {
  toggle: ReactNode;
  refresh: ReactNode;
  menu: ReactNode;
}): ReactElement => {
  return (
    <Flex direction="column" height="100%" width="100%">
      <Flex align="center" gap="2" className={styles.emptyHeader}>
        {toggle}
        <Text size="1" color="gray" className={styles.emptyHeaderLabel}>
          No file selected
        </Text>
        <span className={styles.emptyHeaderSpacer} />
        {refresh}
        {menu}
      </Flex>
      <Flex className={styles.emptyDetail} direction="column" align="center" justify="center" gap="3" p="4">
        <FileText size={28} strokeWidth={1.5} />
        <Text size="2" color="gray">
          Select a file to view its contents
        </Text>
      </Flex>
    </Flex>
  );
};
