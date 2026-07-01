import { FolderTree } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useState } from "react";

import { ElementIds } from "~/api";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";

import styles from "./ExplorerLayout.module.scss";

// The list (sidebar) is a fixed width — it is not user-resizable, so the pane
// stays the same size across the Files / Changes / Commits panels and across
// workspaces. The viewer flexes to fill the remaining space.
const LIST_WIDTH_PX = 240;

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
 * The list (sidebar) on the left is a fixed pixel width and the viewer on the
 * right flexes to fill the rest. A single 1px divider separates them (the
 * list's right border); the sidebar cannot be dragged to a new size. The
 * sidebar-visibility toggle is rendered into the viewer's header; the viewer is
 * always visible.
 *
 * It takes the list and viewer as slots — there is no shared "active diff"
 * singleton, so each panel embeds its own instance with its own selection.
 */
export const ExplorerLayout = ({ list, detail }: ExplorerLayoutProps): ReactElement => {
  // Sidebar visibility is per-instance UI state (each panel can hide its own).
  const [isSidebarHidden, setIsSidebarHidden] = useState(false);

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
        <div className={styles.list} style={{ width: LIST_WIDTH_PX }}>
          {list}
        </div>
      )}
      <div className={styles.detail}>{detailContent}</div>
    </div>
  );
};
