// One uniform section (left / center / right / bottom, or a split half). Renders a
// single SectionHeader (tabs + add + maximize) and the SectionBody. Deliberately
// thin: it subscribes only to narrow per-sub-section flags and to the maximized
// section, while the heavy state lives behind its memoized children. It re-renders
// on a dnd `over` change once drag wiring lands (Task 4.1), so everything here stays
// cheap.
//
// A plain click sets this section active silently (no ring flash) — the ring is only
// pulsed by deliberate jumps (Task 4.4). The active-section ring is drawn as a CSS
// overlay gated on isRingVisible; the maximized styling hook (full layout in Task
// 4.3) flips when this section is the maximized one.

import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { ElementIds } from "~/api";

import styles from "./PanelSection.module.scss";
import { setActiveSectionAtom } from "./sectionActions.ts";
import { isActiveSubSectionAtom } from "./sectionAtoms.ts";
import { SectionBody } from "./SectionBody.tsx";
import { SectionHeader } from "./SectionHeader.tsx";
import type { SubSectionId } from "./sectionTypes.ts";
import { toSection } from "./sectionTypes.ts";
import { isDropTargetAtom, isRingVisibleAtom, maximizedSectionAtom } from "./transientAtoms.ts";

type PanelSectionProps = { subSection: SubSectionId };

const PanelSectionComponent = ({ subSection }: PanelSectionProps): ReactElement => {
  const isDropTarget = useAtomValue(isDropTargetAtom(subSection));
  const isActive = useAtomValue(isActiveSubSectionAtom(subSection));
  const isRingVisible = useAtomValue(isRingVisibleAtom(subSection));
  const maximizedSection = useAtomValue(maximizedSectionAtom);
  const setActiveSection = useSetAtom(setActiveSectionAtom);

  const isMaximized = maximizedSection === toSection(subSection);

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
      className={className}
      data-testid={`${ElementIds.SECTION_ACTIVE_RING}-${subSection}`}
      data-maximized={isMaximized ? "true" : undefined}
      // Task 4.1: wire dnd droppable (keyed by subSection); for now the drop-target
      // styling hook is the only seam. isDropTarget reads the per-sub-section slice.
      data-drop-target-subsection={subSection}
      onPointerDown={handlePointerDown}
    >
      <SectionHeader subSection={subSection} />
      <SectionBody subSection={subSection} />
    </div>
  );
};

export const PanelSection = memo(PanelSectionComponent);
