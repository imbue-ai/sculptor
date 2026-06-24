// minimal cutover bootstrap; Task 6.1/6.2 expand to full default layout + seamless switch
//
// Keeps the panel registry in sync with the active workspace's agents. MINIMAL for
// the cutover: agents only — it derives one agent:<taskId> panel per task in the
// workspace and writes the registry (static + dynamic). Task 6.2 expands this with
// terminals, agent diagnostics, and the onRequestClose delete wiring.

import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useMemo } from "react";

import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import type { DynamicAgentInput } from "~/components/sections/registry/dynamicPanels.tsx";
import { deriveDynamicPanels } from "~/components/sections/registry/dynamicPanels.tsx";
import { buildStaticPanelDefinitions, panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";

export const useWorkspaceDynamicPanels = (workspaceId: string): void => {
  const tasks = useAtomValue(tasksArrayAtom);
  const setPanelRegistry = useSetAtom(panelRegistryAtom);

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

  useEffect(() => {
    const dynamicDefinitions = deriveDynamicPanels(agents, []);
    setPanelRegistry([...buildStaticPanelDefinitions(), ...dynamicDefinitions]);
  }, [agents, setPanelRegistry]);
};
