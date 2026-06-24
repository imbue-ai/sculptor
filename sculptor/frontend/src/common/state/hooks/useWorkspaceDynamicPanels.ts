// minimal cutover bootstrap; Task 6.1/6.2 expand to full default layout + seamless switch
//
// Keeps the panel registry in sync with the active workspace's agents AND terminals.
// It derives one agent:<taskId> panel per task and one terminal:<wsId>:<index> panel
// per persisted terminal tab in the workspace, then writes the registry (static +
// dynamic). Each terminal carries an onRequestClose that opens the close-confirmation
// dialog (TERM-02) via terminalCloseTargetAtom; the dialog itself is rendered by
// TerminalCloseConfirmation in the shell. Task 6.2 expands this with agent diagnostics
// and the agent onRequestClose delete wiring.

import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useMemo } from "react";

import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { terminalCloseTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import type { DynamicAgentInput, DynamicTerminalInput } from "~/components/sections/registry/dynamicPanels.tsx";
import { deriveDynamicPanels, makeTerminalPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { buildStaticPanelDefinitions, panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";

export const useWorkspaceDynamicPanels = (workspaceId: string): void => {
  const tasks = useAtomValue(tasksArrayAtom);
  const allTerminalTabs = useAtomValue(terminalTabStateAtom);
  const setPanelRegistry = useSetAtom(panelRegistryAtom);
  const setTerminalCloseTarget = useSetAtom(terminalCloseTargetAtom);

  // Map this workspace's tasks to the agent inputs the registry derives panels from.
  // Memoized on the workspace's task identity/title/status/read fields so the effect
  // below only refires when something the registry actually depends on changes.
  const agents = useMemo<ReadonlyArray<DynamicAgentInput>>(() => {
    return (tasks ?? [])
      .filter((task) => task.workspaceId === workspaceId)
      .map((task) => ({
        taskId: task.id,
        displayName: task.title ?? task.titleOrSomethingLikeIt,
        status: task.status,
        lastReadAt: task.lastReadAt,
        updatedAt: task.updatedAt,
      }));
  }, [tasks, workspaceId]);

  // Map this workspace's persisted terminal tabs to terminal inputs. Each tab's label
  // already reflects the lowest-available-number reuse (TERM-03) the old panel applied
  // when creating it, so numbering stays in one place. onRequestClose opens the close
  // confirmation (TERM-02) rather than tearing the terminal down directly.
  const terminals = useMemo<ReadonlyArray<DynamicTerminalInput>>(() => {
    const workspaceTabs = allTerminalTabs[workspaceId] ?? [];
    return workspaceTabs.map((tab) => ({
      workspaceId,
      index: tab.index,
      displayName: tab.label,
      onRequestClose: (): void =>
        setTerminalCloseTarget({
          panelId: makeTerminalPanelId(workspaceId, tab.index),
          workspaceId,
          index: tab.index,
          tabId: tab.id,
          name: tab.label,
        }),
    }));
  }, [allTerminalTabs, workspaceId, setTerminalCloseTarget]);

  useEffect(() => {
    const dynamicDefinitions = deriveDynamicPanels(agents, terminals);
    setPanelRegistry([...buildStaticPanelDefinitions(), ...dynamicDefinitions]);
  }, [agents, terminals, setPanelRegistry]);
};
