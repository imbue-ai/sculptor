import { Flex, Text } from "@radix-ui/themes";
import { useAtom } from "jotai";
import { FileText, FolderTree } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { ResizeHandle } from "~/components/panels/ResizeHandle.tsx";
import { explorerListWidthAtom } from "~/components/sections/sectionAtoms.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";

import styles from "./ExplorerLayout.module.scss";

const MIN_LIST_PX = 200;
const MIN_DETAIL_PX = 280;
const HANDLE_PX = 1;

type ExplorerLayoutProps = {
  /** The master list (file tree / changes browser / commit history). */
  list: ReactNode;
  /**
   * The detail (viewer) slot, always rendered (FCC-06). Receives the
   * sidebar-visibility toggle to place in its own header (FCC-05). When the
   * embedded viewer renders its own empty state, ignore `hasSelection`; when it
   * does not, pass `emptyDetail` to have the layout render one.
   */
  detail: (sidebarToggle: ReactElement) => ReactNode;
  /** Whether the detail has something selected. Drives the layout-owned empty
   *  state when `emptyDetail` is provided (FCC-06). */
  hasSelection: boolean;
  /**
   * Optional layout-owned empty detail, rendered instead of `detail` when
   * `hasSelection` is false. Receives the sidebar toggle so the empty header
   * keeps the toggle reachable. Omit when the viewer renders its own empty
   * state.
   */
  emptyDetail?: (sidebarToggle: ReactElement) => ReactNode;
};

/**
 * Shared resizable list-plus-viewer scaffold for the Files / Changes / Commits
 * panels (FCC-04/05/06). The list (sidebar) on the left keeps a fixed pixel
 * width — the GLOBAL `explorerListWidthAtom`, shared across all three panels and
 * across workspaces — and the viewer on the right flexes to fill the rest. The
 * divider resizes the list (min 200px list / min 280px viewer). The
 * sidebar-visibility toggle is rendered into the viewer's header (FCC-05); the
 * viewer is always visible (FCC-06).
 *
 * It takes the list and viewer as slots and the selection as a prop — there is
 * no shared "active diff" singleton, so each panel embeds its own instance with
 * its own selection.
 */
export const ExplorerLayout = ({ list, detail, hasSelection, emptyDetail }: ExplorerLayoutProps): ReactElement => {
  // Width persists globally (shared across the three panels and all workspaces).
  const [listWidth, setListWidth] = useAtom(explorerListWidthAtom);
  // Sidebar visibility is per-instance UI state (each panel can hide its own).
  const [isSidebarHidden, setIsSidebarHidden] = useState(false);

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

  const maxList = Math.max(MIN_LIST_PX, containerWidth - MIN_DETAIL_PX - HANDLE_PX);
  const clampedListWidth = Math.min(Math.max(listWidth, MIN_LIST_PX), maxList);

  const getListSize = useCallback(() => clampedListWidth, [clampedListWidth]);
  const onResizeList = useCallback(
    (nextPx: number): void => {
      if (containerWidth <= 0) return;
      const clamped = Math.min(
        Math.max(nextPx, MIN_LIST_PX),
        Math.max(MIN_LIST_PX, containerWidth - MIN_DETAIL_PX - HANDLE_PX),
      );
      setListWidth(clamped);
    },
    [containerWidth, setListWidth],
  );

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

  const detailContent = !hasSelection && emptyDetail ? emptyDetail(sidebarToggle) : detail(sidebarToggle);

  return (
    <div ref={containerRef} className={styles.row}>
      {!isSidebarHidden && (
        <>
          <div className={styles.list} style={{ width: clampedListWidth }}>
            {list}
          </div>
          <ResizeHandle axis="x" getSize={getListSize} onResize={onResizeList} ariaLabel="Resize sidebar" />
        </>
      )}
      <div className={styles.detail}>{detailContent}</div>
    </div>
  );
};

/**
 * The placeholder header + body for an empty viewer (FCC-06), kept here so a
 * panel that does not delegate its empty state to the embedded viewer can reuse
 * the same look. It keeps the sidebar toggle in the header so the sidebar stays
 * toggleable with nothing selected.
 */
export const EmptyDetail = ({ sidebarToggle }: { sidebarToggle: ReactElement }): ReactElement => {
  return (
    <Flex direction="column" height="100%" width="100%">
      <Flex align="center" gap="2" className={styles.emptyHeader}>
        {sidebarToggle}
        <Text size="1" color="gray" className={styles.emptyHeaderLabel}>
          No file selected
        </Text>
        <span className={styles.emptyHeaderSpacer} />
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
