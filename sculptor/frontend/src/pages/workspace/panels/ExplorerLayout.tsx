import { useAtom } from "jotai";
import { FolderTree } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useState } from "react";

import { ElementIds } from "~/api";
import { ResizeHandle } from "~/components/sections/ResizeHandle.tsx";
import { explorerListWidthAtom } from "~/components/sections/sectionAtoms.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";

import styles from "./ExplorerLayout.module.scss";

type ExplorerLayoutProps = {
  /** The master list (file tree / changes browser / commit history). */
  list: ReactNode;
  /**
   * The detail (viewer) slot, always rendered. Receives the
   * sidebar-visibility toggle to place in its own header. The embedded
   * viewer owns its own empty state.
   */
  detail: (sidebarToggle: ReactElement) => ReactNode;
};

/**
 * Shared list-plus-viewer scaffold for the Files / Changes / Commits panels.
 * The list (sidebar) on the left is drag-resizable via the divider between the
 * panes; its width is a single persisted value (`explorerListWidthAtom`)
 * shared across the three panels and across workspaces, clamped in the atom.
 * The viewer on the right flexes to fill the rest, and the divider doubles as
 * the 1px visual separator between them. The sidebar-visibility toggle is
 * rendered into the viewer's header; the viewer is always visible.
 *
 * It takes the list and viewer as slots — there is no shared "active diff"
 * singleton, so each panel embeds its own instance with its own selection.
 */
export const ExplorerLayout = ({ list, detail }: ExplorerLayoutProps): ReactElement => {
  // Sidebar visibility is per-instance UI state (each panel can hide its own).
  const [isSidebarHidden, setIsSidebarHidden] = useState(false);

  const [listWidthPx, setListWidthPx] = useAtom(explorerListWidthAtom);

  const toggleSidebar = useCallback((): void => setIsSidebarHidden((hidden) => !hidden), []);

  // The sidebar toggle lives in the viewer header in both states: solid while
  // the sidebar is visible, dim while collapsed.
  const sidebarToggle = (
    <TooltipIconButton
      tooltipText={isSidebarHidden ? "Show sidebar" : "Hide sidebar"}
      onClick={toggleSidebar}
      data-testid={isSidebarHidden ? ElementIds.DIFF_HEADER_SHOW_TREE_BTN : ElementIds.FILE_BROWSER_HIDE_TREE_BTN}
    >
      <FolderTree size={14} className={isSidebarHidden ? styles.toggleOff : styles.toggleOn} />
    </TooltipIconButton>
  );

  const detailContent = detail(sidebarToggle);

  return (
    <div className={styles.row}>
      {!isSidebarHidden && (
        <>
          <div className={styles.list} style={{ width: listWidthPx }}>
            {list}
          </div>
          <ResizeHandle
            axis="x"
            direction={1}
            getSize={() => listWidthPx}
            onResize={setListWidthPx}
            ariaLabel="Resize file list"
          />
        </>
      )}
      <div className={styles.detail}>{detailContent}</div>
    </div>
  );
};
