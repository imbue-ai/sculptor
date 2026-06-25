// The empty-section state: a centered "add panel" button that opens the
// same AddPanelDropdown, plus up to five quick actions — always "New {recent}
// agent" and "New terminal", then up to three most-recently-created-but-closed
// single-instance panels (excluding any currently open, and never agents/terminals).
// When the empty pane is a split half it also offers a "close split" affordance so
// the other half can reclaim the space (closeSplitAtom owns this).

import { Button, Flex } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { MessageSquarePlus, Plus, SquareTerminal } from "lucide-react";
import type { ReactElement } from "react";
import { memo } from "react";

import { ElementIds } from "~/api";

import { AddPanelDropdown } from "./AddPanelDropdown.tsx";
import styles from "./EmptySectionState.module.scss";
import { closeSplitAtom } from "./sectionActions.ts";
import { isSplitHalfAtom } from "./sectionAtoms.ts";
import type { SubSectionId } from "./sectionTypes.ts";
import { isSecondary, toSection } from "./sectionTypes.ts";
import { recentlyClosedPanelIdsAtom } from "./transientAtoms.ts";
import type { StaticPanelOption } from "./useAddPanelActions.ts";
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

  // functions and callbacks
  const handleCloseSplit = (): void => {
    closeSplit({ section: toSection(subSection) });
  };

  // rendering / derived data
  // The pane is a split half when it is the secondary half, or when it is the
  // primary of a section that currently has a split.
  const isSplitPane = isSecondary(subSection) || isSectionSplit;

  // Recently-closed single-instance panels that are not currently open anywhere:
  // intersect the recent-closed list (newest first) with the available
  // single-instance panels (which already excludes open panels and dynamic ids).
  const availableById = new Map<string, StaticPanelOption>(
    actions.availableStaticPanels.map((panel) => [panel.id, panel]),
  );
  const recentPanelActions: ReadonlyArray<StaticPanelOption> = recentlyClosedIds
    .map((id) => availableById.get(id))
    .filter((panel): panel is StaticPanelOption => panel !== undefined)
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
              size="2"
              data-testid={`${ElementIds.SECTION_EMPTY_STATE}-${subSection}`}
            >
              <Plus size={14} /> Add panel
            </Button>
          }
        />

        <Flex direction="column" gap="1" align="stretch" className={styles.quickActions}>
          <Button
            variant="ghost"
            color="gray"
            size="1"
            className={styles.quickAction}
            onClick={() => actions.createRecentAgent()}
            data-testid={`${ElementIds.SECTION_EMPTY_QUICK_ACTION}-new-agent`}
          >
            <MessageSquarePlus size={14} /> New {actions.recentAgentLabel} agent
          </Button>
          <Button
            variant="ghost"
            color="gray"
            size="1"
            className={styles.quickAction}
            onClick={() => actions.createTerminal(subSection)}
            data-testid={`${ElementIds.SECTION_EMPTY_QUICK_ACTION}-new-terminal`}
          >
            <SquareTerminal size={14} /> New terminal
          </Button>
          {recentPanelActions.map((panel) => {
            const Icon = panel.icon;
            return (
              <Button
                key={panel.id}
                variant="ghost"
                color="gray"
                size="1"
                className={styles.quickAction}
                onClick={() => actions.openStaticPanel(panel.id, subSection)}
                data-testid={`${ElementIds.SECTION_EMPTY_QUICK_ACTION}-${panel.id}`}
              >
                <Icon size={14} /> {panel.displayName}
              </Button>
            );
          })}
        </Flex>

        {isSplitPane && (
          <Button
            variant="ghost"
            color="gray"
            size="1"
            onClick={handleCloseSplit}
            data-testid={ElementIds.SPLIT_CLOSE_OPTION}
          >
            Close split
          </Button>
        )}
      </div>
    </div>
  );
};

export const EmptySectionState = memo(EmptySectionStateComponent);
