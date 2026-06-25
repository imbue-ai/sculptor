// The four-section frame. Owns the geometry: reads the global section sizes and the
// per-section expanded flags, resolves percentages to pixels (protecting the
// center's larger minimum by shrinking the sides first), renders only expanded
// sections, and short-circuits to a single full-bleed section when one is maximized.
// Its SplittableSection children are memoized with primitive props so a
// per-pointer-move resize does not cascade into them.

import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";

import { CollapsedSectionDropRail } from "./CollapsedSectionDropRail.tsx";
import { PanelSection } from "./PanelSection.tsx";
import { ResizeHandle } from "./ResizeHandle.tsx";
import { isSectionExpandedAtom, sectionSizesAtom, setSectionSizeAtom } from "./sectionAtoms.ts";
import { resolveSectionPixelSizes, sizeToPercent } from "./sectionGeometry.ts";
import styles from "./SectionGrid.module.scss";
import { primaryOf } from "./sectionTypes.ts";
import { SplittableSection } from "./SplittableSection.tsx";
import { draggedPanelIdAtom, maximizedSectionAtom } from "./transientAtoms.ts";

export const SectionGrid = (): ReactElement => {
  const sizes = useAtomValue(sectionSizesAtom);
  const isLeftExpanded = useAtomValue(isSectionExpandedAtom("left"));
  const isRightExpanded = useAtomValue(isSectionExpandedAtom("right"));
  const isBottomExpanded = useAtomValue(isSectionExpandedAtom("bottom"));
  const maximizedSection = useAtomValue(maximizedSectionAtom);
  // A drag is in progress (stable for the whole drag, so this re-renders the grid only
  // on drag start/end) — used to surface drop rails for the collapsed sections.
  const isDragging = useAtomValue(draggedPanelIdAtom) !== null;
  const setSectionSize = useSetAtom(setSectionSizeAtom);

  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = containerRef.current;
    if (element === null) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect !== undefined) {
        setContainerSize({ width: rect.width, height: rect.height });
      }
    });
    observer.observe(element);
    return (): void => observer.disconnect();
  }, []);

  const { width, height } = containerSize;
  const { leftPx, rightPx, bottomPx } = resolveSectionPixelSizes({
    containerWidth: width,
    containerHeight: height,
    sizes,
    isLeftExpanded,
    isRightExpanded,
    isBottomExpanded,
  });

  const resizeSide = useCallback(
    (side: "left" | "right" | "bottom", px: number, dimension: number): void => {
      setSectionSize({ side, percent: sizeToPercent(px, dimension) });
    },
    [setSectionSize],
  );

  if (maximizedSection !== null) {
    // A maximized section shows only ONE sub-section — the primary — so a
    // split section maximizes to its primary half rather than rendering both panes
    // (which, both flagged maximized, would overlap).
    return (
      <div ref={containerRef} className={styles.maximized}>
        <PanelSection subSection={primaryOf(maximizedSection)} />
      </div>
    );
  }

  return (
    <div ref={containerRef} className={styles.outer}>
      <div className={styles.topRow}>
        {/* Collapsed left section: a drop rail at the left edge while dragging. */}
        {isDragging && !isLeftExpanded && <CollapsedSectionDropRail section="left" orientation="vertical" />}
        {isLeftExpanded && (
          <>
            <div className={styles.side} style={{ width: leftPx }} data-testid={ElementIds.SECTION_LEFT}>
              <SplittableSection section="left" />
            </div>
            <ResizeHandle
              axis="x"
              getSize={() => leftPx}
              onResize={(px) => resizeSide("left", px, width)}
              ariaLabel="Resize left section"
              data-testid={`${ElementIds.SECTION_RESIZE_HANDLE}-left`}
            />
          </>
        )}

        <div className={styles.center} data-testid={ElementIds.SECTION_CENTER}>
          <SplittableSection section="center" />
        </div>

        {isRightExpanded && (
          <>
            <ResizeHandle
              axis="x"
              getSize={() => rightPx}
              onResize={(px) => resizeSide("right", px, width)}
              direction={-1}
              ariaLabel="Resize right section"
              data-testid={`${ElementIds.SECTION_RESIZE_HANDLE}-right`}
            />
            <div className={styles.side} style={{ width: rightPx }} data-testid={ElementIds.SECTION_RIGHT}>
              <SplittableSection section="right" />
            </div>
          </>
        )}
        {/* Collapsed right section: a drop rail at the right edge while dragging. */}
        {isDragging && !isRightExpanded && <CollapsedSectionDropRail section="right" orientation="vertical" />}
      </div>

      {isBottomExpanded && (
        <>
          <ResizeHandle
            axis="y"
            getSize={() => bottomPx}
            onResize={(px) => resizeSide("bottom", px, height)}
            direction={-1}
            ariaLabel="Resize bottom section"
            data-testid={`${ElementIds.SECTION_RESIZE_HANDLE}-bottom`}
          />
          <div className={styles.bottom} style={{ height: bottomPx }} data-testid={ElementIds.SECTION_BOTTOM}>
            <SplittableSection section="bottom" />
          </div>
        </>
      )}
      {/* Collapsed bottom section: a drop rail along the bottom edge while dragging. */}
      {isDragging && !isBottomExpanded && <CollapsedSectionDropRail section="bottom" orientation="horizontal" />}
    </div>
  );
};
