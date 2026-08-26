import { useAtomValue } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useState } from "react";

import { createWorkspaceAgent, type LlmModel } from "~/api";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";

/**
 * Creates a new agent in the current workspace — inheriting the currently-viewed
 * agent's model — and navigates to its fresh empty chat. Shared by the
 * AgentSheet's "New agent" row and the workspace header's "Create new agent"
 * menu item so the two stay in lock-step. (The desktop AgentTabs keeps its own
 * copy of this flow.)
 */
export const useCreateAgent = (): { createAgent: () => Promise<void>; isCreating: boolean } => {
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const tasks = useAtomValue(tasksArrayAtom);
  const [isCreating, setIsCreating] = useState(false);

  const createAgent = useCallback(async (): Promise<void> => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      // Inherit the current agent's model so the new agent starts the same.
      const currentAgent = agentID ? (tasks ?? []).find((t) => t.id === agentID) : undefined;
      const model = currentAgent?.model as LlmModel | undefined;
      const response = await createWorkspaceAgent({ path: { workspace_id: workspaceID }, body: { model } });
      if (response.data) {
        posthog.capture("agent.added", { workspace_id: workspaceID, agent_id: response.data.id, model: model ?? null });
        navigateToAgent(workspaceID, response.data.id);
      }
    } catch (error) {
      console.error("Failed to create agent:", error);
    } finally {
      setIsCreating(false);
    }
  }, [isCreating, agentID, tasks, workspaceID, navigateToAgent]);

  return { createAgent, isCreating };
};
