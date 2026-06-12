import { Flex, Select, Text } from "@radix-ui/themes";
import { FolderOpenIcon, PlusIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import type { Project } from "../api";
import { ElementIds } from "../api";
import { AddRepoDialog } from "./add-repo/AddRepoDialog.tsx";
import styles from "./RepoSelector.module.scss";
import type { ToastContent } from "./Toast.tsx";
import { Toast } from "./Toast.tsx";

const truncatePath = (path: string, maxLength: number = 50): string => {
  if (path.length <= maxLength) {
    return path;
  }
  const truncated = path.slice(-(maxLength - 4));
  const firstSlash = truncated.indexOf("/");
  if (firstSlash !== -1) {
    return ".../" + truncated.slice(firstSlash + 1);
  }
  return ".../" + truncated;
};

const _NEW_REPO_SELECT_VALUE = "_NEW_REPO_SELECT_VALUE";

type RepoSelectorProps = {
  projects: ReadonlyArray<Project>;
  selectedProjectId: string | null;
  onProjectChange: (projectId: string) => void;
  className?: string;
};

export const RepoSelector = ({
  projects,
  selectedProjectId,
  onProjectChange,
  className,
}: RepoSelectorProps): ReactElement => {
  const [toast, setToast] = useState<ToastContent | null>(null);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  const handleValueChange = (value: string): void => {
    if (value === _NEW_REPO_SELECT_VALUE) {
      setIsAddDialogOpen(true);
      return;
    }
    onProjectChange(value);
  };

  const currentProject = projects.find((p) => p.objectId === selectedProjectId);
  const displayName = currentProject?.name ?? "Select repo";

  return (
    <>
      <Select.Root
        size="1"
        value={selectedProjectId ?? undefined}
        onValueChange={handleValueChange}
        disabled={projects.length === 0}
      >
        <Select.Trigger variant="ghost" className={className} data-testid={ElementIds.PROJECT_SELECTOR}>
          <Flex align="center" gap="1">
            <FolderOpenIcon size={12} />
            <Text className={styles.selectorLabel}>repo</Text>
            <Text truncate size="1">
              {displayName}
            </Text>
          </Flex>
        </Select.Trigger>
        <Select.Content position="popper" side="bottom" sideOffset={5} className={styles.selectContent}>
          {projects.map((project) => {
            const fullPath = project.userGitRepoUrl?.replace(/^file:\/\//, "") ?? "";
            const displayPath = truncatePath(fullPath);

            return (
              <Select.Item
                key={project.objectId}
                value={project.objectId}
                data-testid={ElementIds.PROJECT_SELECT_ITEM}
                className={styles.repoItem}
              >
                <Flex direction="column" gap="0">
                  <Text weight="medium" className={styles.repoName}>
                    {project.name}
                  </Text>
                  {displayPath && (
                    <Text size="1" className={styles.repoPath}>
                      {displayPath}
                    </Text>
                  )}
                </Flex>
              </Select.Item>
            );
          })}
          <Select.Separator className={styles.newRepoSeparator} />
          <Select.Item value={_NEW_REPO_SELECT_VALUE} data-testid={ElementIds.OPEN_NEW_REPO_BUTTON}>
            <Flex direction="row" align="center" gapX="2">
              <PlusIcon size={16} />
              <Text>Open New Repo</Text>
            </Flex>
          </Select.Item>
        </Select.Content>
      </Select.Root>

      <AddRepoDialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen} setToast={setToast} />

      <Toast open={!!toast} onOpenChange={(open) => !open && setToast(null)} title={toast?.title} type={toast?.type} />
    </>
  );
};
