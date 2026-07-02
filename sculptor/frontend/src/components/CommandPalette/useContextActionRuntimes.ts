import { useSetAtom } from "jotai";
import { useMemo } from "react";

import { markAgentUnreadAtom } from "../../common/state/atoms/unreadOverrides.ts";
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
  const markAgentUnread = useSetAtom(markAgentUnreadAtom);
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
      // Shares markAgentUnreadAtom with the panel-tab "Mark as unread" so both
      // paths record the unread override (which keeps useMarkRead's auto
      // mark-read from undoing the action) alongside the persisted update.
      markUnread: (agent): void => {
        if (agent.workspaceId == null) return;
        markAgentUnread({ workspaceId: agent.workspaceId, taskId: agent.id });
      },
      beginDelete: (agent): void => setAgentDeleteTarget({ id: agent.id, name: agent.title ?? "" }),
    }),
    [setRenamingAgentId, markAgentUnread, setAgentDeleteTarget],
  );

  return { workspaceActionRuntime, agentActionRuntime };
};
