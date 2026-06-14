import { Box, Button, Flex, Spinner, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ElementIds, getDependenciesStatus } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { AddRepoForm } from "~/components/add-repo/AddRepoForm.tsx";
import { CloneProgressBody, CloneTitleContent } from "~/components/add-repo/CloneProgressView.tsx";
import type { RemoteCloneSubmit, RemoteRepoFormView } from "~/components/add-repo/RemoteRepoForm.tsx";
import { RemoteRepoForm } from "~/components/add-repo/RemoteRepoForm.tsx";
import { RepoValidationDialog } from "~/components/add-repo/RepoValidationDialog.tsx";
import type { AddRepoSource, RemoteProvider } from "~/components/add-repo/SourceRadioCards.tsx";
import { SourceRadioCards } from "~/components/add-repo/SourceRadioCards.tsx";
import { useAddRepo } from "~/components/add-repo/useAddRepo.tsx";
import { useDirectoryListing } from "~/components/path-autocomplete/useDirectoryListing.ts";

import styles from "./OnboardingWizard.module.scss";

const noopSetToast = (): void => {};

const isRemoteProvider = (mode: AddRepoSource): mode is RemoteProvider => mode === "github" || mode === "gitlab";

// Per-provider form state, mirroring AddRepoDialog so switching radio cards
// preserves each form's submit payload and "search" / "url" view.
type PerProviderState = {
  submit: { ready: boolean; payload?: RemoteCloneSubmit };
  view: RemoteRepoFormView;
};

const INITIAL_REMOTE_STATE: Record<RemoteProvider, PerProviderState> = {
  github: { submit: { ready: false }, view: "search" },
  gitlab: { submit: { ready: false }, view: "search" },
};

type AddRepoStepProps = {
  onComplete: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
};

