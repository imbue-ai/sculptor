import { useCallback } from "react";

import type { Project, Workspace } from "~/api";
import { resolveWorkspaceSetupCommand } from "~/common/setupDefaults";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings";
import { useProject } from "~/common/state/hooks/useProjects";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";

type SetupCommandActions = {
  workspace: Workspace | null;
  project: Project | null;
  /** The project's current command, tri-state-resolved (null = run nothing). */
  currentCommand: string | null;
  handleCancel: () => Promise<void>;
  handleRerun: () => Promise<void>;
  handleEdit: () => void;
};

const postNoBody = async (path: string): Promise<Response> => fetch(path, { method: "POST" });

/**
 * Shared cancel / rerun / edit handlers and current-command resolution for the
 * workspace setup command. Used by both the chat-intro config affordance
 * (`SetupStatusCard`) and the run-status segment in the workspace banner
 * (`WorkspaceSetupStatus`) so the two don't drift.
 */
export function useSetupCommandActions(workspaceId: string): SetupCommandActions {
  const workspace = useWorkspace(workspaceId);
  const project = useProject(workspace?.projectId ?? "");
  const openSettings = useOpenSettings();

  const handleCancel = useCallback(async () => {
    try {
      await postNoBody(`/api/v1/workspaces/${workspaceId}/setup/cancel`);
    } catch (err) {
      console.error("Failed to cancel setup:", err);
    }
  }, [workspaceId]);

  const handleRerun = useCallback(async () => {
    try {
      await postNoBody(`/api/v1/workspaces/${workspaceId}/setup/rerun`);
    } catch (err) {
      console.error("Failed to rerun setup:", err);
    }
  }, [workspaceId]);

  const handleEdit = useCallback((): void => {
    if (project?.objectId) {
      openSettings("repositories", project.objectId);
    } else {
      openSettings("repositories");
    }
  }, [project?.objectId, openSettings]);

  // Mirror the backend's tri-state resolution: a null stored value runs the
  // current default ("git fetch origin ..."), an empty string means the user
  // cleared it (run nothing), any other string is custom.
  const currentCommand = resolveWorkspaceSetupCommand(project?.workspaceSetupCommand);

  return { workspace, project, currentCommand, handleCancel, handleRerun, handleEdit };
}
