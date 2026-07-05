// A section's content area: the active panel's component (agent chat, terminal, diff
// viewer, …) or the empty-section state. THIS IS THE BOUNDARY that subscribes to the
// resolved active panel COMPONENT (identity-cached per panel id in the registry), NOT
// the panel id followed by a lookup in render — so a registry rebuild on a task tick,
// or a workspace switch, never remounts live panel content.

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { createElement, memo } from "react";

import { activePanelComponentInSubSectionAtom } from "~/pages/workspace/layout/registry/panelRegistry.ts";
import type { SubSectionId } from "~/pages/workspace/layout/types/section.ts";

import { EmptySectionState } from "./EmptySectionState.tsx";
import styles from "./SectionBody.module.scss";

type SectionBodyProps = { subSection: SubSectionId };

const SectionBodyComponent = ({ subSection }: SectionBodyProps): ReactElement => {
  // The panel component arrives from the registry with a cached identity;
  // createElement renders it without the compiler mistaking the local binding
  // for a component defined during render.
  const activePanelComponent = useAtomValue(activePanelComponentInSubSectionAtom(subSection));

  return (
    <div className={styles.content}>
      {activePanelComponent !== undefined ? (
        createElement(activePanelComponent)
      ) : (
        <EmptySectionState subSection={subSection} />
      )}
    </div>
  );
};

export const SectionBody = memo(SectionBodyComponent);
