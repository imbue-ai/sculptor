// The empty-section state: a centered "Add panel" button that opens the same
// AddPanelDropdown, over a "Quick add" list of up to five shortcuts — always
// "New {recent} agent" and "New terminal", then up to three
// most-recently-created-but-closed single-instance panels (excluding any
// currently open, and never agents/terminals).
// When the empty pane is a split half it also offers a "close split" affordance so
// the other half can reclaim the space (closeSplitAtom owns this).

import { Button, Flex, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { ElementIds } from "~/api";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";

import { availableStaticPanelsAtom, recentAgentLabel, recentAgentTypeAtom } from "./addPanelCore.ts";
import { AddPanelDropdown } from "./AddPanelDropdown.tsx";
import styles from "./EmptySectionState.module.scss";
import type { AvailableStaticPanel } from "./layoutQueries.ts";
import { closeSplitAtom } from "./sectionActions.ts";
import { isSplitHalfAtom } from "./sectionAtoms.ts";
import type { SubSectionId } from "./sectionTypes.ts";
import { isSecondary, toSection } from "./sectionTypes.ts";
import { recentlyClosedPanelIdsAtom } from "./transientAtoms.ts";
import { useAddPanelActions } from "./useAddPanelActions.ts";

// At most three recently-closed panel quick actions, so the total stays ≤ five
// alongside the always-present New agent / New terminal rows.
const MAX_RECENT_PANEL_ACTIONS = 3;

type EmptySectionStateProps = { subSection: SubSectionId };

const EmptySectionStateComponent = ({ subSection }: EmptySectionStateProps): ReactElement => {
  // state and hooks
  const isSectionSplit = useAtomValue(isSplitHalfAtom(subSection));
  const closeSplit = useSetAtom(closeSplitAtom);
  const recentlyClosedIds = useAtomValue(recentlyClosedPanelIdsAtom);
  const actions = useAddPanelActions();
  // Unlike the dropdown (whose content mounts on open), the quick-add list and the
  // "New {recent} agent" label render whenever the empty pane is visible, so this
  // component subscribes to the derived add-panel atoms itself. Both are
  // equality-guarded, so layout writes / task ticks that change neither list nor
  // type do not re-render the pane. It only mounts for EMPTY sub-sections, so the
  // registrations query gains at most a handful of observers.
  const recentAgentType = useAtomValue(recentAgentTypeAtom);
  const availableStaticPanels = useAtomValue(availableStaticPanelsAtom);
  const { registrations } = useTerminalAgentRegistrations();

  // functions and callbacks
  const handleCloseSplit = (): void => {
    closeSplit({ section: toSection(subSection) });
  };

  // rendering / derived data
  // The pane is a split half when it is the secondary half, or when it is the
  // primary of a section that currently has a split.
  const isSplitPane = isSecondary(subSection) || isSectionSplit;

  const recentAgentDisplayLabel = recentAgentLabel(recentAgentType, registrations);

  // Recently-closed single-instance panels that are not currently open anywhere:
  // intersect the recent-closed list (newest first) with the available
  // single-instance panels (which already excludes open panels and dynamic ids).
  const availableById = new Map<string, AvailableStaticPanel>(availableStaticPanels.map((panel) => [panel.id, panel]));
  const recentPanelActions: ReadonlyArray<AvailableStaticPanel> = recentlyClosedIds
    .map((id) => availableById.get(id))
    .filter((panel): panel is AvailableStaticPanel => panel !== undefined)
    .slice(0, MAX_RECENT_PANEL_ACTIONS);

  return (
    <div className={styles.launcher}>
      <div className={styles.column}>
        <AddPanelDropdown
          subSection={subSection}
          trigger={
            <Button
              variant="soft"
              color="gray"
              size="1"
              className={styles.addPanelButton}
              data-testid={`${ElementIds.SECTION_EMPTY_STATE}-${subSection}`}
            >
              Add panel
            </Button>
          }
        />

        <Text size="1" color="gray" className={styles.heading}>
          Quick add
        </Text>
        <Flex direction="column" gap="2" align="center">
          <Button
            variant="soft"
            color="gray"
            size="1"
            onClick={() => actions.createRecentAgent(subSection)}
            data-testid={`${ElementIds.SECTION_EMPTY_QUICK_ACTION}-${subSection}-new-agent`}
          >
            New {recentAgentDisplayLabel}
          </Button>
          <Button
            variant="soft"
            color="gray"
            size="1"
            onClick={() => actions.createTerminal(subSection)}
            data-testid={`${ElementIds.SECTION_EMPTY_QUICK_ACTION}-${subSection}-new-terminal`}
          >
            New terminal
          </Button>
          {recentPanelActions.map((panel) => (
            <Button
              key={panel.id}
              variant="soft"
              color="gray"
              size="1"
              onClick={() => actions.openStaticPanel(panel.id, subSection)}
              data-testid={`${ElementIds.SECTION_EMPTY_QUICK_ACTION}-${subSection}-${panel.id}`}
            >
              {panel.displayName}
            </Button>
          ))}
        </Flex>

        {isSplitPane && (
          <Button
            variant="outline"
            color="gray"
            size="1"
            className={styles.closeSplit}
            onClick={handleCloseSplit}
            data-testid={`${ElementIds.SPLIT_CLOSE_OPTION}-${subSection}`}
          >
            Close split
          </Button>
        )}
      </div>
    </div>
  );
};

export const EmptySectionState = memo(EmptySectionStateComponent);
