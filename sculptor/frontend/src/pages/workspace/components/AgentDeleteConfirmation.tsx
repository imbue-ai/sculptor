// Headless owner of the agent delete-confirmation dialog, driven by the
// shared agentDeleteTargetAtom (set from an agent tab's close button via the panel's
// onRequestClose, wired in useWorkspaceDynamicPanels). Confirming runs the optimistic
// agent delete (useOptimisticTaskDelete): the tab disappears instantly, a failed
// backend delete rolls back with an error toast + Retry. Deleting the
// currently-viewed agent navigates to a sibling agent so the user stays in the
// workspace; closing the LAST agent leaves the center empty — no auto-create.
// Mirrors the terminal close-confirmation wiring; rendered once by the workspace
// shell next to TerminalCloseConfirmation.

import { useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useOptimisticTaskDelete } from "~/common/state/hooks/useOptimisticTaskDelete.ts";
import { agentDeleteTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { closePanelAtom } from "~/components/sections/sectionActions.ts";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";

export const AgentDeleteConfirmation = (): ReactElement | null => {
  const [target, setTarget] = useAtom(agentDeleteTargetAtom);
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  // Read the task list lazily inside the delete callback via the store, never as a
  // subscription: tasksArrayAtom rebuilds on every per-task streaming tick, and this
  // shell-level dialog stays mounted for the whole workspace, so subscribing would
  // re-render it (and rebuild its callback chain) on every tick for data only needed
  // the moment a delete is confirmed.
  const store = useStore();
  const { navigateToAgent, navigateToRoot } = useImbueNavigate();
  const { agentId: activeAgentId } = useImbueLocation();

  // When the deleted agent is the one being viewed, move to a sibling agent so the
  // user stays in the workspace. When it was the last agent, navigate to root — the
  // center is left empty, NOT refilled with an auto-created agent.
  // Deleting a non-viewed agent leaves the current view untouched.
  const handleNavigateAfterDelete = useCallback(
    (taskId: string): void => {
      if (taskId !== activeAgentId || workspaceId === null) {
        return;
      }
      const workspaceAgents = (store.get(tasksArrayAtom) ?? [])
        .filter((task) => task.workspaceId === workspaceId)
        .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
      const deletedIndex = workspaceAgents.findIndex((task) => task.id === taskId);
      const remaining = workspaceAgents.filter((task) => task.id !== taskId);
      if (remaining.length === 0) {
        navigateToRoot();
        return;
      }
      const nextAgent = remaining[Math.min(deletedIndex, remaining.length - 1)];
      navigateToAgent(workspaceId, nextAgent.id);
    },
    [activeAgentId, workspaceId, store, navigateToAgent, navigateToRoot],
  );

  const { execute } = useOptimisticTaskDelete({
    workspaceId: workspaceId ?? "",
    onNavigateAfterDelete: handleNavigateAfterDelete,
  });
  const closePanel = useSetAtom(closePanelAtom);

  const handleConfirm = useCallback((): void => {
    if (target === null) {
      return;
    }
    execute(target.id, target.name);
    // Unplace the agent's panel from the layout and reassign its section's active tab to
    // a sibling — mirrors TerminalCloseConfirmation. Route navigation only reassigns the
    // section when the deleted agent is the routed one; deleting the tab that is active
    // in its section (but not the routed agent, e.g. after switching via the tab bar)
    // would otherwise leave activePanel pointing at the now-gone panel, dropping the
    // section to the empty state even though sibling agents remain.
    closePanel({ panelId: makeAgentPanelId(target.id) });
    setTarget(null);
  }, [target, execute, closePanel, setTarget]);

  if (workspaceId === null) {
    return null;
  }

  return (
    <DeleteConfirmationDialog
      isOpen={target !== null}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          setTarget(null);
        }
      }}
      entityType="agent"
      entityName={target?.name ?? ""}
      onConfirm={handleConfirm}
    />
  );
};
