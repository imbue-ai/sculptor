import { useSetAtom } from "jotai";
import { useMemo } from "react";

import { activateAgentPanelAtom } from "../../common/state/agentPanelPlacement.ts";
import { useMarkUnreadMutation } from "../../common/state/mutations";
import { makeAgentPanelId } from "../sections/registry/dynamicPanels.tsx";
import { agentDeleteTargetAtom, palettePendingRenameAtom, workspaceDeleteTargetAtom } from "./contextActions/atoms.ts";
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
  const setPendingRename = useSetAtom(palettePendingRenameAtom);
  const setWorkspaceDeleteTarget = useSetAtom(workspaceDeleteTargetAtom);
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);
  const activateAgentPanel = useSetAtom(activateAgentPanelAtom);
  const { mutate: markUnreadMutate } = useMarkUnreadMutation();
  const gitAndOpenIn = useGitAndOpenInRuntime();

  // Identity-stable (jotai's `useSetAtom` returns stable refs; `gitAndOpenIn`
  // is memoized on `[store]`), so the runtime doesn't churn between renders.
  const workspaceActionRuntime = useMemo<WorkspaceActionRuntime>(
    () => ({
      // Renames are stashed, not started: the palette flushes the handoff from its
      // onCloseAutoFocus so the inline rename input never mounts inside the still-open
      // dialog's focus trap (see palettePendingRenameAtom).
      beginRename: (ws): void => setPendingRename({ kind: "workspace", workspaceId: ws.objectId }),
      beginDelete: (ws): void => setWorkspaceDeleteTarget({ id: ws.objectId, name: ws.description ?? "" }),
      ...gitAndOpenIn,
    }),
    [setPendingRename, setWorkspaceDeleteTarget, gitAndOpenIn],
  );

  const agentActionRuntime = useMemo<AgentActionRuntime>(
    () => ({
      markUnread: (agent): void => {
        if (agent.workspaceId == null) return;
        markUnreadMutate({ workspaceId: agent.workspaceId, agentId: agent.id });
      },
      // Activate the agent's panel immediately so its tab is mounted by the time
      // the rename starts, but stash the rename itself: the palette flushes the
      // handoff to agentRenameTargetAtom from its onCloseAutoFocus so the inline
      // rename input never mounts inside the still-open dialog's focus trap (see
      // palettePendingRenameAtom). Activation is scoped to the active workspace's
      // layout, so it keys off the task id alone.
      beginRename: (agent): void => {
        activateAgentPanel(agent.id);
        setPendingRename({ kind: "agent", panelId: makeAgentPanelId(agent.id) });
      },
      beginDelete: (agent): void => setAgentDeleteTarget({ id: agent.id, name: agent.title ?? "" }),
    }),
    [markUnreadMutate, activateAgentPanel, setPendingRename, setAgentDeleteTarget],
  );

  return { workspaceActionRuntime, agentActionRuntime };
};
