import { useAtom, useAtomValue } from "jotai";
import { type ReactElement, useCallback, useEffect, useMemo } from "react";

import { useKeybindingHandler } from "~/common/keybindings";
import { keybindingsMapAtom } from "~/common/keybindings/atoms.ts";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { isDismissibleOverlayOpen } from "~/common/overlayUtils.ts";
import { shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useOptimisticTaskDelete } from "~/common/state/hooks/useOptimisticTaskDelete.ts";
import { useRegisterCommandAction } from "~/components/CommandPalette/commandActions.ts";
import { agentDeleteTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { CENTER_SECTION_ZONE } from "~/components/panels/sectionHooks.ts";
import { useAddPanelMenu } from "~/pages/workspace/panels/useAddPanelMenu.ts";

/**
 * Headless owner of the workspace-level agent commands that used to live in the
 * AgentTabs strip: the "new agent" keybinding, the Cmd+K create/next/previous
 * actions, the next/previous keyboard cycle, and the delete-confirmation dialog
 * (driven by the shared `agentDeleteTargetAtom` set from tab context menus and
 * the command palette). Rendered once per workspace.
 */
export const AgentWorkspaceCommands = (): ReactElement => {
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const tasks = useAtomValue(tasksArrayAtom);
  const keybindingsMap = useAtomValue(keybindingsMapAtom);
  const [deleteTarget, setDeleteTarget] = useAtom(agentDeleteTargetAtom);
  // New agents are created in the Center section, the default agent home.
  const { createAgent } = useAddPanelMenu(CENTER_SECTION_ZONE);

  const workspaceAgents = useMemo(() => {
    const agents = (tasks ?? []).filter((task) => task.workspaceId === workspaceID);
    return agents.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  }, [tasks, workspaceID]);

  useKeybindingHandler("new_agent", () => createAgent());
  useRegisterCommandAction("agent.create", createAgent);

  const cycleAgent = useCallback(
    (direction: 1 | -1): void => {
      const ids = workspaceAgents.map((a) => a.id);
      if (ids.length === 0) return;
      const currentIndex = agentID ? ids.indexOf(agentID) : -1;
      const nextIndex = (currentIndex + direction + ids.length) % ids.length;
      navigateToAgent(workspaceID, ids[nextIndex]);
    },
    [workspaceAgents, agentID, workspaceID, navigateToAgent],
  );

  useRegisterCommandAction(
    "agent.next",
    useCallback(() => cycleAgent(1), [cycleAgent]),
  );
  useRegisterCommandAction(
    "agent.previous",
    useCallback(() => cycleAgent(-1), [cycleAgent]),
  );

  useEffect(() => {
    const handleAgentCycle = (e: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) return;
      const nextBinding = keybindingsMap.next_agent.binding;
      const prevBinding = keybindingsMap.previous_agent.binding;
      let direction: 1 | -1 | null = null;
      if (nextBinding != null && shouldHandleKeybinding(e, nextBinding)) direction = 1;
      else if (prevBinding != null && shouldHandleKeybinding(e, prevBinding)) direction = -1;
      if (direction == null) return;
      e.preventDefault();
      cycleAgent(direction);
    };
    window.addEventListener("keydown", handleAgentCycle);
    return (): void => window.removeEventListener("keydown", handleAgentCycle);
  }, [keybindingsMap, cycleAgent]);

  const handleNavigateAfterDelete = useCallback(
    (deletedId: string): void => {
      if (deletedId !== agentID) return;
      const remaining = workspaceAgents.filter((a) => a.id !== deletedId);
      if (remaining.length > 0) {
        const deletedIndex = workspaceAgents.findIndex((a) => a.id === deletedId);
        const next = remaining[Math.min(deletedIndex, remaining.length - 1)];
        navigateToAgent(workspaceID, next.id);
      } else {
        createAgent();
      }
    },
    [agentID, workspaceAgents, workspaceID, navigateToAgent, createAgent],
  );

  const { execute: executeDelete } = useOptimisticTaskDelete({
    workspaceId: workspaceID,
    onNavigateAfterDelete: handleNavigateAfterDelete,
  });

  const handleDeleteConfirm = useCallback((): void => {
    if (!deleteTarget) return;
    executeDelete(deleteTarget.id, deleteTarget.name);
    setDeleteTarget(null);
  }, [deleteTarget, executeDelete, setDeleteTarget]);

  return (
    <DeleteConfirmationDialog
      isOpen={deleteTarget !== null}
      onOpenChange={(open) => {
        if (!open) setDeleteTarget(null);
      }}
      entityType="agent"
      entityName={deleteTarget?.name ?? ""}
      onConfirm={handleDeleteConfirm}
    />
  );
};
