import { useDroppable } from "@dnd-kit/core";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { focusedZoneAtom, isDropTargetAtom, isZoneFocusedAtom, maximizedZoneAtom } from "~/components/panels/atoms.ts";
import { SectionBody } from "~/components/panels/SectionBody.tsx";
import { tabStripPositionAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import { SectionTabBar } from "~/components/panels/SectionTabBar.tsx";
import type { ZoneId } from "~/components/panels/types.ts";

import styles from "./PanelSection.module.scss";

export type SectionSide = "left" | "center" | "right" | "bottom";

type PanelSectionProps = {
  zone: ZoneId;
  side: SectionSide;
};

/**
 * One uniform panel section (Left / Center / Right / Bottom). Renders a single
 * tab strip — at the top or bottom per the global setting (REQ-SET-1) — a "+"
 * to add panels/agents/terminals not currently here, and the active panel's
 * content. A section never auto-collapses; it can sit open and empty showing
 * just "+" (REQ-SECTION-1..3).
 *
 * Deliberately thin: the strip (SectionTabBar) and content (SectionBody) are
 * memoized children behind primitive props, and this shell only subscribes to
 * narrow per-zone atoms. It still re-renders on dnd-kit `over` changes (its
 * useDroppable consumes the drag context), so everything here must stay cheap
 * — heavy state belongs in the children, behind their memo boundaries.
 */
const PanelSectionInner = ({ zone, side }: PanelSectionProps): ReactElement => {
  const tabStripPosition = useAtomValue(tabStripPositionAtom);
  // Highlight while a cross-section drag targets this zone.
  const isDropTarget = useAtomValue(isDropTargetAtom(zone));
  // Active-pane indicator: this section shows the (subtle) focus ring when it is
  // the focused zone. Focus is set only by deliberate actions — adding a panel,
  // dropping one via drag, or the pane-navigation hotkeys — never by a plain
  // click. Clicking a DIFFERENT (non-focused) pane instead dismisses the ring,
  // keeping it ephemeral; Escape clears it too (usePageLayoutKeyboardShortcuts).
  const isFocused = useAtomValue(isZoneFocusedAtom(zone));
  const setFocusedZone = useSetAtom(focusedZoneAtom);
  const maximizedZone = useAtomValue(maximizedZoneAtom);
  const isMaximized = maximizedZone === zone;

  // The whole section is a drop target for tab drags (its zone is the droppable
  // id). The PanelDndProvider's shared DndContext drives the move on drop.
  const { setNodeRef: setDroppableRef } = useDroppable({ id: zone });

  const tabBar = <SectionTabBar zone={zone} side={side} />;

  return (
    <div
      ref={setDroppableRef}
      className={`${styles.section} ${isFocused ? styles.focused : ""} ${isDropTarget ? styles.dropTarget : ""} ${isMaximized ? styles.maximized : ""}`}
      data-testid={`panel-section-${side}`}
      data-maximized={isMaximized ? "true" : undefined}
      // Clicking a non-focused pane dismisses the ring (clicking the focused
      // pane leaves it). Clicks never *add* the ring — only add/drop/hotkeys do.
      onPointerDown={() => {
        if (!isFocused) setFocusedZone(null);
      }}
    >
      {tabStripPosition === "top" && tabBar}
      <SectionBody zone={zone} />
      {tabStripPosition === "bottom" && tabBar}
    </div>
  );
};

export const PanelSection = memo(PanelSectionInner);
