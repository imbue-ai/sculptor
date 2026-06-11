import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo, useCallback, useEffect, useRef } from "react";

import { panelsInZoneAtom } from "~/components/panels/atoms.ts";
import type { SectionSide } from "~/components/panels/PanelSection.tsx";
import { PanelSection } from "~/components/panels/PanelSection.tsx";
import { ResizeHandle } from "~/components/panels/ResizeHandle.tsx";
import { sectionSplitAtom, sectionSplitForZoneAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import type { ZoneId } from "~/components/panels/types.ts";
import { toSplitZone } from "~/components/panels/types.ts";
import { hasPendingSplitPanelAtom } from "~/pages/workspace/panels/panelDerivedAtoms.ts";

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
const SplittableSectionInner = ({ primaryZone, side }: SplittableSectionProps): ReactElement => {
  // Per-zone slice: a split-ratio drag elsewhere must not re-render this section.
  const split = useAtomValue(sectionSplitForZoneAtom(primaryZone));
  const setSectionSplit = useSetAtom(sectionSplitAtom);
  const splitZone = toSplitZone(primaryZone);
  const splitPanelCount = useAtomValue(panelsInZoneAtom(splitZone)).length;
  // Boolean atom over assignments + the streaming task/terminal lists, so this
  // section doesn't re-render on every task update — only when the answer flips.
  // See panelDerivedAtoms.ts for why the pending window must not collapse the split.
  const hasPendingSplitPanel = useAtomValue(hasPendingSplitPanelAtom(primaryZone));

  const containerRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLDivElement>(null);

  const isStacked = split?.axis === "horizontal";

  // Self-heal: collapse the split when its SECONDARY half loses its last panel
  // through some path other than closing its tab (e.g. the agent in it is
  // deleted, or it is dragged/moved out). The primary then reclaims the space.
  // We only watch the secondary half: an empty PRIMARY half is a valid state (a
  // section split while it had a single tab leaves the primary empty by design),
  // and primary emptying via removal is collapsed at the mutation site instead.
  // The pending-panel guard makes this race-safe on reload (see above).
  useEffect(() => {
    if (split === undefined || splitPanelCount > 0 || hasPendingSplitPanel) return;
    setSectionSplit((prev) => {
      const next = { ...prev };
      delete next[primaryZone];
      return next;
    });
  }, [split, splitPanelCount, hasPendingSplitPanel, primaryZone, setSectionSplit]);

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

// Memoized with primitive props so CompactLayout's per-pointer-move re-renders
// during section resizes stop at this boundary.
export const SplittableSection = memo(SplittableSectionInner);
