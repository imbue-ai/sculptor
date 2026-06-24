import { useAtomValue, useSetAtom } from "jotai";
import { useCallback } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { setActiveTabByIdAtom, setAgentForWorkspaceAtom, workspaceAtomFamily } from "./state/atoms/workspaces";

type ImbueNavigationFunctions = {
  navigateToWorkspace: (workspaceID: string) => void;
  navigateToAgent: (workspaceID: string, agentID: string) => void;
  navigateToAddWorkspace: (draftId?: string) => void;
  navigateToHome: () => void;
  navigateToGlobalSettings: (section?: string) => void;
  navigateToRepoSetupCommand: (projectId: string) => void;
  navigateToComponentGallery: () => void;
  navigateToRoot: () => void;
};

export const useImbueNavigate = (): ImbueNavigationFunctions => {
  const navigate = useNavigate();
  const setActiveTabById = useSetAtom(setActiveTabByIdAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);

  return {
    navigateToWorkspace: useCallback(
      (workspaceID: string): void => {
        navigate(`/ws/${workspaceID}`);
      },
      [navigate],
    ),
    // Persist the active tab + agent synchronously, then change the URL. Keeping
    // both writes inside the navigation primitive means the URL and `tabsAtom`
    // (and therefore the `sculptor-tabs` localStorage entry) cannot diverge in
    // the window between navigation and `useSyncActiveTabFromRoute`'s effect —
    // which would otherwise let the rootLoader read a stale entry on cold start
    // and redirect to /ws/<wsId> instead of /ws/<wsId>/agent/<agentID>.
    navigateToAgent: useCallback(
      (workspaceID: string, agentID: string): void => {
        setActiveTabById(workspaceID);
        setAgentForWorkspace({ wsId: workspaceID, agentId: agentID });
        navigate(`/ws/${workspaceID}/agent/${agentID}`);
      },
      [navigate, setActiveTabById, setAgentForWorkspace],
    ),
    navigateToAddWorkspace: useCallback(
      // The legacy /ws/new page is gone; creation is the new-workspace modal. The
      // remaining callers are fallback redirects (e.g. landing on a since-deleted
      // workspace), so route them to Home — which shows the inline first-run form when
      // there are no workspaces, or the home landing where the modal can be opened.
      (_draftId?: string): void => {
        navigate(`/home`);
      },
      [navigate],
    ),
    navigateToHome: useCallback((): void => {
      navigate(`/home`);
    }, [navigate]),
    navigateToGlobalSettings: useCallback(
      (section?: string): void => {
        navigate(section ? `/settings?section=${section}` : `/settings`);
      },
      [navigate],
    ),
    navigateToRepoSetupCommand: useCallback(
      (projectId: string): void => {
        navigate(`/settings?section=repositories&focusRepo=${encodeURIComponent(projectId)}`);
      },
      [navigate],
    ),
    navigateToComponentGallery: useCallback((): void => {
      navigate(`/component-gallery`);
    }, [navigate]),
    navigateToRoot: useCallback((): void => {
      navigate(`/`);
    }, [navigate]),
  };
};

type ImbueLocationType = {
  isAgentRoute: boolean;
  isWorkspaceRoute: boolean;
  isAddWorkspaceRoute: boolean;
  addWorkspaceDraftId: string | null;
  isHomeRoute: boolean;
  isSettingsRoute: boolean;
  isComponentGalleryRoute: boolean;
  /** Parsed `workspaceId` from the current pathname, or null when not on a workspace/agent route. */
  workspaceId: string | null;
  /** Parsed agent (task) id from the current pathname, or null when not on an agent route. */
  agentId: string | null;
};

export const useImbueLocation = (): ImbueLocationType => {
  const location = useLocation();
  const pathname = location.pathname;

  const isAgentRoute = /^\/ws\/[^/]+\/agent\/[^/]+$/.test(pathname);
  const addWorkspaceMatch = pathname.match(/^\/ws\/new\/([^/]+)$/);
  const isAddWorkspaceRoute = /^\/ws\/new(\/[^/]+)?$/.test(pathname);
  const addWorkspaceDraftId = addWorkspaceMatch ? addWorkspaceMatch[1] : null;
  const isHomeRoute = /^\/home$/.test(pathname);
  const isSettingsRoute = /^\/settings$/.test(pathname);
  const isComponentGalleryRoute = /^\/component-gallery$/.test(pathname);
  // A "workspace route" means we're viewing a specific workspace (or one of
  // its agents). Excludes the new-workspace draft page (/ws/new/...).
  const isWorkspaceRoute = /^\/ws\/(?!new\b)[^/]+/.test(pathname);

  // Parse the workspace + agent ids from the path. We can't use `useParams`
  // here because `useImbueLocation` is called outside the matched <Route>
  // tree (e.g. from the global CommandPalette), so it has no params context.
  const workspaceMatch = pathname.match(/^\/ws\/(?!new\b)([^/?]+)(?:\/agent\/([^/?]+))?/);
  const workspaceId = workspaceMatch ? (workspaceMatch[1] ?? null) : null;
  const agentId = workspaceMatch ? (workspaceMatch[2] ?? null) : null;

  return {
    isAgentRoute,
    isWorkspaceRoute,
    isAddWorkspaceRoute,
    addWorkspaceDraftId,
    isHomeRoute,
    isSettingsRoute,
    isComponentGalleryRoute,
    workspaceId,
    agentId,
  };
};

class ExpectedParamsNotFoundError extends Error {}

// Workspace-centric hooks

type WorkspaceURLParams = {
  workspaceID?: string;
  id?: string; // agent ID from /ws/:workspaceID/agent/:id
};

export type WorkspacePageParams = {
  workspaceID: string;
  agentID?: string;
};

export const useWorkspacePageParams = (): WorkspacePageParams => {
  const location = useLocation();
  const params = useParams<WorkspaceURLParams>();
  if (params.workspaceID === undefined || params.workspaceID === null) {
    throw new ExpectedParamsNotFoundError(
      `Expected URL ${location.pathname} to contain workspaceID but only extracted the following: ${JSON.stringify(params)}`,
    );
  }
  return {
    workspaceID: params.workspaceID,
    agentID: params.id,
  };
};

export const useActiveProjectID = (): string | null => {
  const params = useParams<WorkspaceURLParams>();
  const workspaceID = params.workspaceID;
  const workspace = useAtomValue(workspaceAtomFamily(workspaceID ?? ""));
  if (workspace === null) {
    return null;
  }
  return workspace.projectId;
};

/**
 * Returns the current project ID and task (agent) ID from URL params.
 *
 * On workspace routes (/ws/:workspaceID/agent/:id), derives projectID from
 * the workspace atom and maps the agent :id param to taskID.
 */
export type ImbueParams = {
  projectID?: string;
  taskID?: string;
};

export const useImbueParams = (): ImbueParams => {
  const params = useParams<WorkspaceURLParams>();
  const workspace = useAtomValue(workspaceAtomFamily(params.workspaceID ?? ""));
  return {
    projectID: workspace?.projectId,
    taskID: params.id,
  };
};
