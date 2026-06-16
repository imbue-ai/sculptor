import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useMemo, useRef } from "react";

import { type AgentTypeName, createWorkspaceAgent, type LlmModel } from "~/api";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import {
  encodeRegisteredAgentType,
  lastUsedAgentTypeAtom,
  parseStoredAgentType,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { tasksArrayAtom, updateTasksAtom } from "~/common/state/atoms/tasks.ts";
import { isPiAgentEnabledAtom } from "~/common/state/atoms/userConfig.ts";
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
  /**
   * Create a fresh agent here and focus it. With no argument, creates the
   * last-used agent type; pass an explicit `harness` (and `registrationId`
   * for registered agents) to choose one — which also becomes the new default.
   */
  createAgent: (harness?: AgentTypeName, registrationId?: string) => void;
  /** Create a fresh terminal here. */
  createTerminal: () => void;
};

/**
 * Everything a section's "+" can add: static panels, plus the agent/terminal
 * "New …" actions and the lists of existing agents/terminals not open anywhere
 * (REQ-AGENT-2 / REQ-TERM-2 / REQ-INST-1).
 */
export const useAddPanelMenu = (zone: ZoneId): AddPanelMenu => {
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const tasks = useAtomValue(tasksArrayAtom);
  const updateTasks = useSetAtom(updateTasksAtom);
  const addTerminal = useSetAtom(addTerminalAtom);
  const movePanel = useAddPanelToSection();
  const [lastUsedAgentType, setLastUsedAgentType] = useAtom(lastUsedAgentTypeAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  // Guards against a held `new_agent` keybinding firing a second create before
  // the first POST resolves.
  const isCreatingRef = useRef(false);

  const staticPanels = useAddablePanels(zone);
  const existingAgents = useAddableDynamicPanels("agent");
  const existingTerminals = useAddableDynamicPanels("terminal");

  const openPanel = useCallback((panelId: PanelId): void => movePanel(panelId, zone), [movePanel, zone]);

  const workspaceAgents = useMemo(
    () => (tasks ?? []).filter((task) => task.workspaceId === workspaceID),
    [tasks, workspaceID],
  );

  // A stored "pi" is unusable once pi-agent is turned off — fall back to Claude.
  const defaultAgentType: StoredAgentType =
    lastUsedAgentType === "pi" && !isPiAgentEnabled ? "claude" : lastUsedAgentType;

  const createAgent = useCallback(
    (harness?: AgentTypeName, registrationId?: string): void => {
      if (isCreatingRef.current) return;
      isCreatingRef.current = true;
      void (async (): Promise<void> => {
        try {
          // An explicit choice wins and becomes the new default; calling with
          // no argument (the `+`, the keybinding, Cmd+K) creates the last-used
          // type. Registered agents are remembered as `registered:<id>`.
          let agentType: AgentTypeName;
          let resolvedRegistrationId: string | undefined;
          if (harness !== undefined) {
            agentType = harness;
            resolvedRegistrationId = registrationId;
            setLastUsedAgentType(
              harness === "registered" && registrationId !== undefined
                ? encodeRegisteredAgentType(registrationId)
                : harness,
            );
          } else {
            ({ agentType, registrationId: resolvedRegistrationId } = parseStoredAgentType(defaultAgentType));
          }

          // Inherit the model from the currently viewed agent so the new agent
          // starts with the same selection. Terminal agents never read it.
          const currentAgent = agentID ? workspaceAgents.find((a) => a.id === agentID) : undefined;
          const model = currentAgent?.model as LlmModel | undefined;

          let response;
          try {
            response = await createWorkspaceAgent({
              path: { workspace_id: workspaceID },
              body: { model, agentType, registrationId: resolvedRegistrationId },
            });
          } catch (error) {
            // A remembered registered agent's registration can be deleted out
            // from under the stored default — only that case retries as Claude.
            // Other failures propagate rather than silently substituting a
            // different agent type than the user asked for.
            if (harness === undefined && agentType === "registered") {
              setLastUsedAgentType("claude");
              response = await createWorkspaceAgent({
                path: { workspace_id: workspaceID },
                body: { model, agentType: "claude" },
              });
            } else {
              throw error;
            }
          }

          if (response.data) {
            posthog.capture("agent.added", {
              workspace_id: workspaceID,
              agent_id: response.data.id,
              model: model ?? null,
              agent_type: agentType,
            });
            // Add the task optimistically so its panel is registered before the
            // WebSocket update arrives, then place + focus it in this zone.
            updateTasks({ [response.data.id]: response.data });
            movePanel(agentPanelId(response.data.id), zone);
            navigateToAgent(workspaceID, response.data.id);
          }
        } catch (error) {
          console.error("Failed to create agent:", error);
        } finally {
          isCreatingRef.current = false;
        }
      })();
    },
    [
      workspaceID,
      agentID,
      workspaceAgents,
      defaultAgentType,
      setLastUsedAgentType,
      updateTasks,
      movePanel,
      zone,
      navigateToAgent,
    ],
  );

  const createTerminal = useCallback((): void => {
    const panelId = addTerminal(workspaceID);
    movePanel(panelId, zone);
  }, [addTerminal, workspaceID, movePanel, zone]);

  return { staticPanels, existingAgents, existingTerminals, openPanel, createAgent, createTerminal };
};
