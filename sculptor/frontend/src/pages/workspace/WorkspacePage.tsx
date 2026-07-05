import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { useWorkspaceTabActions } from "~/common/state/hooks/useWorkspaceTabActions.ts";

import { useImbueNavigate, useWorkspacePageParams } from "../../common/hooks/navigation.ts";
import { useIsMobile } from "../../common/hooks/useLayoutMode.ts";
import { markSwitchMilestone } from "../../common/perf/workspaceSwitchProfiler.ts";
import { workspaceAgentIdsWhenLoadedAtomFamily } from "../../common/state/agentPanelPlacement.ts";
import {
  agentIdForWorkspaceAtomFamily,
  isWorkspaceKnownAtomFamily,
  removeTabFromOrderAtom,
  setAgentForWorkspaceAtom,
} from "../../common/state/atoms/workspaces.ts";
import { useWorkspaceShellBootstrap } from "../../common/state/hooks/useWorkspaceShellBootstrap.ts";
import { useArtifactSync } from "./hooks/useArtifactSync.ts";
import { WorkspaceLayoutShell } from "./workspaceChrome/WorkspaceLayoutShell.tsx";

// The desktop shell, bootstrapped for the active workspace + agent: scope switch,
// registry sync, and center-agent placement happen here so the center renders the
// resolved agent's chat. `agentId` is undefined for a workspace with no agents,
// which renders the shell with an empty center. The mobile branch
// (MobileWorkspaceShell) is not built yet — useIsMobile is a no-op seam that
// always takes this path.
const WorkspacePageContent = ({ workspaceId, agentId }: { workspaceId: string; agentId?: string }): ReactElement => {
  // The bootstrap resolves which agent is being viewed (route vs. active panel);
  // sync that agent's artifacts here so `common/` never imports this workspace hook.
  // The empty id in an agentless workspace matches no agent, so the sync is a no-op.
  const viewedAgentId = useWorkspaceShellBootstrap({ workspaceId, agentId });
  useArtifactSync(workspaceId, viewedAgentId ?? "");

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
  const { navigateToAgent } = useImbueNavigate();
  const { navigateToNextTab } = useWorkspaceTabActions();
  const isMobile = useIsMobile();
  // Narrow per-workspace slices, never the raw workspace/agent arrays: those
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
      // The workspace backing this route is gone: deleted from another session,
      // or the active tab we just optimistically deleted while this route still
      // holds the stale param. Drop the now-stale tab and route through
      // navigateToNextTab (which falls back to Home when no tabs remain) so we
      // land on a surviving sibling instead of hard-coding Home.
      removeTab(workspaceID);
      navigateToNextTab(workspaceID);
      return;
    }
    if (agentIDFromUrl) return; // URL is authoritative, nothing to fix up
    if (agentIds === undefined) return; // agents haven't loaded; can't validate yet

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
    navigateToNextTab,
    setAgentForWorkspace,
    removeTab,
  ]);

  // The mobile shell is not built yet; the seam always resolves to desktop for now.
  if (isMobile) return null;
  if (agentIDFromUrl) {
    return <WorkspacePageContent workspaceId={workspaceID} agentId={agentIDFromUrl} />;
  }
  // No agent in the URL: a workspace that genuinely has no agents (e.g. created
  // headlessly) renders the shell with an empty center rather than a blank page.
  // Until the workspace and agent lists have loaded we can't tell "agentless" from
  // "still resolving" — render nothing for that brief window and let the fix-up
  // effect above navigate once an agent (or a stale-workspace redirect) resolves.
  const isAgentless = agentIds !== undefined && agentIds.length === 0;
  if (isKnownWorkspace !== true || !isAgentless) return null;
  return <WorkspacePageContent workspaceId={workspaceID} />;
};
