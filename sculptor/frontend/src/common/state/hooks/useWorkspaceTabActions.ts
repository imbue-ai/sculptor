import { useAtomValue } from "jotai";
import { useCallback } from "react";

import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import {
  agentIdsByWorkspaceAtom,
  effectiveOpenTabIdsAtom,
  parseDraftIdFromTabId,
} from "~/common/state/atoms/workspaces.ts";

import { HOME_TAB_ID, SETTINGS_TAB_ID } from "../../utils/workspaceTabIds.ts";

/**
 * `navigateToNextTab` — the shared "this tab is going away, move to a sensible
 * neighbour" rule. Callers that close or delete a tab pass the departing tab id;
 * this picks the next tab from the open order (falling back to Home when nothing
 * remains) and navigates there, resolving pseudo-tabs (Home/Settings), draft
 * tabs, and each workspace's last-viewed agent. The sidebar's delete flow and the
 * palette's delete confirmation both reuse it so their post-delete navigation
 * can't drift.
 */
export const useWorkspaceTabActions = (): {
  navigateToNextTab: (closedTabId: string) => void;
} => {
  const effectiveOpenTabIds = useAtomValue(effectiveOpenTabIdsAtom);
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const { navigateToWorkspace, navigateToAgent, navigateToHome, navigateToGlobalSettings } = useImbueNavigate();

  const handleWorkspaceClick = useCallback(
    (workspaceId: string): void => {
      const savedAgentId = agentIdsByWorkspace.get(workspaceId);
      if (savedAgentId) {
        navigateToAgent(workspaceId, savedAgentId);
        return;
      }
      navigateToWorkspace(workspaceId);
    },
    [agentIdsByWorkspace, navigateToAgent, navigateToWorkspace],
  );

  const navigateToNextTab = useCallback(
    (closedTabId: string): void => {
      const remaining = effectiveOpenTabIds.filter((id) => id !== closedTabId);
      if (remaining.length === 0) {
        navigateToHome();
        return;
      }
      // closedTabId may already be gone from effectiveOpenTabIds — e.g. an
      // optimistic delete removed the tab before this runs — making indexOf
      // return -1. Clamp to a valid range so we land on the first surviving tab
      // instead of reading remaining[-1] (undefined).
      const closedIndex = effectiveOpenTabIds.indexOf(closedTabId);
      const nextTab = remaining[Math.min(Math.max(closedIndex, 0), remaining.length - 1)];
      if (nextTab === HOME_TAB_ID) {
        navigateToHome();
      } else if (nextTab === SETTINGS_TAB_ID) {
        navigateToGlobalSettings();
      } else {
        const draftId = parseDraftIdFromTabId(nextTab);
        if (draftId !== null) {
          // Draft tabs have no route of their own; fall back to Home.
          navigateToHome();
        } else {
          handleWorkspaceClick(nextTab);
        }
      }
    },
    [effectiveOpenTabIds, handleWorkspaceClick, navigateToHome, navigateToGlobalSettings],
  );

  return { navigateToNextTab };
};
