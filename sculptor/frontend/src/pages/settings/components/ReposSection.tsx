import { Box, Button, Separator, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { PlusIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { deleteProject, ElementIds, type Project } from "~/api";
import { agentsArrayAtom } from "~/common/state/atoms/agents.ts";
import { removeProjectAtom } from "~/common/state/atoms/projects.ts";
import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";
import { useProjects } from "~/common/state/hooks/useProjects.ts";
import { getErrorMessage } from "~/common/utils/errors.ts";
import { AddRepoDialog } from "~/components/addRepo/AddRepoDialog.tsx";

import { RemoveRepoDialog } from "./RemoveRepoDialog.tsx";
import { RepoRow } from "./RepoRow.tsx";
import styles from "./ReposSection.module.scss";
import { SettingsSectionLayout } from "./SettingsSection.tsx";

type RemoveDialogState =
  | { status: "closed" }
  | { status: "confirming"; projectId: string; projectName: string; agentCount: number }
  | { status: "deleting"; projectId: string; projectName: string; agentCount: number };

export const ReposSection = ({ setToast }: { setToast: (toast: ToastContent | null) => void }): ReactElement => {
  const projects = useProjects();
  const [searchParams] = useSearchParams();
  const focusRepoId = searchParams.get("focusRepo");
  const allAgents = useAtomValue(agentsArrayAtom);
  const removeProjectFromState = useSetAtom(removeProjectAtom);
  const [removeDialogState, setRemoveDialogState] = useState<RemoveDialogState>({ status: "closed" });
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  // Derive agent counts from global agents atom (grouped by project via workspace)
  const agentCounts = useMemo(() => {
    const agents = allAgents ?? [];
    const counts: Record<string, number> = {};
    for (const project of projects) {
      const projectAgents = agents.filter((agent) => agent.projectId === project.objectId && !agent.isDeleted);
      counts[project.objectId] = projectAgents.length;
    }
    return counts;
  }, [projects, allAgents]);

  const handleRemoveClick = useCallback(
    (project: Project) => {
      const count = agentCounts[project.objectId] ?? 0;
      setRemoveDialogState({
        status: "confirming",
        projectId: project.objectId,
        projectName: project.name,
        agentCount: count,
      });
    },
    [agentCounts],
  );

  const handleRemoveConfirm = useCallback(async () => {
    if (removeDialogState.status !== "confirming") return;

    const { projectId, projectName, agentCount } = removeDialogState;
    setRemoveDialogState({ status: "deleting", projectId, projectName, agentCount });

    try {
      await deleteProject({
        path: { project_id: projectId },
      });
      removeProjectFromState(projectId);

      // If this was the last repo, reload so RequireOnboarding redirects to the add-repo step.
      if (projects.length === 1) {
        window.location.reload();
        return;
      }

      setRemoveDialogState({ status: "closed" });

      setToast({
        type: ToastType.SUCCESS,
        title: "Repository removed successfully",
      });
    } catch (error) {
      setToast({
        type: ToastType.ERROR,
        title: getErrorMessage(error, "Failed to remove repository"),
      });
      setRemoveDialogState({ status: "confirming", projectId, projectName, agentCount });
    }
  }, [removeDialogState, setToast, removeProjectFromState, projects.length]);

  const handleRemoveCancel = useCallback(() => {
    if (removeDialogState.status === "deleting") return;
    setRemoveDialogState({ status: "closed" });
  }, [removeDialogState.status]);

  return (
    <>
      <SettingsSectionLayout description="Add or remove repositories from Sculptor.">
        {projects.length === 0 ? (
          <Box className={styles.emptyState}>
            <Text size="2">No repositories found. Open a repository to get started.</Text>
          </Box>
        ) : (
          <Box className={styles.reposList}>
            {projects.map((project) => {
              const count = agentCounts[project.objectId] ?? 0;
              const projectPath = project.userGitRepoUrl?.replace("file://", "") ?? "";
              const shouldAutoFocusSetupCommand = focusRepoId === project.objectId;
              return (
                <RepoRow
                  key={project.objectId}
                  projectId={project.objectId}
                  projectName={project.name}
                  projectPath={projectPath}
                  agentCount={count}
                  isPathAccessible={project.isPathAccessible ?? false}
                  onRemove={() => handleRemoveClick(project)}
                  shouldAutoFocusSetupCommand={shouldAutoFocusSetupCommand}
                  workspaceSetupCommand={project.workspaceSetupCommand ?? null}
                  namingPattern={project.namingPattern ?? ""}
                  setToast={setToast}
                />
              );
            })}
          </Box>
        )}
        {projects.length > 0 && <Separator size="4" className={styles.separator} />}
        <Box>
          <Button
            variant="solid"
            onClick={() => setIsAddDialogOpen(true)}
            data-testid={ElementIds.SETTINGS_ADD_REPO_BUTTON}
          >
            <PlusIcon size={14} />
            Add new repository
          </Button>
        </Box>
      </SettingsSectionLayout>

      <AddRepoDialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen} setToast={setToast} />

      <RemoveRepoDialog
        isOpen={removeDialogState.status !== "closed"}
        onClose={handleRemoveCancel}
        onConfirm={handleRemoveConfirm}
        projectName={removeDialogState.status !== "closed" ? removeDialogState.projectName : ""}
        agentCount={removeDialogState.status !== "closed" ? removeDialogState.agentCount : 0}
        isDeleting={removeDialogState.status === "deleting"}
      />
    </>
  );
};
