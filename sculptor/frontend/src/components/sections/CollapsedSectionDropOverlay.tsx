// An absolutely positioned drop target at a collapsed section's window edge while a
// panel drag is in progress. It overlays the existing content — nothing shifts —
// and dropping a panel onto it lands the panel in the section's primary
// sub-section, which expands the section and appends (withMovePanel →
// withExpandedSection). It shares the section body's droppable id — the body is not
// mounted while collapsed, so there is never a clash — and the same drop-target
// slice drives its highlight.
//
// Mounted for the whole drag so the keyboard pipeline can step onto it
// (ArrowLeft/Right/Down), but VISIBLE only while the pointer is in the matching
// window half — or while it is the current drop target, which covers keyboard
// drags. The overlay region is inside its half, so it is always visible when the
// pointer is over it; a hidden overlay never swallows a drop.

import { useDroppable } from "@dnd-kit/core";
import { useAtomValue } from "jotai";
import type { LucideIcon } from "lucide-react";
import { PanelBottom, PanelLeft, PanelRight } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./CollapsedSectionDropOverlay.module.scss";
import { sectionBodyDroppableId } from "./panelDnd.ts";
import { primaryOf } from "./sectionTypes.ts";
import { isDragPointerInHalfAtom, isDropTargetAtom } from "./transientAtoms.ts";

type CollapsibleSection = "left" | "right" | "bottom";

const SECTION_ICONS: Record<CollapsibleSection, LucideIcon> = {
  left: PanelLeft,
  right: PanelRight,
  bottom: PanelBottom,
};

type CollapsedSectionDropOverlayProps = { section: CollapsibleSection };

export const CollapsedSectionDropOverlay = ({ section }: CollapsedSectionDropOverlayProps): ReactElement => {
  const subSection = primaryOf(section);
  const isDropTarget = useAtomValue(isDropTargetAtom(subSection));
  const isPointerInHalf = useAtomValue(isDragPointerInHalfAtom(section));
  const { setNodeRef } = useDroppable({
    id: sectionBodyDroppableId(subSection),
    data: { kind: "section-body", subSection },
  });

  const isVisible = isPointerInHalf || isDropTarget;
  const Icon = SECTION_ICONS[section];

  const className = [
    styles.overlay,
    styles[section],
    isVisible ? styles.visible : "",
    isDropTarget ? styles.dropActive : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      ref={setNodeRef}
      className={className}
      data-testid={`${ElementIds.SECTION_DROP_OVERLAY}-${section}`}
      data-drop-target-subsection={subSection}
      data-drop-active={isDropTarget ? "true" : undefined}
    >
      <div className={styles.hint}>
        <Icon size={16} />
        <span className={styles.hintLabel}>Open {section} section</span>
      </div>
    </div>
  );
};
