import { Box, Button, Dialog, Flex, Spinner, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ElementIds, getDependenciesStatus } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { useDirectoryListing } from "~/components/path-autocomplete/useDirectoryListing.ts";
import type { ToastContent } from "~/components/Toast.tsx";

import styles from "./AddRepoDialog.module.scss";
import { AddRepoForm } from "./AddRepoForm.tsx";
import { CloneProgressView } from "./CloneProgressView.tsx";
import { PROVIDER_META } from "./providerMeta.ts";
import type { RemoteCloneSubmit, RemoteRepoFormView } from "./RemoteRepoForm.tsx";
import { RemoteRepoForm } from "./RemoteRepoForm.tsx";
import { isRemoteFormShowingNotConfigured } from "./remoteRepoFormHelpers.ts";
import { RepoValidationView } from "./RepoValidationView.tsx";
import type { AddRepoSource, RemoteProvider } from "./SourceRadioCards.tsx";
import { SourceRadioCards } from "./SourceRadioCards.tsx";
import { useAddRepo } from "./useAddRepo.tsx";

type AddRepoDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  setToast: (toast: ToastContent | null) => void;
};

const isRemoteProvider = (mode: AddRepoSource): mode is RemoteProvider => mode === "github";

// Per-provider form state. `submit` is the form's readiness + payload for the
// dialog's submit button; `view` is the form's "search" / "url" toggle. These
// are always updated for the same provider, so we keep them in one record to
// avoid drifting state and to make the dialog's reset path a single setter.
type PerProviderState = {
  submit: { ready: boolean; payload?: RemoteCloneSubmit };
  view: RemoteRepoFormView;
};

const INITIAL_REMOTE_STATE: Record<RemoteProvider, PerProviderState> = {
  github: { submit: { ready: false }, view: "search" },
};

