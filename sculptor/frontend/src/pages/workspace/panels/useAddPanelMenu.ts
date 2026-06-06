import { useSetAtom } from "jotai";
import { useCallback } from "react";

import { createWorkspaceAgent } from "~/api";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { updateTasksAtom } from "~/common/state/atoms/tasks.ts";
import { useAddableDynamicPanels, useAddablePanels, useAddPanelToSection } from "~/components/panels/sectionHooks.ts";
import type { PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";
import { agentPanelId } from "~/pages/workspace/panels/dynamicPanels.tsx";
import { addTerminalAtom } from "~/pages/workspace/panels/terminals.ts";

type AddPanelMenu = {
  /** Static panels addable here (move from wherever they are). */
  staticPanels: ReadonlyArray<PanelDefinition>;
  /** Agents not currently open in any section (REQ-AGENT-2). */
  existingAgents: ReadonlyArray<PanelDefinition>;
  /** Terminals not currently open in any section (REQ-TERM-2). */
  existingTerminals: ReadonlyArray<PanelDefinition>;
  /** Move an existing panel (static, agent, or terminal) into this section. */
  openPanel: (panelId: PanelId) => void;
  /** Create a fresh agent here and focus it. */
  createAgent: () => void;
  /** Create a fresh terminal here. */
  createTerminal: () => void;
};

/**
 * Everything a section's "+" can add: static panels, plus the agent/terminal
 * "New …" actions and the lists of existing agents/terminals not open anywhere
 * (REQ-AGENT-2 / REQ-TERM-2 / REQ-INST-1).
 */
export const useAddPanelMenu = (zone: ZoneId): AddPanelMenu => {
  const { workspaceID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const updateTasks = useSetAtom(updateTasksAtom);
  const addTerminal = useSetAtom(addTerminalAtom);
  const movePanel = useAddPanelToSection();

  const staticPanels = useAddablePanels(zone);
  const existingAgents = useAddableDynamicPanels("agent");
  const existingTerminals = useAddableDynamicPanels("terminal");

  const openPanel = useCallback((panelId: PanelId): void => movePanel(panelId, zone), [movePanel, zone]);

  const createAgent = useCallback((): void => {
    void (async (): Promise<void> => {
      try {
        const response = await createWorkspaceAgent({ path: { workspace_id: workspaceID }, body: {} });
        if (response.data) {
          // Add the task optimistically so its panel is registered before the
          // WebSocket update arrives, then place + focus it.
          updateTasks({ [response.data.id]: response.data });
          movePanel(agentPanelId(response.data.id), zone);
          navigateToAgent(workspaceID, response.data.id);
        }
      } catch (error) {
        console.error("Failed to create agent:", error);
      }
    })();
  }, [workspaceID, updateTasks, movePanel, zone, navigateToAgent]);

  const createTerminal = useCallback((): void => {
    const panelId = addTerminal(workspaceID);
    movePanel(panelId, zone);
  }, [addTerminal, workspaceID, movePanel, zone]);

  return { staticPanels, existingAgents, existingTerminals, openPanel, createAgent, createTerminal };
};
