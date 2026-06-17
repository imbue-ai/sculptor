import { useDroppable } from "@dnd-kit/core";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import {
  isDropTargetAtom,
  isZoneFocusedAtom,
  isZoneRingVisibleAtom,
  maximizedZoneAtom,
  selectZoneAtom,
} from "~/components/panels/atoms.ts";
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
  // Active-pane indicator. `isFocused` is the persisted LOGICAL focus — "where
  // I'm working". It is recorded by clicking into a pane (silently, below), by
  // pane-navigation hotkeys, and by adding/dropping a panel; it persists so
  // returning to the workspace can flash the ring there. `isRingVisible` is the
  // TRANSIENT visual ring: it pulses on a deliberate jump (or workspace entry)
  // and fades after FOCUS_RING_VISIBLE_MS (useFocusRingFade) — a plain click sets
  // focus without flashing it, so the ring stays wayfinding, not steady chrome.
  const isFocused = useAtomValue(isZoneFocusedAtom(zone));
  const isRingVisible = useAtomValue(isZoneRingVisibleAtom(zone));
  const selectZone = useSetAtom(selectZoneAtom);
  const maximizedZone = useAtomValue(maximizedZoneAtom);
  const isMaximized = maximizedZone === zone;

  // The whole section is a drop target for tab drags (its zone is the droppable
  // id). The PanelDndProvider's shared DndContext drives the move on drop.
  const { setNodeRef: setDroppableRef } = useDroppable({ id: zone });

  const tabBar = <SectionTabBar zone={zone} side={side} />;

  return (
    <div
      ref={setDroppableRef}
      className={`${styles.section} ${isFocused ? styles.focused : ""} ${isRingVisible ? styles.ringVisible : ""} ${isDropTarget ? styles.dropTarget : ""} ${isMaximized ? styles.maximized : ""}`}
      data-testid={`panel-section-${side}`}
      data-maximized={isMaximized ? "true" : undefined}
      // Clicking a non-focused pane records it as the focused pane (silently —
      // no ring flash; clicking the already-focused pane is a no-op). The ring
      // is only *flashed* by deliberate jumps (add/drop/hotkeys) and workspace
      // entry, never by a plain click.
      onPointerDown={() => {
        if (!isFocused) selectZone(zone);
      }}
    >
      {tabStripPosition === "top" && tabBar}
      <SectionBody zone={zone} />
      {tabStripPosition === "bottom" && tabBar}
    </div>
  );
};

export const PanelSection = memo(PanelSectionInner);
