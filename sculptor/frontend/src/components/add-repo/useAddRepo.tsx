import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";

import { createInitialCommit, initializeGitRepository, initializeProject, listProjects } from "~/api";
import { getErrorMessage, HTTPException } from "~/common/Errors.ts";
import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";
import { updateProjectsAtom } from "~/common/state/atoms/projects.ts";
import type { RepoValidationState } from "~/components/add-repo/RepoValidationDialog.tsx";
import { RepoValidationDialog } from "~/components/add-repo/RepoValidationDialog.tsx";
import type { ToastContent } from "~/components/Toast.tsx";
import { ToastType } from "~/components/Toast.tsx";
import { isElectron, selectProjectDirectory } from "~/electron/utils.ts";

type UseAddRepoResult = {
  handleOpenNewRepo: (path: string) => Promise<void>;
  handleBrowse: () => Promise<string | undefined>;
  canBrowse: boolean;
  isValidating: boolean;
  validationDialogs: ReactElement;
};

export const useAddRepo = ({
  setToast,
  onSuccess,
}: {
  setToast: (toast: ToastContent | null) => void;
  onSuccess?: () => void;
}): UseAddRepoResult => {
  const [validationState, setValidationState] = useState<RepoValidationState | undefined>(undefined);
  const [isAdding, setIsAdding] = useState<boolean>(false);
  const updateProjects = useSetAtom(updateProjectsAtom);

  const finalizeProject = useCallback(
    async (path: string): Promise<void> => {
      await initializeProject({ body: { projectPath: path } });
      const { data: projects } = await listProjects();
      updateProjects(projects);

      setValidationState(undefined);
      setIsAdding(false);
      onSuccess?.();
      setToast({ title: "Repository added successfully", type: ToastType.SUCCESS });
    },
    [updateProjects, setToast, onSuccess],
  );

  const handleOpenNewRepo = useCallback(
    async (path: string): Promise<void> => {
      setIsAdding(true);

      try {
        await finalizeProject(path);
      } catch (error) {
        setIsAdding(false);
        if (error instanceof HTTPException && error.status === 400 && error.detail.includes("not a git repository")) {
          setValidationState({ status: "not-git-repo", repoPath: path });
        } else if (error instanceof HTTPException && error.status === 409 && error.detail.includes("initial commit")) {
          setValidationState({ status: "empty-repo", repoPath: path });
        } else {
          setValidationState({
            status: "error",
            repoPath: path,
            errorMessage: getErrorMessage(error, "Failed to open repo"),
          });
        }
      }
    },
    [finalizeProject],
  );

  const handleInitializeGit = useCallback(async (): Promise<void> => {
    if (!validationState) return;
    const path = validationState.repoPath;
    setValidationState({ status: "initializing", repoPath: path });

    try {
      await initializeGitRepository({
        body: { projectPath: path },
        meta: { skipWsAck: true },
      });
      await finalizeProject(path);
    } catch (error) {
      setValidationState({
        status: "error",
        repoPath: path,
        errorMessage: getErrorMessage(error, "Failed to initialize git repository"),
      });
    }
  }, [validationState, finalizeProject]);

  const handleCreateInitialCommit = useCallback(async (): Promise<void> => {
    if (!validationState) return;
    const path = validationState.repoPath;
    setValidationState({ status: "initializing", repoPath: path });

    try {
      await createInitialCommit({
        body: { projectPath: path },
        meta: { skipWsAck: true },
      });
      await finalizeProject(path);
    } catch (error) {
      setValidationState({
        status: "error",
        repoPath: path,
        errorMessage: getErrorMessage(error, "Failed to create initial commit"),
      });
    }
  }, [validationState, finalizeProject]);

  const handleCancelValidation = useCallback((): void => {
    setValidationState(undefined);
  }, []);

  const canBrowse = isElectron() && getBackendCapabilities().canSelectLocalDir;

  const handleBrowse = useCallback(async (): Promise<string | undefined> => {
    try {
      const path = await selectProjectDirectory();
      return path ?? undefined;
    } catch (error) {
      console.error("Failed to select directory:", error);
      setToast({ title: "Failed to select directory", type: ToastType.ERROR });
      return undefined;
    }
  }, [setToast]);

  const validationDialogs =
    validationState !== undefined ? (
      <RepoValidationDialog
        isOpen
        state={validationState}
        onInitializeGit={handleInitializeGit}
        onCreateInitialCommit={handleCreateInitialCommit}
        onCancel={handleCancelValidation}
      />
    ) : (
      <></>
    );

  return {
    handleOpenNewRepo,
    handleBrowse,
    canBrowse,
    isValidating: isAdding || validationState !== undefined,
    validationDialogs,
  };
};
