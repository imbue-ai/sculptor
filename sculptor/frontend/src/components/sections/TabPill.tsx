// A non-interactive copy of a panel tab pill (status dot + label), used where the
// real draggable tab (SectionHeader's PanelTab) can't be:
//   - "ghost": the drop-preview placeholder spliced into a section's tab strip
//     during a cross-section drag. Deliberately NOT a dnd-kit draggable/droppable —
//     the real draggable (same panel id) is still mounted in the source section, and
//     registering the id twice would confuse dnd-kit. Mirrors the tab pill footprint
//     so the strip reserves the right space for the drop.
//   - "overlay": the floating copy rendered in the dnd-kit DragOverlay, elevated so
//     it reads as "picked up" while it follows the cursor.
//
// Reads the panel's registry slice itself so call sites only pass the id; renders
// nothing for unknown panels.

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { AgentStatusDot } from "~/components/statusDot";

import { panelDefinitionByIdAtom } from "./registry/panelRegistry.ts";
import type { PanelId } from "./sectionTypes.ts";
import styles from "./TabPill.module.scss";

type TabPillProps = {
  panelId: PanelId;
  variant: "ghost" | "overlay";
};

const TabPillComponent = ({ panelId, variant }: TabPillProps): ReactElement | null => {
  const definition = useAtomValue(panelDefinitionByIdAtom(panelId));
  if (definition === undefined) {
    return null;
  }
  const isGhost = variant === "ghost";
  return (
    <div
      className={`${styles.pill} ${isGhost ? styles.ghost : styles.overlay}`}
      // The ghost sits inside the real tab strip but is hidden from the accessibility
      // tree wholesale. It deliberately omits `data-section-tab`, so the drop-index math
      // (which counts only real `data-section-tab` tabs) skips it without needing a marker.
      {...(isGhost ? { "aria-hidden": true } : {})}
    >
      {definition.dotStatus !== undefined && (
        // The overlay is visible to assistive tech, so its decorative dot is hidden
        // individually; the ghost's whole root is already aria-hidden.
        <div className={styles.dot} data-panel-tab-dot={definition.dotStatus} aria-hidden={isGhost ? undefined : true}>
          <AgentStatusDot status={definition.dotStatus} size={8} />
        </div>
      )}
      <span className={styles.label}>{definition.displayName}</span>
    </div>
  );
};

export const TabPill = memo(TabPillComponent);
