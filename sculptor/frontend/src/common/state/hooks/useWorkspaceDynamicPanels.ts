// minimal cutover bootstrap; Task 6.1/6.2 expand to full default layout + seamless switch
//
// Keeps the panel registry in sync with the active workspace's agents AND terminals.
// It derives one agent:<taskId> panel per task and one terminal:<wsId>:<index> panel
// per persisted terminal tab in the workspace, then writes the registry (static +
// dynamic). Each terminal carries an onRequestClose that opens the close-confirmation
// dialog (TERM-02) via terminalCloseTargetAtom; each agent carries an onRequestClose
// that opens the agent delete-confirmation dialog (AGENT-04) via agentDeleteTargetAtom
// plus diagnostics for its tab context-menu copy actions (AGENT-06). Both confirmation
// dialogs are rendered by the shell (TerminalCloseConfirmation / AgentDeleteConfirmation).

import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useMemo } from "react";

import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { agentDeleteTargetAtom, terminalCloseTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import type { DynamicAgentInput, DynamicTerminalInput } from "~/components/sections/registry/dynamicPanels.tsx";
import { deriveDynamicPanels, makeTerminalPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import {
  buildPluginPanelDefinitions,
  buildStaticPanelDefinitions,
  panelRegistryAtom,
} from "~/components/sections/registry/panelRegistry.ts";
import { pluginPanelsAtom } from "~/plugins/pluginRegistry.ts";

import { useWorkspaceAgentDiagnostics } from "./useWorkspaceAgentDiagnostics.ts";

export const useWorkspaceDynamicPanels = (workspaceId: string): void => {
  const tasks = useAtomValue(tasksArrayAtom);
  const allTerminalTabs = useAtomValue(terminalTabStateAtom);
  const pluginPanels = useAtomValue(pluginPanelsAtom);
  const setPanelRegistry = useSetAtom(panelRegistryAtom);
  const setTerminalCloseTarget = useSetAtom(terminalCloseTargetAtom);
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);

  // This workspace's tasks, narrowed to the identity/title/status/read fields the
  // registry derives panels from (so the memo below only refires when one changes).
  const workspaceTasks = useMemo(() => {
    return (tasks ?? []).filter((task) => task.workspaceId === workspaceId);
  }, [tasks, workspaceId]);

  // Lazily-fetched per-agent diagnostics (session id + transcript paths) powering the
  // tab context-menu copy actions (AGENT-06); refetched as an agent's status changes
  // so a session that appears after a prompt enables the copy items.
  const diagnosticsTargets = useMemo(
    () => workspaceTasks.map((task) => ({ taskId: task.id, status: task.status })),
    [workspaceTasks],
  );
  const diagnosticsByTaskId = useWorkspaceAgentDiagnostics(workspaceId, diagnosticsTargets);

  // Map this workspace's tasks to the agent inputs the registry derives panels from.
  const agents = useMemo<ReadonlyArray<DynamicAgentInput>>(() => {
    return workspaceTasks.map((task) => ({
      taskId: task.id,
      displayName: task.title ?? task.titleOrSomethingLikeIt,
      status: task.status,
      lastReadAt: task.lastReadAt,
      updatedAt: task.updatedAt,
      diagnostics: diagnosticsByTaskId[task.id],
      // Closing an agent tab deletes the agent with confirmation (AGENT-04); confirming
      // runs the optimistic delete + rollback + Retry flow (AGENT-08). Closing the last
      // agent leaves the center empty — no auto-create (Decision B1).
      onRequestClose: (): void => setAgentDeleteTarget({ id: task.id, name: task.title ?? "" }),
    }));
  }, [workspaceTasks, diagnosticsByTaskId, setAgentDeleteTarget]);

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
    // Merge plugin-contributed panels (PANEL-/plugin spec) into the rebuilt registry so
    // they survive every task-tick rebuild. A plugin panel whose id collides with a
    // static or dynamic panel loses (the host panel wins) so a plugin can't shadow a
    // built-in surface.
    const reservedIds = new Set([
      ...buildStaticPanelDefinitions().map((p) => p.id),
      ...dynamicDefinitions.map((p) => p.id),
    ]);
    const pluginDefinitions = buildPluginPanelDefinitions(pluginPanels.filter((panel) => !reservedIds.has(panel.id)));
    setPanelRegistry([...buildStaticPanelDefinitions(), ...pluginDefinitions, ...dynamicDefinitions]);
  }, [agents, terminals, pluginPanels, setPanelRegistry]);
};
