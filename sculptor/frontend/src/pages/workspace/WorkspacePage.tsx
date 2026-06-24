import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useMemo } from "react";

import { useIsMobile } from "../../common/hooks/useLayoutMode.ts";
import { useImbueNavigate, useWorkspacePageParams } from "../../common/NavigateUtils.ts";
import { markSwitchMilestone } from "../../common/perf/workspaceSwitchProfiler.ts";
import { tasksArrayAtom } from "../../common/state/atoms/tasks.ts";
import {
  agentIdForWorkspaceAtomFamily,
  removeTabFromOrderAtom,
  setAgentForWorkspaceAtom,
  workspaceIdsAtom,
} from "../../common/state/atoms/workspaces.ts";
import { useWorkspaceShellBootstrap } from "../../common/state/hooks/useWorkspaceShellBootstrap.ts";
import { WorkspaceLayoutShell } from "./WorkspaceLayoutShell.tsx";

// The desktop shell, bootstrapped for the active workspace + agent: scope switch,
// registry sync, and center-agent placement happen here so the center renders the
// resolved agent's chat. The mobile branch (MobileWorkspaceShell) is not built yet
// — useIsMobile is a no-op seam that always takes this path.
const WorkspacePageContent = ({ workspaceId, taskId }: { workspaceId: string; taskId: string }): ReactElement => {
  useWorkspaceShellBootstrap({ workspaceId, taskId });

  // Workspace-switch profiler (SWITCH-01 / SEC-18): the content rendered with the
  // new workspace id; the bootstrap above has restored its persisted layout into
  // the section atoms, and a double-rAF approximates the first painted frame so
  // the start→first-paint window measures any stale-content / layout-shift gap.
  // Every mark is inert unless the profiler is opted in (dev-only by default).
  markSwitchMilestone("page-content-render");
  useEffect(() => {
    markSwitchMilestone("layout-restored");
    let secondRaf = 0;
    const firstRaf = requestAnimationFrame(() => {
      secondRaf = requestAnimationFrame(() => markSwitchMilestone("first-paint-after-restore"));
    });
    return (): void => {
      cancelAnimationFrame(firstRaf);
      if (secondRaf) cancelAnimationFrame(secondRaf);
    };
  }, [workspaceId]);

  return <WorkspaceLayoutShell />;
};

export const WorkspacePage = (): ReactElement | null => {
  const { workspaceID, agentID: agentIDFromUrl } = useWorkspacePageParams();
  const { navigateToAgent, navigateToAddWorkspace } = useImbueNavigate();
  const isMobile = useIsMobile();
  const tasks = useAtomValue(tasksArrayAtom);
  const workspaceIds = useAtomValue(workspaceIdsAtom);
  const savedAgentIdAtom = useMemo(() => agentIdForWorkspaceAtomFamily(workspaceID), [workspaceID]);
  const savedAgentId = useAtomValue(savedAgentIdAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);
  const removeTab = useSetAtom(removeTabFromOrderAtom);

  // Optimistic-render-then-validate: rootLoader has already redirected us to
  // the saved agent URL on cold start, so the common path is `agentIDFromUrl`
  // is set and we render the shell immediately. This effect only covers the
  // cleanup paths: stale workspace, stale or missing agent.
  useEffect(() => {
    if (workspaceIds === undefined) return; // first WS snapshot hasn't arrived
    if (!workspaceIds.includes(workspaceID)) {
      // Workspace was deleted between sessions — drop the tab and bail out.
      removeTab(workspaceID);
      navigateToAddWorkspace();
      return;
    }
    if (agentIDFromUrl) return; // URL is authoritative, nothing to fix up
    if (tasks === undefined) return; // tasks haven't loaded; can't validate yet

    const workspaceTasks = tasks.filter((task) => task.workspaceId === workspaceID);
    if (savedAgentId !== null && workspaceTasks.some((task) => task.id === savedAgentId)) {
      navigateToAgent(workspaceID, savedAgentId);
      return;
    }
    const fallback = workspaceTasks[0];
    if (fallback) {
      setAgentForWorkspace({ wsId: workspaceID, agentId: fallback.id });
      navigateToAgent(workspaceID, fallback.id);
    }
  }, [
    workspaceID,
    agentIDFromUrl,
    workspaceIds,
    tasks,
    savedAgentId,
    navigateToAgent,
    navigateToAddWorkspace,
    setAgentForWorkspace,
    removeTab,
  ]);

  if (!agentIDFromUrl) return null;
  // The mobile shell is not built yet (component_hierarchy.md → "Mobile shell
  // variant"); the seam always resolves to desktop for now.
  if (isMobile) return null;
  return <WorkspacePageContent workspaceId={workspaceID} taskId={agentIDFromUrl} />;
};