export const AddRepoStep = ({ onComplete, isLoading, error }: AddRepoStepProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const [path, setPath] = useState("");
  const [mode, setMode] = useState<AddRepoSource>("github");
  const [remoteState, setRemoteState] = useState<Record<RemoteProvider, PerProviderState>>(INITIAL_REMOTE_STATE);
  // Onboarding runs outside of PageLayout, so the unified stream isn't
  // populating this atom yet — we refresh manually on mount below.
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);
  const [isRefreshingDeps, setIsRefreshingDeps] = useState(false);
  const { fetchDirectories } = useDirectoryListing();

  const {
    phase,
    isValidating,
    handleOpenNewRepo,
    handleCloneAndOpen,
    handleBrowse,
    canBrowse,
    handleInitializeGit,
    handleCreateInitialCommit,
    handleOpenLocalFromClone,
    handleBackToForm,
  } = useAddRepo({
    setToast: noopSetToast,
    onSuccess: onComplete,
  });

  // skipWsAck: the dependencies endpoint doesn't open a data-model
  // transaction, so it never produces the WS ack the SDK waits on by default.
  // Without this the call would time out at 10s and the GitHub/GitLab forms
  // would flash NotConfiguredSection.
  useEffect(() => {
    let isCancelled = false;
    setIsRefreshingDeps(true);
    void (async (): Promise<void> => {
      try {
        const { data } = await getDependenciesStatus({ meta: { skipWsAck: true } });
        if (!isCancelled && data) setDependenciesStatus(data);
      } catch {
        // Best-effort; the form falls back to NotConfiguredSection.
      } finally {
        if (!isCancelled) setIsRefreshingDeps(false);
      }
    })();

    return (): void => {
      isCancelled = true;
    };
  }, [setDependenciesStatus]);

  const currentRemoteSubmit = useMemo(
    () => (isRemoteProvider(mode) ? remoteState[mode].submit : { ready: false }),
    [mode, remoteState],
  );

  const handleAddClick = useCallback((): void => {
    if (mode === "local") {
      if (path.trim()) void handleOpenNewRepo(path.trim());
      return;
    }

    if (currentRemoteSubmit.ready && currentRemoteSubmit.payload) {
      void handleCloneAndOpen(currentRemoteSubmit.payload);
    }
  }, [mode, path, handleOpenNewRepo, currentRemoteSubmit, handleCloneAndOpen]);

  // Stable identity so RemoteRepoForm's effect handlers don't churn.
  const handleGithubSubmittableChange = useCallback((next: { ready: boolean; payload?: RemoteCloneSubmit }): void => {
    setRemoteState((prev) => ({ ...prev, github: { ...prev.github, submit: next } }));
  }, []);
  const handleGitlabSubmittableChange = useCallback((next: { ready: boolean; payload?: RemoteCloneSubmit }): void => {
    setRemoteState((prev) => ({ ...prev, gitlab: { ...prev.gitlab, submit: next } }));
  }, []);
  const handleGithubViewChange = useCallback((next: RemoteRepoFormView): void => {
    setRemoteState((prev) => (prev.github.view === next ? prev : { ...prev, github: { ...prev.github, view: next } }));
  }, []);
  const handleGitlabViewChange = useCallback((next: RemoteRepoFormView): void => {
    setRemoteState((prev) => (prev.gitlab.view === next ? prev : { ...prev, gitlab: { ...prev.gitlab, view: next } }));
  }, []);

  const handleLocalSubmit = useCallback(
    (value: string): void => {
      void handleOpenNewRepo(value);
    },
    [handleOpenNewRepo],
  );

  // The clone phase replaces the form with a progress card (matches
  // AddRepoDialog). All other in-flight phases either keep the form mounted
  // ("validating") or open RepoValidationDialog over the form ("not-git-repo",
  // "empty-repo", "error", "clone-failed", "initializing").
  if (phase.type === "cloning") {
    return (
      <Flex direction="column" gap="4" data-testid={ElementIds.ONBOARDING_ADD_REPO_STEP}>
        <Text className={styles.titleText}>
          <CloneTitleContent displayName={phase.displayName} webUrl={phase.webUrl} />
        </Text>
        <CloneProgressBody />
      </Flex>
    );
  }

  const isSubmitting = isValidating;
  const isSubmitDisabled = isSubmitting || isLoading || (mode === "local" ? !path.trim() : !currentRemoteSubmit.ready);
  const localOnBrowse = canBrowse ? handleBrowse : undefined;

  return (
    <>
      <Flex direction="column" gap="2" data-testid={ElementIds.ONBOARDING_ADD_REPO_STEP}>
        <Text className={styles.titleText}>Add your first repo</Text>
        <Text color="gray" className={styles.secondaryText}>
          Point Sculptor at a repository to get started.
        </Text>

        <Box mt="3">
          <SourceRadioCards value={mode} onValueChange={setMode} disabled={isSubmitting} />
        </Box>

        {/* All three forms stay mounted (display:none, not conditional render)
            so each preserves its internal state across radio-card switches. */}
        <Box mt="3" style={{ display: mode === "local" ? "block" : "none" }}>
          <AddRepoForm
            fetchDirectories={fetchDirectories}
            path={path}
            onPathChange={setPath}
            onSubmit={handleLocalSubmit}
            onBrowse={localOnBrowse}
            canBrowse={canBrowse}
            disabled={isSubmitting}
            showDescription={false}
          />
        </Box>
        <Box mt="3" style={{ display: mode === "github" ? "block" : "none" }}>
          <RemoteRepoForm
            provider="github"
            dependenciesStatus={dependenciesStatus}
            isLoadingDependencies={isRefreshingDeps}
            disabled={isSubmitting}
            view={remoteState.github.view}
            onViewChange={handleGithubViewChange}
            onSubmittableChange={handleGithubSubmittableChange}
          />
        </Box>
        <Box mt="3" style={{ display: mode === "gitlab" ? "block" : "none" }}>
          <RemoteRepoForm
            provider="gitlab"
            dependenciesStatus={dependenciesStatus}
            isLoadingDependencies={isRefreshingDeps}
            disabled={isSubmitting}
            view={remoteState.gitlab.view}
            onViewChange={handleGitlabViewChange}
            onSubmittableChange={handleGitlabSubmittableChange}
          />
        </Box>

        {error && (
          <Text size="2" color={dangerColor} className={styles.error}>
            {error}
          </Text>
        )}

        <Button
          mt="1"
          size="3"
          variant="solid"
          className={styles.primaryButton}
          disabled={isSubmitDisabled}
          onClick={handleAddClick}
          data-testid={ElementIds.ADD_REPO_SUBMIT_BUTTON}
        >
          {isSubmitting || isLoading ? <Spinner /> : "Add"}
        </Button>
      </Flex>

      {phase.type !== "form" && phase.type !== "validating" && (
        <RepoValidationDialog
          isOpen
          phase={phase}
          onInitializeGit={handleInitializeGit}
          onCreateInitialCommit={handleCreateInitialCommit}
          onCancel={handleBackToForm}
          onOpenLocal={handleOpenLocalFromClone}
        />
      )}
    </>
  );
};
