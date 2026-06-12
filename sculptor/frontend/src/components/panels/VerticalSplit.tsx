import type { ReactElement } from "react";

import { ResizeHandle } from "~/components/panels/ResizeHandle";
import type { ZoneId } from "~/components/panels/types.ts";
import { ZoneContent } from "~/components/panels/ZoneContent";

import styles from "./DockingLayout.module.scss";

type VerticalSplitProps = {
  topZoneId: ZoneId;
  bottomZoneId: ZoneId;
  isTopVisible: boolean;
  isBottomVisible: boolean;
  bottomPx: number;
  getBottomSize: () => number;
  onBottomResize: (px: number) => void;
  topTestId?: string;
  bottomTestId?: string;
  handleTestId?: string;
  handleAriaLabel?: string;
};

/** Top zone fills, bottom zone has an explicit pixel height, and a drag
 *  handle between them when both zones are visible. */
export const VerticalSplit = ({
  topZoneId,
  bottomZoneId,
  isTopVisible,
  isBottomVisible,
  bottomPx,
  getBottomSize,
  onBottomResize,
  topTestId,
  bottomTestId,
  handleTestId,
  handleAriaLabel,
}: VerticalSplitProps): ReactElement => (
  <>
    {isTopVisible && (
      <div className={styles.innerTop} data-testid={topTestId}>
        <ZoneContent zoneId={topZoneId} />
      </div>
    )}
    {isTopVisible && isBottomVisible && (
      <ResizeHandle
        axis="y"
        getSize={getBottomSize}
        onResize={onBottomResize}
        direction={-1}
        ariaLabel={handleAriaLabel}
        data-testid={handleTestId}
      />
    )}
    {isBottomVisible && (
      <div
        // When the top zone is also visible, this zone has an explicit
        // pixel height that the resize handle drives. When it's the only
        // visible zone in the column, the explicit height becomes wrong:
        // the column is taller than `bottomPx` (default 200), so the
        // panel sits cropped at the top and leaves the column empty
        // below it. Reuse the top-zone fill class in that case so it
        // grows to fill the column.
        className={isTopVisible ? styles.innerBottom : styles.innerTop}
        style={isTopVisible ? { height: bottomPx } : undefined}
        data-testid={bottomTestId}
      >
        <ZoneContent zoneId={bottomZoneId} />
      </div>
    )}
  </>
);
