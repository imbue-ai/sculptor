// One section, rendered either as a single PanelSection or, when split, as primary +
// resize handle + secondary. Memoized behind primitive props so SectionGrid's
// per-pointer-move resize re-renders stop at this boundary, and it subscribes only
// to THIS section's split slice so a split-ratio drag elsewhere never re-renders it.
//
// A horizontal divider stacks the halves top/bottom (ResizeHandle axis "y"); a
// vertical divider places them side-by-side (axis "x"). The primary half carries an
// explicit flex-basis from the ratio (clamped to SPLIT_RATIO_MIN/MAX) and the
// secondary fills the rest. Splits persist when a half empties (the empty half
// renders its empty state); only the explicit close-split action merges — this
// component just reflects the resulting split slice.

import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo, useCallback, useRef } from "react";

import { ElementIds } from "~/api";

import { PanelSection } from "./PanelSection.tsx";
import { ResizeHandle } from "./ResizeHandle.tsx";
import { setSplitRatioAtom, SPLIT_RATIO_MAX, SPLIT_RATIO_MIN } from "./sectionActions.ts";
import { sectionSplitForSectionAtom } from "./sectionAtoms.ts";
import type { SectionId } from "./sectionTypes.ts";
import { primaryOf, toSecondary } from "./sectionTypes.ts";
import styles from "./SplittableSection.module.scss";

type SplittableSectionProps = { section: SectionId };

const SplittableSectionComponent = ({ section }: SplittableSectionProps): ReactElement => {
  const split = useAtomValue(sectionSplitForSectionAtom(section));
  const setSplitRatio = useSetAtom(setSplitRatioAtom);

  const containerRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLDivElement>(null);

  const isStacked = split?.axis === "horizontal";

  const handleResize = useCallback(
    (nextPrimaryPx: number): void => {
      const container = containerRef.current;
      if (container === null) {
        return;
      }
      const rect = container.getBoundingClientRect();
      const dimension = isStacked ? rect.height : rect.width;
      if (dimension <= 0) {
        return;
      }
      const ratio = Math.max(SPLIT_RATIO_MIN, Math.min(SPLIT_RATIO_MAX, nextPrimaryPx / dimension));
      setSplitRatio({ section, ratio });
    },
    [isStacked, section, setSplitRatio],
  );

  const getPrimarySize = useCallback((): number => {
    const rect = primaryRef.current?.getBoundingClientRect();
    if (rect === undefined) {
      return 0;
    }
    return isStacked ? rect.height : rect.width;
  }, [isStacked]);

  if (split === undefined) {
    return <PanelSection subSection={primaryOf(section)} />;
  }

  const primaryBasis = `${split.ratio * 100}%`;

  return (
    <div
      ref={containerRef}
      className={isStacked ? styles.stacked : styles.sideBySide}
      data-testid={`${ElementIds.SECTION_SPLIT_SUBSECTION}-${section}`}
    >
      <div ref={primaryRef} className={styles.primaryPane} style={{ flexBasis: primaryBasis }}>
        <PanelSection subSection={primaryOf(section)} />
      </div>
      <ResizeHandle
        axis={isStacked ? "y" : "x"}
        getSize={getPrimarySize}
        onResize={handleResize}
        ariaLabel={`Resize ${section} split`}
        data-testid={`${ElementIds.SECTION_RESIZE_HANDLE}-${toSecondary(section)}`}
      />
      <div className={styles.splitPane}>
        <PanelSection subSection={toSecondary(section)} />
      </div>
    </div>
  );
};

export const SplittableSection = memo(SplittableSectionComponent);
