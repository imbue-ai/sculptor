import { useSetAtom } from "jotai";
import { useCallback, useReducer } from "react";

import { cloneRemoteRepo, createInitialCommit, initializeGitRepository, initializeProject, listProjects } from "~/api";
import { getErrorMessage, HTTPException } from "~/common/Errors.ts";
import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";
import { updateProjectsAtom } from "~/common/state/atoms/projects.ts";
import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";
import { isElectron, selectProjectDirectory } from "~/electron/utils.ts";

import { stripGitSuffix } from "../utils/remoteRepoFormHelpers.ts";

type CloneAndOpenArgs = {
  provider: "github";
  url: string;
  targetDir: string;
  name: string;
  fullName?: string;
};

type FormPhase = { type: "form" };
type ValidatingPhase = { type: "validating"; repoPath: string };
type CloningPhase = {
  type: "cloning";
  repoPath: string;
  /** "owner/repo" (or a nested "group/sub/repo" path), shown in the progress card title. */
  displayName: string;
  /** https URL to the repo's web page; renders as a clickable link in the title. */
  webUrl?: string;
};
type InitializingPhase = { type: "initializing"; repoPath: string };
type NotGitRepoPhase = { type: "not-git-repo"; repoPath: string };
type EmptyRepoPhase = { type: "empty-repo"; repoPath: string };
type ErrorPhase = { type: "error"; repoPath: string; errorMessage: string };
type CloneFailedPhase = {
  type: "clone-failed";
  repoPath: string;
  errorMessage: string;
  /**
   * When set, the validation view offers a primary "Add as local folder" CTA
   * that imports this path through the existing local flow. Use an absolute,
   * already-expanded path so the displayed value matches what gets added.
   */
  localPathSuggestion?: string;
};

export type AddRepoPhase =
  | FormPhase
  | ValidatingPhase
  | CloningPhase
  | InitializingPhase
  | NotGitRepoPhase
  | EmptyRepoPhase
  | ErrorPhase
  | CloneFailedPhase;

export type AddRepoAction =
  | { type: "SUBMIT_STARTED"; repoPath: string }
  | { type: "START_CLONING"; repoPath: string; displayName: string; webUrl?: string }
  | { type: "START_INITIALIZING"; repoPath: string }
  | { type: "BACK_TO_FORM" }
  | { type: "NOT_GIT_REPO"; repoPath: string }
  | { type: "EMPTY_REPO"; repoPath: string }
  | { type: "ERROR"; repoPath: string; errorMessage: string }
  | { type: "CLONE_FAILED"; repoPath: string; errorMessage: string; localPathSuggestion?: string };

export const initialPhase: AddRepoPhase = { type: "form" };

/**
 * Extract "owner/repo" (or a nested "group/sub/repo" path) from a clone
 * URL. Accepts both HTTPS (`https://host/owner/repo.git`) and SSH
 * (`git@host:owner/repo.git`) shapes. Falls back to the trimmed input if the
 * URL doesn't match either — the caller still gets *something* renderable.
 */
export const deriveDisplayName = (url: string, fallbackName: string): string => {
  const trimmed = stripGitSuffix(url.trim());
  const sshMatch = trimmed.match(/^[^@\s]+@[^:]+:(.+)$/);
  if (sshMatch?.[1]) return sshMatch[1];
  const httpsMatch = trimmed.match(/^https?:\/\/[^/]+\/(.+)$/);
  if (httpsMatch?.[1]) return httpsMatch[1];
  return fallbackName;
};

/**
 * Build a web URL (https://host/owner/repo) the link in the progress card can
 * navigate to. SSH-form clone URLs get rewritten to https; HTTPS URLs just lose
 * the `.git` suffix. Returns undefined for unrecognized shapes so the title
 * falls back to plain text instead of linking to something invalid.
 */
