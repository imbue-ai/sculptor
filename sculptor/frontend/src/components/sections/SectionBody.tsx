// A section's content area: the active panel's component (agent chat, terminal, diff
// viewer, …) or the empty-section state. THIS IS THE BOUNDARY that subscribes to the
// resolved active panel COMPONENT (identity-cached per panel id in the registry), NOT
// the panel id followed by a lookup in render — so a registry rebuild on a task tick,
// or a workspace switch, never remounts live panel content.

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { createElement, memo } from "react";

import { EmptySectionState } from "./EmptySectionState.tsx";
import { activePanelComponentInSubSectionAtom, isSubSectionPanelLoadingAtom } from "./registry/panelRegistry.ts";
import styles from "./SectionBody.module.scss";
import { SectionLoadingState } from "./SectionLoadingState.tsx";
import type { SubSectionId } from "./sectionTypes.ts";

type SectionBodyProps = { subSection: SubSectionId };

const SectionBodyComponent = ({ subSection }: SectionBodyProps): ReactElement => {
  // The panel component arrives from the registry with a cached identity;
  // createElement renders it without the compiler mistaking the local binding
  // for a component defined during render.
  const activePanelComponent = useAtomValue(activePanelComponentInSubSectionAtom(subSection));
  // When no component resolves, tell "the placed panel is still loading (agent
  // snapshot not in yet)" apart from "this section is genuinely empty" — a bare
  // undefined component can't, so a reload would flash the Add-panel launcher.
  const isPanelLoading = useAtomValue(isSubSectionPanelLoadingAtom(subSection));

  return (
    <div className={styles.content}>
      {activePanelComponent !== undefined ? (
        createElement(activePanelComponent)
      ) : isPanelLoading ? (
        <SectionLoadingState />
      ) : (
        <EmptySectionState subSection={subSection} />
      )}
    </div>
  );
};

export const SectionBody = memo(SectionBodyComponent);