export const AddRepoDialog = ({ open, onOpenChange, setToast }: AddRepoDialogProps): ReactElement => {
  // internal state
  const [path, setPath] = useState<string>("");
  // Local is the default source: adding a folder already on disk needs no CLI
  // install or auth, so a fresh user is never greeted by NotConfiguredSection.
  const [mode, setMode] = useState<AddRepoSource>("local");
  // Shared atom: the WS stream and the dropdown's prefetch keep this populated
  // before the dialog opens, so we render the configured state on first paint
  // instead of flashing NotConfiguredSection while our first poll is in flight.
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);
  // Per-provider form state so switching radio cards preserves each form's
  // submit payload and "search" / "url" view. Owned here so the dialog footer
  // can derive the "Configure …" CTA without the form pushing notifications up.
  const [remoteState, setRemoteState] = useState<Record<RemoteProvider, PerProviderState>>(INITIAL_REMOTE_STATE);

  // hooks
  const navigate = useNavigate();
  const handleClose = useCallback(() => onOpenChange(false), [onOpenChange]);
  const {
    phase,
    isValidating,
    handleOpenNewRepo,
    handleCloneAndOpen,
    handleInitializeGit,
    handleCreateInitialCommit,
    handleOpenLocalFromClone,
    handleBackToForm,
    handleBrowse,
    canBrowse,
  } = useAddRepo({
    setToast,
    onSuccess: handleClose,
  });
  const { fetchDirectories } = useDirectoryListing();

  // `isRefreshingDeps` gates the form on a spinner so the radio cards don't
  // flash NotConfiguredSection while the first poll is in flight on dialogs
  // opened before the WS stream / dropdown prefetch populated the atom.
  const [isRefreshingDeps, setIsRefreshingDeps] = useState(false);

  // Prime the WS-pushed dependenciesStatus atom via a one-shot HTTP GET. This
  // deliberately departs from the usual "HTTP → TanStack, WS → atom" split:
  // the dialog opens during onboarding and before the unified stream is
  // connected, so there's no WS frame yet to populate the atom. We GET-then-
  // write so the real CLI state shows on first paint; the WS reconciles the
  // authoritative value once the stream is live.
  // skipWsAck: the dependencies endpoint doesn't open a data-model
  // transaction, so it never produces the WS acknowledgment the SDK
  // waits on by default. Without this the call times out at 10s and
  // dependenciesStatus stays null, leaving every provider stuck on
  // the NotConfiguredSection.
  const refreshDependencies = useCallback(async (): Promise<void> => {
    try {
      const { data } = await getDependenciesStatus({ meta: { skipWsAck: true } });
      if (data) setDependenciesStatus(data);
    } catch {
      // Best-effort; the form falls back to NotConfiguredSection.
    }
  }, [setDependenciesStatus]);

  // effects
  // Refresh dependency status when the dialog opens so the radio cards
  // reflect the current CLI install/auth state on first paint.
  useEffect(() => {
    if (!open) return;
    let isCancelled = false;
    // Genuine on-open fetch from the backend; the synchronous setState is only
    // the loading-flag flip on an external-system sync, not derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsRefreshingDeps(true);
    void refreshDependencies().finally(() => {
      if (!isCancelled) setIsRefreshingDeps(false);
    });

    return (): void => {
      isCancelled = true;
    };
  }, [open, refreshDependencies]);

  // callbacks
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

  const handleOpenChange = useCallback(
    (isOpen: boolean): void => {
      // Prevent closing while validating
      if (!isOpen && isValidating) return;
      onOpenChange(isOpen);
    },
    [onOpenChange, isValidating],
  );

  // Reset internal state when the parent flips us from closed to open.
  // Done in an effect (rather than inside handleOpenChange) so a stray
  // ``onOpenChange(true)`` fired by Radix while ``open`` is already true
  // — which can happen on focus/remount transitions while the dialog is
  // mid-flow — doesn't wipe the user's in-progress source selection.
  const prevOpenRef = useRef(open);
  useEffect(() => {
    if (open && !prevOpenRef.current) {
      setPath("");
      setMode("local");
      setRemoteState(INITIAL_REMOTE_STATE);
    }
    prevOpenRef.current = open;
  }, [open]);

  // Stable identity so the form's event handlers don't capture a new callback every render.
  const handleGithubSubmittableChange = useCallback((next: { ready: boolean; payload?: RemoteCloneSubmit }): void => {
    setRemoteState((prev) => ({ ...prev, github: { ...prev.github, submit: next } }));
  }, []);
  const handleGithubViewChange = useCallback((next: RemoteRepoFormView): void => {
    setRemoteState((prev) => (prev.github.view === next ? prev : { ...prev, github: { ...prev.github, view: next } }));
  }, []);

  // Rendering
  // `validating` keeps the form mounted with disabled inputs + a spinner on the
  // submit button. The dialog only swaps to RepoValidationView once we reach an
  // interactive error state or initializing (the post-confirm git init /
  // initial-commit run).
  const isSubmitting = phase.type === "validating";
  const isFormPhase = phase.type === "form" || phase.type === "validating";
  const isSubmitDisabled = isSubmitting || (mode === "local" ? !path.trim() : !currentRemoteSubmit.ready);
  const configureProvider: RemoteProvider | null =
    isRemoteProvider(mode) &&
    isRemoteFormShowingNotConfigured(dependenciesStatus, remoteState[mode].view, isRefreshingDeps)
      ? mode
      : null;
  const isConfigureCtaVisible = configureProvider !== null && !isSubmitting;

  // Pass the existing onBrowse wiring into AddRepoForm only in local mode.
  const localOnBrowse = canBrowse ? handleBrowse : undefined;

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Content maxWidth="520px" data-testid={ElementIds.ADD_REPO_DIALOG} className={styles.dialogContent}>
        {phase.type === "cloning" ? (
          <CloneProgressView displayName={phase.displayName} webUrl={phase.webUrl} />
        ) : isFormPhase ? (
          <>
            <Dialog.Title>
              <Text size="5" weight="bold">
                Add Repository
              </Text>
            </Dialog.Title>

            <Flex direction="column" gap="4" mt="4">
              <SourceRadioCards value={mode} onValueChange={setMode} disabled={isSubmitting} />

              {/* Both forms stay mounted (display:none, not conditional render)
                  so each preserves its internal state across radio-card switches. */}
              <Box style={{ display: mode === "local" ? "block" : "none" }}>
                <AddRepoForm
                  fetchDirectories={fetchDirectories}
                  path={path}
                  onPathChange={setPath}
                  onSubmit={handleOpenNewRepo}
                  onBrowse={localOnBrowse}
                  canBrowse={canBrowse}
                  disabled={isSubmitting}
                />
              </Box>
              <Box style={{ display: mode === "github" ? "block" : "none" }}>
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
            </Flex>

            <Flex gap="3" mt="5" justify="end">
              <Button variant="soft" color="gray" disabled={isSubmitting} onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              {isConfigureCtaVisible && configureProvider ? (
                <Button
                  variant="solid"
                  data-testid={ElementIds.ADD_REPO_CONFIGURE_CTA}
                  onClick={() => {
                    handleClose();
                    navigate(`/settings?section=DEPENDENCIES&cli=${PROVIDER_META[configureProvider].cliBinary}`);
                  }}
                >
                  Configure {PROVIDER_META[configureProvider].label}
                </Button>
              ) : (
                <Button
                  variant="solid"
                  data-testid={ElementIds.ADD_REPO_SUBMIT_BUTTON}
                  disabled={isSubmitDisabled}
                  onClick={handleAddClick}
                >
                  {isSubmitting ? (
                    <>
                      <Spinner size="2" />
                      Adding…
                    </>
                  ) : (
                    "Add Repository"
                  )}
                </Button>
              )}
            </Flex>
          </>
        ) : (
          <RepoValidationView
            phase={phase}
            onInitializeGit={handleInitializeGit}
            onCreateInitialCommit={handleCreateInitialCommit}
            onCancel={handleBackToForm}
            onOpenLocal={handleOpenLocalFromClone}
          />
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};
