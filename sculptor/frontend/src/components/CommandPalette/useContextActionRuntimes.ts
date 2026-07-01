import { useSetAtom } from "jotai";
import { useMemo } from "react";

import { markWorkspaceAgentUnread } from "../../api";
import { updateTasksAtom } from "../../common/state/atoms/tasks.ts";
import {
  agentDeleteTargetAtom,
  renamingAgentIdAtom,
  renamingWorkspaceIdAtom,
  workspaceDeleteTargetAtom,
} from "./contextActions/atoms.ts";
import type { AgentActionRuntime, WorkspaceActionRuntime } from "./contextActions/types.ts";
import { useGitAndOpenInRuntime } from "./contextActions/useGitAndOpenInRuntime.ts";

/**
 * Build the `WorkspaceActionRuntime` and `AgentActionRuntime` objects
 * the dynamic providers need.
 */
export const useContextActionRuntimes = (): {
  workspaceActionRuntime: WorkspaceActionRuntime;
  agentActionRuntime: AgentActionRuntime;
} => {
  const setRenamingWorkspaceId = useSetAtom(renamingWorkspaceIdAtom);
  const setWorkspaceDeleteTarget = useSetAtom(workspaceDeleteTargetAtom);
  const setRenamingAgentId = useSetAtom(renamingAgentIdAtom);
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);
  const updateTasks = useSetAtom(updateTasksAtom);
  const gitAndOpenIn = useGitAndOpenInRuntime();

  // Identity-stable (jotai's `useSetAtom` returns stable refs; `gitAndOpenIn`
  // is memoized on `[store]`), so the runtime doesn't churn between renders.
  const workspaceActionRuntime = useMemo<WorkspaceActionRuntime>(
    () => ({
      beginRename: (ws): void => setRenamingWorkspaceId(ws.objectId),
      beginDelete: (ws): void => setWorkspaceDeleteTarget({ id: ws.objectId, name: ws.description ?? "" }),
      ...gitAndOpenIn,
    }),
    [setRenamingWorkspaceId, setWorkspaceDeleteTarget, gitAndOpenIn],
  );

  const agentActionRuntime = useMemo<AgentActionRuntime>(
    () => ({
      beginRename: (agent): void => setRenamingAgentId(agent.id),
      markUnread: (agent): void => {
        if (agent.workspaceId == null) return;
        updateTasks({ [agent.id]: { ...agent, lastReadAt: null } });
        markWorkspaceAgentUnread({
          path: { workspace_id: agent.workspaceId, agent_id: agent.id },
        }).catch(() => {
          // Fire-and-forget: server value will arrive via WebSocket.
        });
      },
      beginDelete: (agent): void => setAgentDeleteTarget({ id: agent.id, name: agent.title ?? "" }),
    }),
    [setRenamingAgentId, updateTasks, setAgentDeleteTarget],
  );

  return { workspaceActionRuntime, agentActionRuntime };
};