export const deriveWebUrl = (url: string): string | undefined => {
  const trimmed = stripGitSuffix(url.trim());
  const sshMatch = trimmed.match(/^[^@\s]+@([^:]+):(.+)$/);
  if (sshMatch) return `https://${sshMatch[1]}/${sshMatch[2]}`;
  if (/^https?:\/\//.test(trimmed)) return trimmed;
  return undefined;
};

export const phaseReducer = (state: AddRepoPhase, action: AddRepoAction): AddRepoPhase => {
  switch (action.type) {
    case "SUBMIT_STARTED":
      return { type: "validating", repoPath: action.repoPath };
    case "START_CLONING":
      return {
        type: "cloning",
        repoPath: action.repoPath,
        displayName: action.displayName,
        webUrl: action.webUrl,
      };
    case "START_INITIALIZING":
      return { type: "initializing", repoPath: action.repoPath };
    case "BACK_TO_FORM":
      return { type: "form" };
    case "NOT_GIT_REPO":
      return { type: "not-git-repo", repoPath: action.repoPath };
    case "EMPTY_REPO":
      return { type: "empty-repo", repoPath: action.repoPath };
    case "ERROR":
      return { type: "error", repoPath: action.repoPath, errorMessage: action.errorMessage };
    case "CLONE_FAILED":
      return {
        type: "clone-failed",
        repoPath: action.repoPath,
        errorMessage: action.errorMessage,
        localPathSuggestion: action.localPathSuggestion,
      };
  }
};

type UseAddRepoResult = {
  phase: AddRepoPhase;
  isValidating: boolean;
  handleOpenNewRepo: (path: string) => Promise<void>;
  handleCloneAndOpen: (args: CloneAndOpenArgs) => Promise<void>;
  handleInitializeGit: () => Promise<void>;
  handleCreateInitialCommit: () => Promise<void>;
  handleOpenLocalFromClone: (path: string) => void;
  handleBackToForm: () => void;
  handleBrowse: () => Promise<string | undefined>;
  canBrowse: boolean;
};

export const useAddRepo = ({
  setToast,
  onSuccess,
}: {
  setToast: (toast: ToastContent | null) => void;
  onSuccess?: () => void;
}): UseAddRepoResult => {
  const [phase, dispatch] = useReducer(phaseReducer, initialPhase);
  const updateProjects = useSetAtom(updateProjectsAtom);

  const finalizeProject = useCallback(
    async (path: string): Promise<void> => {
      await initializeProject({ body: { projectPath: path } });
      const { data: projects } = await listProjects();
      updateProjects(projects);

      dispatch({ type: "BACK_TO_FORM" });
      onSuccess?.();
      setToast({ title: "Repository added successfully", type: ToastType.SUCCESS });
    },
    [updateProjects, setToast, onSuccess],
  );

  const handleOpenNewRepo = useCallback(
    async (path: string): Promise<void> => {
      dispatch({ type: "SUBMIT_STARTED", repoPath: path });

      try {
        await finalizeProject(path);
      } catch (error) {
        if (error instanceof HTTPException && error.status === 400 && error.detail.includes("not a git repository")) {
          dispatch({ type: "NOT_GIT_REPO", repoPath: path });
        } else if (error instanceof HTTPException && error.status === 409 && error.detail.includes("initial commit")) {
          dispatch({ type: "EMPTY_REPO", repoPath: path });
        } else {
          dispatch({ type: "ERROR", repoPath: path, errorMessage: getErrorMessage(error, "Failed to open repo") });
        }
      }
    },
    [finalizeProject],
  );

  const handleCloneAndOpen = useCallback(
    async ({ provider, url, targetDir, name, fullName }: CloneAndOpenArgs): Promise<void> => {
      const repoPath = `${targetDir}/${name}`;
      // Clones have their own phase so the dialog can swap the form for a
      // dedicated progress card. Local opens stay in `validating` because they
      // resolve in milliseconds and don't need a progress UI.
      const displayName = deriveDisplayName(url, name);
      const webUrl = deriveWebUrl(url);
      dispatch({ type: "START_CLONING", repoPath, displayName, webUrl });

      try {
        // skipWsAck: /api/v1/remotes/clone runs git clone synchronously without
        // opening a data-model transaction, so it never produces the WS ack the
        // SDK waits on by default. Without this, the call fails at the 10s ack
        // timeout even when the clone itself is still in progress.
        const { data } = await cloneRemoteRepo({
          body: { provider, url, targetDir, name, fullName },
          meta: { skipWsAck: true },
        });
        const projectPath = data?.projectPath ?? repoPath;
        await finalizeProject(projectPath);
      } catch (error) {
        if (error instanceof HTTPException && error.status === 409) {
          dispatch({
            type: "CLONE_FAILED",
            repoPath,
            errorMessage: "This folder already exists. Add it as a local folder instead?",
            localPathSuggestion: repoPath,
          });
        } else if (error instanceof HTTPException) {
          // Any other backend status (412 not signed in, 504 timeout, 400 bad
          // input) surfaces its detail. The "Add as local folder" hint is
          // intentionally omitted — only a 409 path conflict offers that CTA.
          dispatch({ type: "CLONE_FAILED", repoPath, errorMessage: error.detail });
        } else {
          // Network failures (the browser's "Failed to fetch" TypeError),
          // timeouts, or anything else where we couldn't reach the backend.
          // Don't speculate about whether the folder exists — the backend
          // pre-flights that and returns a 409 above when it does.
          const detail = error instanceof Error ? error.message : "Couldn't reach the backend.";
          dispatch({ type: "CLONE_FAILED", repoPath, errorMessage: detail });
        }
      }
    },
    [finalizeProject],
  );

  const handleInitializeGit = useCallback(async (): Promise<void> => {
    if (phase.type !== "not-git-repo") return;
    const path = phase.repoPath;
    dispatch({ type: "START_INITIALIZING", repoPath: path });

    try {
      await initializeGitRepository({
        body: { projectPath: path },
        meta: { skipWsAck: true },
      });
      await finalizeProject(path);
    } catch (error) {
      dispatch({
        type: "ERROR",
        repoPath: path,
        errorMessage: getErrorMessage(error, "Failed to initialize git repository"),
      });
    }
  }, [phase, finalizeProject]);

  const handleCreateInitialCommit = useCallback(async (): Promise<void> => {
    if (phase.type !== "empty-repo") return;
    const path = phase.repoPath;
    dispatch({ type: "START_INITIALIZING", repoPath: path });

    try {
      await createInitialCommit({
        body: { projectPath: path },
        meta: { skipWsAck: true },
      });
      await finalizeProject(path);
    } catch (error) {
      dispatch({
        type: "ERROR",
        repoPath: path,
        errorMessage: getErrorMessage(error, "Failed to create initial commit"),
      });
    }
  }, [phase, finalizeProject]);

  const handleBackToForm = useCallback((): void => {
    dispatch({ type: "BACK_TO_FORM" });
  }, []);

  const handleOpenLocalFromClone = useCallback(
    (path: string): void => {
      // handleOpenNewRepo dispatches SUBMIT_STARTED, which replaces the
      // clone-failed phase cleanly — no need to BACK_TO_FORM first.
      void handleOpenNewRepo(path);
    },
    [handleOpenNewRepo],
  );

  const canBrowse = isElectron() && getBackendCapabilities().canSelectLocalDir;

  const handleBrowse = useCallback(async (): Promise<string | undefined> => {
    try {
      const path = await selectProjectDirectory();
      return path ?? undefined;
    } catch {
      // The toast is the user-facing signal; no separate console log needed.
      setToast({ title: "Failed to select directory", type: ToastType.ERROR });
      return undefined;
    }
  }, [setToast]);

  return {
    phase,
    isValidating: phase.type !== "form",
    handleOpenNewRepo,
    handleCloneAndOpen,
    handleInitializeGit,
    handleCreateInitialCommit,
    handleOpenLocalFromClone,
    handleBackToForm,
    handleBrowse,
    canBrowse,
  };
};
