import { useSetAtom } from "jotai";
import { useStore } from "jotai/react";
import { useMemo } from "react";

import { markWorkspaceAgentUnread } from "../../api";
import { updateTasksAtom } from "../../common/state/atoms/tasks.ts";
import { effectiveOpenTabIdsAtom } from "../../common/state/atoms/workspaces.ts";
import { useWorkspaceTabActions } from "../useWorkspaceTabActions.ts";
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
 *
 * The close handlers come from `useWorkspaceTabActions`, the same hook
 * `WorkspaceTabs.tsx` consumes — so the right-click context menu and
 * the Cmd+K palette share one implementation of close + navigate.
 */
export const useContextActionRuntimes = (): {
  workspaceActionRuntime: WorkspaceActionRuntime;
  agentActionRuntime: AgentActionRuntime;
} => {
  const store = useStore();
  const setRenamingWorkspaceId = useSetAtom(renamingWorkspaceIdAtom);
  const setWorkspaceDeleteTarget = useSetAtom(workspaceDeleteTargetAtom);
  const setRenamingAgentId = useSetAtom(renamingAgentIdAtom);
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);
  const updateTasks = useSetAtom(updateTasksAtom);
  const gitAndOpenIn = useGitAndOpenInRuntime();
  const { handleClose, handleCloseOthers, handleCloseAll } = useWorkspaceTabActions();

  // Identity-stable (jotai's `useStore` and `useSetAtom` return stable refs;
  // `gitAndOpenIn` is memoized on `[store]`). `canCloseOthers` reads the
  // tab count from the store at call time so the runtime doesn't churn
  // every time the user opens or closes a tab — that previously cascaded
  // into re-registering the workspace-actions provider.
  const workspaceActionRuntime = useMemo<WorkspaceActionRuntime>(
    () => ({
      beginRename: (ws): void => setRenamingWorkspaceId(ws.objectId),
      closeWorkspace: (ws): void => handleClose(ws.objectId),
      closeOtherWorkspaces: (ws): void => handleCloseOthers(ws.objectId),
      closeAllWorkspaces: (): void => handleCloseAll(),
      beginDelete: (ws): void => setWorkspaceDeleteTarget({ id: ws.objectId, name: ws.description ?? "" }),
      canCloseOthers: (): boolean => (store.get(effectiveOpenTabIdsAtom) ?? []).length > 1,
      ...gitAndOpenIn,
    }),
    [
      store,
      setRenamingWorkspaceId,
      handleClose,
      handleCloseOthers,
      handleCloseAll,
      setWorkspaceDeleteTarget,
      gitAndOpenIn,
    ],
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
