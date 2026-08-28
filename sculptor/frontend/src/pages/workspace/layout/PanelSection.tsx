// One uniform section (left / center / right / bottom, or a split half). Renders a
// single SectionHeader (tabs + add + maximize) and the SectionBody. Deliberately
// thin: it subscribes only to narrow per-sub-section flags and to the maximized
// section, while the heavy state lives behind its memoized children. During a drag it
// re-renders only when its own isDropTargetAtom slice flips (the section the cursor is
// over), so a pointer move elsewhere never reaches it.
//
// A plain click sets this section active silently (no ring flash) — the ring is only
// pulsed by deliberate jumps. The active-section ring is drawn as a CSS
// overlay gated on isRingVisible; the maximized styling hook flips when this section
// is the maximized one.

import { useDroppable } from "@dnd-kit/core";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { ElementIds } from "~/api";
import { isActiveSubSectionAtom } from "~/pages/workspace/layout/atoms/section.ts";
import { setActiveSectionAtom } from "~/pages/workspace/layout/atoms/sectionActions.ts";
import {
  isDropTargetAtom,
  isMaximizedSectionAtom,
  isRingVisibleAtom,
} from "~/pages/workspace/layout/atoms/transient.ts";
import type { SubSectionId } from "~/pages/workspace/layout/types/section.ts";
import { toSection } from "~/pages/workspace/layout/types/section.ts";
import { sectionBodyDroppableId } from "~/pages/workspace/layout/utils/panelDnd.ts";

import styles from "./PanelSection.module.scss";
import { SectionBody } from "./SectionBody.tsx";
import { SectionHeader } from "./SectionHeader.tsx";

type PanelSectionProps = { subSection: SubSectionId };

const PanelSectionComponent = ({ subSection }: PanelSectionProps): ReactElement => {
  const isDropTarget = useAtomValue(isDropTargetAtom(subSection));
  const isActive = useAtomValue(isActiveSubSectionAtom(subSection));
  const isRingVisible = useAtomValue(isRingVisibleAtom(subSection));
  const isMaximized = useAtomValue(isMaximizedSectionAtom(toSection(subSection)));
  const setActiveSection = useSetAtom(setActiveSectionAtom);

  // This section's body is a drop target keyed by its sub-section id; the drop-target
  // highlight is driven by the narrow isDropTargetAtom slice above, not dnd's isOver.
  const { setNodeRef } = useDroppable({
    id: sectionBodyDroppableId(subSection),
    data: { kind: "section-body", subSection },
  });

  const className = [
    styles.section,
    isActive ? styles.active : "",
    isRingVisible ? styles.ringVisible : "",
    isDropTarget ? styles.dropTarget : "",
    isMaximized ? styles.maximized : "",
  ]
    .filter(Boolean)
    .join(" ");

  const handlePointerDown = (): void => {
    if (!isActive) {
      setActiveSection({ subSection });
    }
  };

  return (
    <div
      ref={setNodeRef}
      className={className}
      data-testid={`${ElementIds.SECTION_ACTIVE_RING}-${subSection}`}
      data-maximized={isMaximized ? "true" : undefined}
      // The dnd-kit drop target is keyed by subSection; the drop-target styling hook
      // (.dropTarget) is driven by the isDropTargetAtom slice, not dnd's own isOver.
      data-drop-target-subsection={subSection}
      data-drop-active={isDropTarget ? "true" : undefined}
      // Behavioral hooks for the active-section ring: which section is the
      // logical active one, and whether its transient ring is currently visible.
      data-active={isActive ? "true" : undefined}
      data-ring-visible={isRingVisible ? "true" : undefined}
      onPointerDown={handlePointerDown}
    >
      <SectionHeader subSection={subSection} />
      <SectionBody subSection={subSection} />
    </div>
  );
};

export const PanelSection = memo(PanelSectionComponent);
