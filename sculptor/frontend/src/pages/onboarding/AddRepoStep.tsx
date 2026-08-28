import { Box, Button, Flex, Spinner, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ElementIds, getDependenciesStatus } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { AddRepoForm } from "~/components/addRepo/AddRepoForm.tsx";
import { CloneProgressBody, CloneTitleContent } from "~/components/addRepo/CloneProgressView.tsx";
import { useAddRepo } from "~/components/addRepo/hooks/useAddRepo.tsx";
import type { RemoteCloneSubmit, RemoteRepoFormView } from "~/components/addRepo/RemoteRepoForm.tsx";
import { RemoteRepoForm } from "~/components/addRepo/RemoteRepoForm.tsx";
import { RepoValidationDialog } from "~/components/addRepo/RepoValidationDialog.tsx";
import type { AddRepoSource, RemoteProvider } from "~/components/addRepo/SourceRadioCards.tsx";
import { SourceRadioCards } from "~/components/addRepo/SourceRadioCards.tsx";
import { useDirectoryListing } from "~/components/pathAutocomplete/hooks/useDirectoryListing.ts";

import styles from "./OnboardingWizard.module.scss";

const noopSetToast = (): void => {};

const isRemoteProvider = (mode: AddRepoSource): mode is RemoteProvider => mode === "github";

// Per-provider form state, mirroring AddRepoDialog so switching radio cards
// preserves each form's submit payload and "search" / "url" view.
type PerProviderState = {
  submit: { ready: boolean; payload?: RemoteCloneSubmit };
  view: RemoteRepoFormView;
};

const INITIAL_REMOTE_STATE: Record<RemoteProvider, PerProviderState> = {
  github: { submit: { ready: false }, view: "search" },
};

type AddRepoStepProps = {
  onComplete: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
};

export const AddRepoStep = ({ onComplete, isLoading, error }: AddRepoStepProps): ReactElement => {
  const [path, setPath] = useState("");
  const dangerColor = useThemeDangerColor();
  // Local is the default source (matching AddRepoDialog): adding a folder
  // already on disk needs no CLI install or auth, so first-run never opens
  // on NotConfiguredSection.
  const [mode, setMode] = useState<AddRepoSource>("local");
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

  // Re-fetch dependency status into the shared atom.
  // skipWsAck: the dependencies endpoint doesn't open a data-model
  // transaction, so it never produces the WS ack the SDK waits on by default.
  // Without this the call would time out at 10s and the GitHub form
  // would flash NotConfiguredSection.
  const refreshDependencies = useCallback(async (): Promise<void> => {
    try {
      const { data } = await getDependenciesStatus({ meta: { skipWsAck: true } });
      if (data) setDependenciesStatus(data);
    } catch {
      // Best-effort; the form falls back to NotConfiguredSection.
    }
  }, [setDependenciesStatus]);

  // Onboarding runs outside of PageLayout, so the unified stream isn't
  // populating the atom yet — refresh manually on mount.
  useEffect(() => {
    let isCancelled = false;
    // Genuine mount-time fetch from the backend; the synchronous setState is
    // only the loading-flag flip on an external-system sync, not derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsRefreshingDeps(true);
    void refreshDependencies().finally(() => {
      if (!isCancelled) setIsRefreshingDeps(false);
    });

    return (): void => {
      isCancelled = true;
    };
  }, [refreshDependencies]);

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
  const handleGithubViewChange = useCallback((next: RemoteRepoFormView): void => {
    setRemoteState((prev) => (prev.github.view === next ? prev : { ...prev, github: { ...prev.github, view: next } }));
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

        {/* Both forms stay mounted (display:none, not conditional render)
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
            onNotConfigured={refreshDependencies}
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
