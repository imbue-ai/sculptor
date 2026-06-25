// A thin drop target rendered at a collapsed section's grid edge while a panel drag is
// in progress. Dropping a panel onto it lands the panel in the section's
// primary sub-section, which expands the section and appends (withMovePanel →
// withExpandedSection). It shares the section body's droppable id — the body is not
// mounted while collapsed, so there is never a clash — and the same drop-target slice
// drives its highlight, so it reads identically to an in-grid section drop target.
//
// Rendered only during a drag (SectionGrid gates on the stable dragged-panel id), so
// it never occupies layout otherwise. Being a real in-grid droppable at the section's
// edge keeps the keyboard drag navigable: ArrowLeft/Right/Down jumps to it the same way
// it jumps to an expanded section body.

import { useDroppable } from "@dnd-kit/core";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./CollapsedSectionDropRail.module.scss";
import { sectionBodyDroppableId } from "./panelDnd.ts";
import type { SectionId } from "./sectionTypes.ts";
import { primaryOf } from "./sectionTypes.ts";
import { isDropTargetAtom } from "./transientAtoms.ts";

type CollapsedSectionDropRailProps = { section: SectionId; orientation: "vertical" | "horizontal" };

export const CollapsedSectionDropRail = ({ section, orientation }: CollapsedSectionDropRailProps): ReactElement => {
  const subSection = primaryOf(section);
  const isDropTarget = useAtomValue(isDropTargetAtom(subSection));
  const { setNodeRef } = useDroppable({
    id: sectionBodyDroppableId(subSection),
    data: { kind: "section-body", subSection },
  });

  const className = [
    styles.rail,
    orientation === "vertical" ? styles.vertical : styles.horizontal,
    isDropTarget ? styles.dropActive : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      ref={setNodeRef}
      className={className}
      data-testid={`${ElementIds.SECTION_DROP_RAIL}-${section}`}
      data-drop-target-subsection={subSection}
      data-drop-active={isDropTarget ? "true" : undefined}
    />
  );
};
