import { useAtom } from "jotai";
import { FolderTree } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import {
  EXPLORER_LIST_MAX_WIDTH_PX,
  EXPLORER_LIST_MIN_WIDTH_PX,
  explorerListWidthAtom,
} from "~/pages/workspace/layout/atoms/section.ts";
import { ResizeHandle } from "~/pages/workspace/layout/ResizeHandle.tsx";

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
  const listRef = useRef<HTMLDivElement | null>(null);

  // Drags start from the RENDERED width, not the stored one: in a narrow host
  // section the stylesheet caps the pane below the shared width, and starting
  // the drag math from the (larger) stored value would make the divider feel
  // dead until the pointer traveled the phantom difference. Falls back to the
  // stored width where layout isn't measured (jsdom reports offsetWidth 0).
  const getRenderedListWidth = useCallback((): number => {
    const measured = listRef.current?.offsetWidth;
    return measured ? measured : listWidthPx;
  }, [listWidthPx]);

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
          <div ref={listRef} className={styles.list} style={{ width: listWidthPx }}>
            {list}
          </div>
          <ResizeHandle
            axis="x"
            direction={1}
            getSize={getRenderedListWidth}
            onResize={setListWidthPx}
            ariaLabel="Resize file list"
            ariaValueNow={Math.round(listWidthPx)}
            ariaValueMin={EXPLORER_LIST_MIN_WIDTH_PX}
            ariaValueMax={EXPLORER_LIST_MAX_WIDTH_PX}
          />
        </>
      )}
      <div className={styles.detail}>{detailContent}</div>
    </div>
  );
};
