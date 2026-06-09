import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef } from "react";

import { panelsInZoneAtom } from "~/components/panels/atoms.ts";
import type { SectionSide } from "~/components/panels/PanelSection.tsx";
import { PanelSection } from "~/components/panels/PanelSection.tsx";
import { ResizeHandle } from "~/components/panels/ResizeHandle.tsx";
import { sectionSplitAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import type { ZoneId } from "~/components/panels/types.ts";
import { toSplitZone } from "~/components/panels/types.ts";

import styles from "./SplittableSection.module.scss";

// Neither sub-section may shrink below this fraction of the section.
const MIN_RATIO = 0.15;
const MAX_RATIO = 0.85;

type SplittableSectionProps = {
  /** The primary section zone (e.g. "center"); its split half is derived. */
  primaryZone: ZoneId;
  side: SectionSide;
};

/**
 * A section that can be split once into two sub-sections — stacked (axis
 * "horizontal") or side-by-side (axis "vertical"). When un-split it renders a
 * single PanelSection; when split it renders the primary PanelSection, a resize
 * handle, and a second PanelSection bound to the "<zone>:split" zone. Each
 * sub-section is a full PanelSection, so each gets its own tab strip and "+".
 */
export const SplittableSection = ({ primaryZone, side }: SplittableSectionProps): ReactElement => {
  const split = useAtomValue(sectionSplitAtom)[primaryZone];
  const setSectionSplit = useSetAtom(sectionSplitAtom);
  const splitZone = toSplitZone(primaryZone);
  const splitPanelCount = useAtomValue(panelsInZoneAtom(splitZone)).length;

  const containerRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLDivElement>(null);

  const isStacked = split?.axis === "horizontal";

  // Self-heal: if the split half loses its last panel through some path other
  // than closing its tab — e.g. the agent in it is deleted, or it is moved out
  // via another section's "+" — collapse the split so the primary reclaims the
  // space (a split half is never left sitting empty).
  useEffect(() => {
    if (split !== undefined && splitPanelCount === 0) {
      setSectionSplit((prev) => {
        const next = { ...prev };
        delete next[primaryZone];
        return next;
      });
    }
  }, [split, splitPanelCount, primaryZone, setSectionSplit]);

  const handleResize = useCallback(
    (nextPrimaryPx: number): void => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const dimension = isStacked ? rect.height : rect.width;
      if (dimension <= 0) return;
      const ratio = Math.max(MIN_RATIO, Math.min(MAX_RATIO, nextPrimaryPx / dimension));
      setSectionSplit((prev) => {
        const current = prev[primaryZone];
        if (!current) return prev;
        return { ...prev, [primaryZone]: { ...current, ratio } };
      });
    },
    [isStacked, primaryZone, setSectionSplit],
  );

  const getPrimarySize = useCallback((): number => {
    const rect = primaryRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    return isStacked ? rect.height : rect.width;
  }, [isStacked]);

  if (!split) {
    return <PanelSection zone={primaryZone} side={side} />;
  }

  const primaryBasis = `${split.ratio * 100}%`;

  return (
    <div ref={containerRef} className={isStacked ? styles.stacked : styles.sideBySide}>
      <div ref={primaryRef} className={styles.primaryPane} style={{ flexBasis: primaryBasis }}>
        <PanelSection zone={primaryZone} side={side} />
      </div>
      <ResizeHandle
        axis={isStacked ? "y" : "x"}
        getSize={getPrimarySize}
        onResize={handleResize}
        ariaLabel={`Resize ${side} split`}
      />
      <div className={styles.splitPane}>
        <PanelSection zone={splitZone} side={side} />
      </div>
    </div>
  );
};
