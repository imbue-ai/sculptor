// A section's content area: the active panel's component (agent chat, terminal, diff
// viewer, …) or the empty-section state. THIS IS THE BOUNDARY that subscribes to the
// resolved active panel COMPONENT (identity-cached per panel id in the registry), NOT
// the panel id followed by a lookup in render — so a registry rebuild on a task tick,
// or a workspace switch, never remounts live panel content.

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { EmptySectionState } from "./EmptySectionState.tsx";
import { activePanelComponentInSubSectionAtom } from "./registry/panelRegistry.ts";
import styles from "./SectionBody.module.scss";
import type { SubSectionId } from "./sectionTypes.ts";

type SectionBodyProps = { subSection: SubSectionId };

const SectionBodyComponent = ({ subSection }: SectionBodyProps): ReactElement => {
  const ActivePanelComponent = useAtomValue(activePanelComponentInSubSectionAtom(subSection));

  return (
    <div className={styles.content}>
      {ActivePanelComponent !== undefined ? <ActivePanelComponent /> : <EmptySectionState subSection={subSection} />}
    </div>
  );
};

export const SectionBody = memo(SectionBodyComponent);
