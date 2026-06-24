// The empty-section state: a centered "add panel" button shown when a sub-section
// has no open panels. This is a SHELL — the up-to-five quick actions land in Task
// 3.5. When the empty pane is a split half (the secondary half, or a primary whose
// section is split), it also offers a "close split" affordance so the other half can
// reclaim the space.

import { Button } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Plus } from "lucide-react";
import type { ReactElement } from "react";
import { memo } from "react";

import { ElementIds } from "~/api";

import styles from "./EmptySectionState.module.scss";
import { closeSplitAtom } from "./sectionActions.ts";
import { isSplitHalfAtom } from "./sectionAtoms.ts";
import type { SubSectionId } from "./sectionTypes.ts";
import { isSecondary, toSection } from "./sectionTypes.ts";

type EmptySectionStateProps = { subSection: SubSectionId };

const EmptySectionStateComponent = ({ subSection }: EmptySectionStateProps): ReactElement => {
  const isSectionSplit = useAtomValue(isSplitHalfAtom(subSection));
  const closeSplit = useSetAtom(closeSplitAtom);

  // The pane is a split half when it is the secondary half, or when it is the
  // primary of a section that currently has a split.
  const isSplitPane = isSecondary(subSection) || isSectionSplit;

  const handleAddPanel = (): void => {
    // Task 3.5: open AddPanelDropdown scoped to this sub-section.
  };

  const handleCloseSplit = (): void => {
    closeSplit({ section: toSection(subSection) });
  };

  return (
    <div className={styles.launcher}>
      <div className={styles.column}>
        <Button
          variant="soft"
          color="gray"
          size="2"
          onClick={handleAddPanel}
          data-testid={`${ElementIds.SECTION_EMPTY_STATE}-${subSection}`}
        >
          <Plus size={14} /> Add panel
        </Button>
        {isSplitPane && (
          <Button variant="ghost" color="gray" size="1" onClick={handleCloseSplit}>
            Close split
          </Button>
        )}
      </div>
    </div>
  );
};

export const EmptySectionState = memo(EmptySectionStateComponent);
