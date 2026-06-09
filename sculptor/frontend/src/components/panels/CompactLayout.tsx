import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { CENTER_PANEL_MIN_WIDTH_PX, PANEL_MIN_PX } from "~/components/panels/constants.ts";
import { PanelDndProvider } from "~/components/panels/PanelDndProvider.tsx";
import { ResizeHandle } from "~/components/panels/ResizeHandle.tsx";
import {
  BOTTOM_ZONE,
  CENTER_SECTION_ZONE,
  LEFT_SECTION_ZONE,
  RIGHT_SECTION_ZONE,
  useSectionVisible,
} from "~/components/panels/sectionHooks.ts";
import {
  DEFAULT_SECTION_PERCENT,
  type SectionSizeKey,
  sectionSizePercentAtom,
} from "~/components/panels/sectionLayoutAtoms.ts";
import { SplittableSection } from "~/components/panels/SplittableSection.tsx";

import styles from "./CompactLayout.module.scss";

// Sides may shrink to this floor so the center keeps its minimum (REQ-PERSIST-3).
const SECTION_FLOOR_PX = 150;

/**
 * The uniform-panels workspace layout: four sections — Left, Center, Right,
 * Bottom — all rendered by the same PanelSection (REQ-PANEL-1). The Center is
 * always present (no top-bar toggle); Left / Right / Bottom collapse via their
 * toggles. Sizes are a global percentage of the screen, clamped so the center
 * can't shrink below its minimum (other sections give way) (REQ-PERSIST-2/3).
 */
export const CompactLayout = (): ReactElement => {
  const isLeftVisible = useSectionVisible(LEFT_SECTION_ZONE);
  const isRightVisible = useSectionVisible(RIGHT_SECTION_ZONE);
  const isBottomVisible = useSectionVisible(BOTTOM_ZONE);

  const sizes = useAtomValue(sectionSizePercentAtom);
  const setSizes = useSetAtom(sectionSizePercentAtom);

  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    observer.observe(el);
    return (): void => observer.disconnect();
  }, []);

  const { width, height } = size;
  const leftPct = sizes.left ?? DEFAULT_SECTION_PERCENT.left;
  const rightPct = sizes.right ?? DEFAULT_SECTION_PERCENT.right;
  const bottomPct = sizes.bottom ?? DEFAULT_SECTION_PERCENT.bottom;

  // Resolve side widths in px, then protect the center's minimum by shrinking
  // the right side first, then the left.
  const handleCount = (isLeftVisible ? 1 : 0) + (isRightVisible ? 1 : 0);
  let leftPx = isLeftVisible ? Math.max(SECTION_FLOOR_PX, Math.round((leftPct / 100) * width)) : 0;
  let rightPx = isRightVisible ? Math.max(SECTION_FLOOR_PX, Math.round((rightPct / 100) * width)) : 0;
  if (width > 0) {
    let deficit = leftPx + rightPx + CENTER_PANEL_MIN_WIDTH_PX + handleCount - width;
    if (deficit > 0 && isRightVisible) {
      const r = Math.min(deficit, rightPx - SECTION_FLOOR_PX);
      rightPx -= r;
      deficit -= r;
    }

    if (deficit > 0 && isLeftVisible) {
      const l = Math.min(deficit, leftPx - SECTION_FLOOR_PX);
      leftPx -= l;
    }
  }
  const bottomPx = isBottomVisible ? Math.max(PANEL_MIN_PX, Math.round((bottomPct / 100) * height)) : 0;

  const setPct = useCallback(
    (key: SectionSizeKey, px: number, dimension: number): void => {
      if (dimension <= 0) return;
      const pct = Math.max(5, Math.min(80, (px / dimension) * 100));
      setSizes((prev) => ({ ...prev, [key]: pct }));
    },
    [setSizes],
  );

  return (
    <PanelDndProvider>
      <div ref={containerRef} className={styles.outer}>
        <div className={styles.topRow}>
          {isLeftVisible && (
            <>
              <div className={styles.side} style={{ width: leftPx }}>
                <SplittableSection primaryZone={LEFT_SECTION_ZONE} side="left" />
              </div>
              <ResizeHandle
                axis="x"
                getSize={() => leftPx}
                onResize={(px) => setPct("left", px, width)}
                ariaLabel="Resize left section"
              />
            </>
          )}

          <div className={styles.center}>
            <SplittableSection primaryZone={CENTER_SECTION_ZONE} side="center" />
          </div>

          {isRightVisible && (
            <>
              <ResizeHandle
                axis="x"
                getSize={() => rightPx}
                onResize={(px) => setPct("right", px, width)}
                direction={-1}
                ariaLabel="Resize right section"
              />
              <div className={styles.side} style={{ width: rightPx }}>
                <SplittableSection primaryZone={RIGHT_SECTION_ZONE} side="right" />
              </div>
            </>
          )}
        </div>

        {isBottomVisible && (
          <>
            <ResizeHandle
              axis="y"
              getSize={() => bottomPx}
              onResize={(px) => setPct("bottom", px, height)}
              direction={-1}
              ariaLabel="Resize bottom section"
            />
            <div className={styles.bottom} style={{ height: bottomPx }}>
              <SplittableSection primaryZone={BOTTOM_ZONE} side="bottom" />
            </div>
          </>
        )}
      </div>
    </PanelDndProvider>
  );
};
