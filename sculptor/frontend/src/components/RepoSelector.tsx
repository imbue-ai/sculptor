import { Flex, Select, Text } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import { FolderOpenIcon, PlusIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";

import type { Project } from "../api";
import { ElementIds, getDependenciesStatus } from "../api";
import { dependenciesStatusAtom } from "../common/state/atoms/dependenciesStatus.ts";
import { AddRepoDialog } from "./add-repo/AddRepoDialog.tsx";
import { prefetchInitialRemoteRepos } from "./add-repo/useRemoteRepos.ts";
import styles from "./RepoSelector.module.scss";
import type { ToastContent } from "./Toast.tsx";
import { Toast } from "./Toast.tsx";

const PATH_ELLIPSIS = ".../";

const truncatePath = (path: string, maxLength: number = 50): string => {
  if (path.length <= maxLength) {
    return path;
  }
  const truncated = path.slice(-(maxLength - PATH_ELLIPSIS.length));
  const firstSlash = truncated.indexOf("/");
  if (firstSlash !== -1) {
    return PATH_ELLIPSIS + truncated.slice(firstSlash + 1);
  }
  return PATH_ELLIPSIS + truncated;
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
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);

  const handleValueChange = (value: string): void => {
    if (value === _NEW_REPO_SELECT_VALUE) {
      setIsAddDialogOpen(true);
      return;
    }
    onProjectChange(value);
  };

  const handleToastOpenChange = useCallback((open: boolean): void => {
    if (!open) {
      setToast(null);
    }
  }, []);

  // Warm caches when the user pops open the repo dropdown so the Add
  // Repository dialog paints with real data on first frame:
  //   1. Dependencies status → skips the NotConfiguredSection flash while the
  //      dialog's own first poll is in flight.
  //   2. github/gitlab initial repo lists → the search combobox paints with
  //      results instead of a spinner. Fired in parallel; 412 (unconfigured
  //      CLI) is harmless since the combobox doesn't mount for that provider.
  // All best-effort; on failure the dialog falls back to its own fetches.
  const handleSelectOpenChange = useCallback(
    (isOpen: boolean): void => {
      if (!isOpen) return;
      void (async (): Promise<void> => {
        try {
          const { data } = await getDependenciesStatus({ meta: { skipWsAck: true } });
          if (data) setDependenciesStatus(data);
        } catch {
          // Dialog's own poll will retry on open.
        }
      })();
      void prefetchInitialRemoteRepos("github");
      void prefetchInitialRemoteRepos("gitlab");
    },
    [setDependenciesStatus],
  );

  const currentProject = projects.find((p) => p.objectId === selectedProjectId);
  const displayName = currentProject?.name ?? "Select repo";

  return (
    <>
      <Select.Root
        size="1"
        value={selectedProjectId ?? undefined}
        onValueChange={handleValueChange}
        onOpenChange={handleSelectOpenChange}
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
              <Text>Add new repository</Text>
            </Flex>
          </Select.Item>
        </Select.Content>
      </Select.Root>

      <AddRepoDialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen} setToast={setToast} />

      <Toast open={!!toast} onOpenChange={handleToastOpenChange} title={toast?.title} type={toast?.type} />
    </>
  );
};
