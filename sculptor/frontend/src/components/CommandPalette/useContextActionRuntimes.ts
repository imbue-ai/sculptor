import { useSetAtom } from "jotai";
import { useMemo } from "react";

import { activateAgentPanelAtom } from "../../common/state/agentPanelPlacement.ts";
import { useMarkUnreadMutation } from "../../common/state/mutations";
import { makeAgentPanelId } from "../sections/registry/dynamicPanels.tsx";
import {
  agentDeleteTargetAtom,
  agentRenameTargetAtom,
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
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);
  const setAgentRenameTarget = useSetAtom(agentRenameTargetAtom);
  const activateAgentPanel = useSetAtom(activateAgentPanelAtom);
  const { mutate: markUnreadMutate } = useMarkUnreadMutation();
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
      markUnread: (agent): void => {
        if (agent.workspaceId == null) return;
        markUnreadMutate({ workspaceId: agent.workspaceId, agentId: agent.id });
      },
      // Activate the agent's panel first so its tab is guaranteed mounted, then
      // hand the panel id to the tab (via agentRenameTargetAtom) to enter inline
      // rename. Activation is scoped to the active workspace's layout, so it
      // keys off the task id alone.
      beginRename: (agent): void => {
        activateAgentPanel(agent.id);
        setAgentRenameTarget(makeAgentPanelId(agent.id));
      },
      beginDelete: (agent): void => setAgentDeleteTarget({ id: agent.id, name: agent.title ?? "" }),
    }),
    [markUnreadMutate, activateAgentPanel, setAgentRenameTarget, setAgentDeleteTarget],
  );

  return { workspaceActionRuntime, agentActionRuntime };
};
