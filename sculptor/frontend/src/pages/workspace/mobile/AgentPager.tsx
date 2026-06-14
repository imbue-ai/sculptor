import { useAtomValue } from "jotai";
import { posthog } from "posthog-js";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { createWorkspaceAgent, type LlmModel } from "~/api";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";

import styles from "./AgentPager.module.scss";

/**
 * AgentPager (A1-A3) — centered pager dots under the chat input, one per agent
 * in the workspace (the active dot is elongated / accent), plus a dashed
 * "new agent" dot at the end. Tapping a dot switches the active agent; tapping
 * the dashed dot creates a new agent and lands on its fresh empty chat (the
 * new-agent compose destination, CH2). Tap-first; swipe is a follow-up.
 */
export const AgentPager = (): ReactElement | null => {
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const tasks = useAtomValue(tasksArrayAtom);
  const [isCreating, setIsCreating] = useState(false);

  const workspaceAgents = useMemo(() => {
    return (tasks ?? [])
      .filter((task) => task.workspaceId === workspaceID)
      .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  }, [tasks, workspaceID]);

  const handleNewAgent = useCallback(async (): Promise<void> => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      // Inherit the current agent's model so the new agent starts the same.
      const currentAgent = agentID ? workspaceAgents.find((a) => a.id === agentID) : undefined;
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
  }, [isCreating, agentID, workspaceAgents, workspaceID, navigateToAgent]);

  // A lone agent with no peers still shows its dot + the new-agent dot.
  if (workspaceAgents.length === 0) return null;

  return (
    <div className={styles.pager}>
      <div className={styles.dots}>
        {workspaceAgents.map((agent) => {
          const isActive = agent.id === agentID;
          return (
            <button
              key={agent.id}
              type="button"
              className={`${styles.dot} ${isActive ? styles.dotActive : ""}`}
              aria-label={`Switch to ${agent.titleOrSomethingLikeIt}`}
              aria-current={isActive}
              onClick={() => navigateToAgent(workspaceID, agent.id)}
            />
          );
        })}
        <button
          type="button"
          className={styles.newAgentDot}
          aria-label="New agent"
          disabled={isCreating}
          onClick={() => void handleNewAgent()}
        />
      </div>
    </div>
  );
};
