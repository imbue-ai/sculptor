import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { useIsMobile } from "../../common/hooks/useLayoutMode.ts";
import { useImbueNavigate, useWorkspacePageParams } from "../../common/NavigateUtils.ts";
import { markSwitchMilestone } from "../../common/perf/workspaceSwitchProfiler.ts";
import { workspaceAgentIdsWhenLoadedAtomFamily } from "../../common/state/agentPanelPlacement.ts";
import {
  agentIdForWorkspaceAtomFamily,
  isWorkspaceKnownAtomFamily,
  removeTabFromOrderAtom,
  setAgentForWorkspaceAtom,
} from "../../common/state/atoms/workspaces.ts";
import { useWorkspaceShellBootstrap } from "../../common/state/hooks/useWorkspaceShellBootstrap.ts";
import { WorkspaceLayoutShell } from "./WorkspaceLayoutShell.tsx";

// The desktop shell, bootstrapped for the active workspace + agent: scope switch,
// registry sync, and center-agent placement happen here so the center renders the
// resolved agent's chat. `taskId` is undefined for a workspace with no agents,
// which renders the shell with an empty center. The mobile branch
// (MobileWorkspaceShell) is not built yet — useIsMobile is a no-op seam that
// always takes this path.
const WorkspacePageContent = ({ workspaceId, taskId }: { workspaceId: string; taskId?: string }): ReactElement => {
  useWorkspaceShellBootstrap({ workspaceId, taskId });

  // Workspace-switch profiler: the content rendered with the
  // new workspace id; the bootstrap above has restored its persisted layout into
  // the section atoms. Reporting `layout-restored` lets the profiler schedule
  // `first-paint-after-restore` on its own (via an internal double-rAF) so the
  // start→first-paint window measures any stale-content / layout-shift gap.
  // Every mark is inert unless the profiler is opted in (dev-only by default).
  markSwitchMilestone("page-content-render");
  useEffect(() => {
    markSwitchMilestone("layout-restored");
  }, [workspaceId]);

  return <WorkspaceLayoutShell />;
};

export const WorkspacePage = (): ReactElement | null => {
  const { workspaceID, agentID: agentIDFromUrl } = useWorkspacePageParams();
  const { navigateToAgent, navigateToAddWorkspace } = useImbueNavigate();
  const isMobile = useIsMobile();
  // Narrow per-workspace slices, never the raw workspace/task arrays: those
  // rebuild on every streaming tick, and this component sits above the whole
  // shell subtree. Both slices keep the `undefined` loading state so the
  // gates below can tell "still resolving" from "genuinely absent".
  const isKnownWorkspace = useAtomValue(isWorkspaceKnownAtomFamily(workspaceID));
  const agentIds = useAtomValue(workspaceAgentIdsWhenLoadedAtomFamily(workspaceID));
  const savedAgentId = useAtomValue(agentIdForWorkspaceAtomFamily(workspaceID));
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);
  const removeTab = useSetAtom(removeTabFromOrderAtom);

  // Optimistic-render-then-validate: rootLoader has already redirected us to
  // the saved agent URL on cold start, so the common path is `agentIDFromUrl`
  // is set and we render the shell immediately. This effect only covers the
  // cleanup paths: stale workspace, stale or missing agent.
  useEffect(() => {
    if (isKnownWorkspace === undefined) return; // first WS snapshot hasn't arrived
    if (!isKnownWorkspace) {
      // Workspace was deleted between sessions — drop the tab and bail out.
      removeTab(workspaceID);
      navigateToAddWorkspace();
      return;
    }
    if (agentIDFromUrl) return; // URL is authoritative, nothing to fix up
    if (agentIds === undefined) return; // tasks haven't loaded; can't validate yet

    if (savedAgentId !== null && agentIds.includes(savedAgentId)) {
      navigateToAgent(workspaceID, savedAgentId);
      return;
    }
    const fallback = agentIds[0];
    if (fallback !== undefined) {
      setAgentForWorkspace({ wsId: workspaceID, agentId: fallback });
      navigateToAgent(workspaceID, fallback);
    }
  }, [
    workspaceID,
    agentIDFromUrl,
    isKnownWorkspace,
    agentIds,
    savedAgentId,
    navigateToAgent,
    navigateToAddWorkspace,
    setAgentForWorkspace,
    removeTab,
  ]);

  // The mobile shell is not built yet; the seam always resolves to desktop for now.
  if (isMobile) return null;
  if (agentIDFromUrl) {
    return <WorkspacePageContent workspaceId={workspaceID} taskId={agentIDFromUrl} />;
  }
  // No agent in the URL: a workspace that genuinely has no agents (e.g. created
  // headlessly) renders the shell with an empty center rather than a blank page.
  // Until the workspace and task lists have loaded we can't tell "agentless" from
  // "still resolving" — render nothing for that brief window and let the fix-up
  // effect above navigate once an agent (or a stale-workspace redirect) resolves.
  const isAgentless = agentIds !== undefined && agentIds.length === 0;
  if (isKnownWorkspace !== true || !isAgentless) return null;
  return <WorkspacePageContent workspaceId={workspaceID} />;
};
