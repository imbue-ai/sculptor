import { useAtom, useAtomValue } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ResizeHandle } from "~/components/panels/ResizeHandle.tsx";
import { masterDetailDetailPercentAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import { diffPanelStateAtomFamily } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { DiffPanel } from "~/pages/workspace/components/diffPanel/DiffPanel.tsx";

import styles from "./MasterDetailPanel.module.scss";

const MIN_LIST_PX = 140;
const MIN_DETAIL_PX = 280;
const HANDLE_PX = 1;

type MasterDetailPanelProps = {
  workspaceId: string;
  /** The per-panel diff scope key — this panel's own selected-file state. */
  stateKey: string;
  /** The master list (file tree / changes / commits). */
  children: ReactNode;
};

/**
 * Side-by-side master-detail layout shared by the Files / Changes / Commits
 * panels (REQ-DIFF-1/2/3): the list on the left, the selected file's diff on the
 * right, with a resizable divider. The detail shows only when this panel's own
 * scope has a selected file, and one file is shown at a time.
 */
export const MasterDetailPanel = ({ workspaceId, stateKey, children }: MasterDetailPanelProps): ReactElement => {
  const diffState = useAtomValue(diffPanelStateAtomFamily(stateKey));
  const [detailPercent, setDetailPercent] = useAtom(masterDetailDetailPercentAtom);

  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setContainerWidth(rect.width);
    });
    observer.observe(el);
    return (): void => observer.disconnect();
  }, []);

  const hasDetail = diffState.activeTabPath != null;

  const maxDetail = Math.max(MIN_DETAIL_PX, containerWidth - MIN_LIST_PX - HANDLE_PX);
  const desiredDetail = containerWidth > 0 ? Math.round((detailPercent / 100) * containerWidth) : 0;
  const detailWidth = Math.min(Math.max(desiredDetail, MIN_DETAIL_PX), maxDetail);

  const getDetailSize = useCallback(() => detailWidth, [detailWidth]);
  const onResizeDetail = useCallback(
    (nextPx: number): void => {
      if (containerWidth <= 0) return;
      const clamped = Math.min(
        Math.max(nextPx, MIN_DETAIL_PX),
        Math.max(MIN_DETAIL_PX, containerWidth - MIN_LIST_PX - HANDLE_PX),
      );
      setDetailPercent((clamped / containerWidth) * 100);
    },
    [containerWidth, setDetailPercent],
  );

  return (
    <div ref={containerRef} className={styles.row}>
      <div className={styles.list}>{children}</div>
      {hasDetail && (
        <>
          <ResizeHandle
            axis="x"
            getSize={getDetailSize}
            onResize={onResizeDetail}
            direction={-1}
            ariaLabel="Resize file viewer"
          />
          <div className={styles.detail} style={{ width: detailWidth }}>
            <DiffPanel workspaceId={workspaceId} stateKey={stateKey} singleFile />
          </div>
        </>
      )}
    </div>
  );
};
