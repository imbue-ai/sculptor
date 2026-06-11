import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { activePanelIdInZoneAtom, panelRegistryAtom } from "~/components/panels/atoms.ts";
import { EmptyPanelLauncher } from "~/components/panels/EmptyPanelLauncher.tsx";
import { isSplitHalfAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import type { ZoneId } from "~/components/panels/types.ts";

import styles from "./PanelSection.module.scss";

type SectionBodyProps = {
  zone: ZoneId;
};

/**
 * A section's content area: the active panel (agent chat, terminal, diff
 * viewer, …) or the empty-section launcher. Memoized behind primitive props
 * and narrow per-zone atoms so that drag previews, resizes, and other
 * tab-strip churn never re-render the (heavy) panel content. The wrapper div
 * keeps the `data-zone-id` / `tabIndex` contract that the panel focus
 * shortcuts and maximize-focused command query.
 */
const SectionBodyInner = ({ zone }: SectionBodyProps): ReactElement => {
  const registry = useAtomValue(panelRegistryAtom);
  const activePanelId = useAtomValue(activePanelIdInZoneAtom(zone));
  // Whether this section is one half of a split (its primary zone is split).
  // Used to clarify, when the half is empty, that splitting moved the tab to
  // the other pane and this one can be filled.
  const isSplitHalf = useAtomValue(isSplitHalfAtom(zone));

  const ActivePanelComponent = activePanelId ? registry.find((p) => p.id === activePanelId)?.component : undefined;

  return (
    <div className={styles.content} data-zone-id={zone} tabIndex={-1}>
      {ActivePanelComponent ? (
        <ActivePanelComponent />
      ) : (
        <EmptyPanelLauncher
          zone={zone}
          heading={isSplitHalf ? "This split pane is empty — add a panel, or drag a tab here." : undefined}
        />
      )}
    </div>
  );
};

export const SectionBody = memo(SectionBodyInner);
