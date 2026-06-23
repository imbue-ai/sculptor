import { Box, Button, Checkbox, Flex, Link, Spinner, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement, Ref } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { DependenciesStatus } from "~/api";
import { ElementIds } from "~/api";
import { defaultClonesDirAtom, getBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";
import { defaultCloneTargetDirAtom } from "~/common/state/atoms/userConfig.ts";
import { PathAutocomplete } from "~/components/path-autocomplete/PathAutocomplete.tsx";
import { useDirectoryListing } from "~/components/path-autocomplete/useDirectoryListing.ts";
import { isElectron, selectProjectDirectory } from "~/electron/utils.ts";

import { NotConfiguredSection } from "./NotConfiguredSection.tsx";
import type { RemoteRepo } from "./RemoteRepoCombobox.tsx";
import { RemoteRepoCombobox } from "./RemoteRepoCombobox.tsx";
import styles from "./RemoteRepoForm.module.scss";
import type { SubmittableInputs } from "./remoteRepoFormHelpers.ts";
import {
  computeSubmittable,
  deriveNameFromUrl,
  getRemoteCliDependencyInfo,
  isRemoteFormShowingNotConfigured,
  stripGitSuffix,
} from "./remoteRepoFormHelpers.ts";
import type { RemoteProvider } from "./SourceRadioCards.tsx";

export type RemoteCloneSubmit = {
  provider: RemoteProvider;
  url: string;
  targetDir: string;
  name: string;
  /**
   * `owner/repo` slug for picker selections. Omitted in the manual-URL view.
   * The backend uses this — when present — to invoke `gh repo clone` with the
   * slug rather than the URL, so `gh` picks the protocol from the user's CLI
   * config rather than the one embedded in the URL.
   */
  fullName?: string;
};

export type RemoteRepoFormView = "search" | "url";

type RemoteRepoFormProps = {
  provider: RemoteProvider;
  dependenciesStatus: DependenciesStatus | null;
  isLoadingDependencies?: boolean;
  disabled?: boolean;
  view: RemoteRepoFormView;
  onViewChange: (view: RemoteRepoFormView) => void;
  onSubmittableChange: (submittable: { ready: boolean; payload?: RemoteCloneSubmit }) => void;
  /**
   * Called when the combobox discovers the provider CLI is no longer
   * configured (a 412 mid-session). The owner of `dependenciesStatus` should
   * refresh it so `isConfigured` flips false and the form swaps in
   * NotConfiguredSection. No-op by default.
   */
  onNotConfigured?: () => void;
  searchInputRef?: Ref<HTMLInputElement>;
};

export const RemoteRepoForm = ({
  provider,
  dependenciesStatus,
  isLoadingDependencies = false,
  disabled = false,
  view,
  onViewChange,
  onSubmittableChange,
  onNotConfigured,
}: RemoteRepoFormProps): ReactElement => {
  const capabilities = getBackendCapabilities();
  const canBrowse = isElectron() && capabilities.canSelectLocalDir;
  const userDefaultCloneTargetDir = useAtomValue(defaultCloneTargetDirAtom);
  const hostDefaultClonesDir = useAtomValue(defaultClonesDirAtom);
  // Always append `/<provider>` so two same-name repos from different
  // providers don't collide on disk, regardless of whether the base path
  // comes from the user's Settings or the renderer-resolved default.
  // Null while the IPC hasn't resolved (or in non-Electron environments)
  // — the form treats that as "no default, user must type one".
  const defaultTargetDir = useMemo<string | null>(() => {
    const base = userDefaultCloneTargetDir.trim() || hostDefaultClonesDir;
    return base ? `${base}/${provider}` : null;
  }, [hostDefaultClonesDir, provider, userDefaultCloneTargetDir]);

  // internal state
  const [selectedRepo, setSelectedRepo] = useState<RemoteRepo | undefined>(undefined);
  const [urlInput, setUrlInput] = useState<string>("");
  const [name, setName] = useState<string>("");
  // `userTargetDir` is undefined until the user explicitly edits or picks a
  // folder; while undefined we render `defaultTargetDir` so a late-arriving
  // backend value (e.g. /api/v1/config/backend-capabilities resolving after
  // first paint) flows through automatically.
  const [userTargetDir, setUserTargetDir] = useState<string | undefined>(undefined);
  const [isUsingCustomTarget, setIsUsingCustomTarget] = useState<boolean>(false);

  // hooks
  const { fetchDirectories } = useDirectoryListing();

  const dependencyInfo = getRemoteCliDependencyInfo(dependenciesStatus);
  const isConfigured = Boolean(dependencyInfo?.installed && dependencyInfo.isAuthenticated);
  // Suppress the configured/not-configured branches until the first poll
  // resolves; otherwise dialogs opened without a pre-populated atom flash
  // NotConfiguredSection before the real status arrives.
  const isWaitingForFirstStatus = isLoadingDependencies && !dependencyInfo;

  // The user-typed value wins over the default; when the input mode doesn't
  // expose an editor (no browse, no custom-target checkbox toggled), we fall
  // back to `defaultTargetDir` so toggling the checkbox off cleanly reverts.
  // Coerce null defaults to empty string for inputs / submit gating.
  const targetDirInputValue = userTargetDir ?? defaultTargetDir ?? "";
  const effectiveTargetDir = canBrowse || isUsingCustomTarget ? targetDirInputValue : (defaultTargetDir ?? "");

  // Push the current submittable to the parent, computed from the *next* values
  // produced by an event handler. We compute from explicit arguments rather
  // than closing over state so we don't depend on the render's stale values.
  const pushSubmittable = useCallback(
    (overrides: Partial<SubmittableInputs>): void => {
      const next = computeSubmittable({
        provider,
        view,
        selectedRepo,
        urlInput,
        name,
        effectiveTargetDir,
        ...overrides,
      });
      onSubmittableChange(next);
    },
    [provider, view, selectedRepo, urlInput, name, effectiveTargetDir, onSubmittableChange],
  );

  // Latest-ref so the effect below can re-push without listing every input as a
  // dependency (which would re-run it on every keystroke).
  const pushSubmittableRef = useRef(pushSubmittable);
  pushSubmittableRef.current = pushSubmittable;

  // Re-push when `effectiveTargetDir` changes on its own — i.e. the resolved
  // default target folder arrives asynchronously (the backend-capabilities and
  // user-config atoms settle after first paint). Without this, the displayed
  // value updates but the parent's cached submittable keeps the stale
  // targetDir, so a fast click would clone into the wrong folder. User edits
  // already push via their handlers; this only catches the late default.
  useEffect(() => {
    pushSubmittableRef.current({});
  }, [effectiveTargetDir]);

  // callbacks
  const handleSelectRepo = useCallback(
    (repo: RemoteRepo): void => {
      setSelectedRepo(repo);
      const parts = repo.fullName.split("/");
      const derived = stripGitSuffix(parts[parts.length - 1] ?? repo.fullName);
      setName(derived);
      pushSubmittable({ selectedRepo: repo, name: derived });
    },
    [pushSubmittable],
  );

  const handleClearSelectedRepo = useCallback((): void => {
    setSelectedRepo(undefined);
    pushSubmittable({ selectedRepo: undefined });
  }, [pushSubmittable]);

  const handleUrlChange = useCallback(
    (next: string): void => {
      setUrlInput(next);
      const derived = deriveNameFromUrl(next);
      const nextName = derived || name;
      if (derived) {
        setName(derived);
      }
      pushSubmittable({ urlInput: next, name: nextName });
    },
    [pushSubmittable, name],
  );

  const handleNameChange = useCallback(
    (next: string): void => {
      setName(next);
      pushSubmittable({ name: next });
    },
    [pushSubmittable],
  );

  const handleBrowseClick = useCallback(async (): Promise<void> => {
    try {
      const picked = await selectProjectDirectory();
      if (picked) {
        setUserTargetDir(picked);
        // `canBrowse` implies the editable PathAutocomplete is visible, so
        // `effectiveTargetDir` becomes `picked` immediately.
        pushSubmittable({ effectiveTargetDir: picked });
      }
    } catch (error) {
      // Surface in console; the parent dialog handles toast errors for submit.
      console.error("Failed to select directory:", error);
    }
  }, [pushSubmittable]);

  const handleTargetDirChange = useCallback(
    (next: string): void => {
      setUserTargetDir(next);
      // Only the editable surface drives `effectiveTargetDir`; mirror the same
      // gate here so we don't lie to the parent when the checkbox is off.
      const nextEffective = canBrowse || isUsingCustomTarget ? next : (defaultTargetDir ?? "");
      pushSubmittable({ effectiveTargetDir: nextEffective });
    },
    [pushSubmittable, canBrowse, isUsingCustomTarget, defaultTargetDir],
  );

  const handleCustomTargetToggle = useCallback(
    (checked: boolean): void => {
      setIsUsingCustomTarget(checked);
      const nextEffective = canBrowse || checked ? (userTargetDir ?? defaultTargetDir ?? "") : (defaultTargetDir ?? "");
      pushSubmittable({ effectiveTargetDir: nextEffective });
    },
    [pushSubmittable, canBrowse, userTargetDir, defaultTargetDir],
  );

  const handleViewChange = useCallback(
    (next: RemoteRepoFormView): void => {
      onViewChange(next);
      pushSubmittable({ view: next });
    },
    [onViewChange, pushSubmittable],
  );

  // Stable wrapper so the combobox's effect dependency doesn't churn when the
  // parent passes an inline callback.
  const handleNotConfigured = useCallback((): void => {
    onNotConfigured?.();
  }, [onNotConfigured]);

  // rendering
  const trimmedName = name.trim();
  const targetSuffix = trimmedName ? `/${trimmedName}` : undefined;
  // The "Search my repositories instead" toggle is always available so the
  // user can land on the NotConfiguredSection from URL view. Form fields below
  // are hidden in that state since there's no URL to clone. Shared with
  // AddRepoDialog's footer-CTA logic so the two can't drift.
  const isShowingNotConfiguredSection = isRemoteFormShowingNotConfigured(
    dependenciesStatus,
    view,
    isLoadingDependencies,
  );

  const renderTargetFolderInput = (): ReactElement => {
    if (canBrowse) {
      return (
        <Flex direction="column" gap="2">
          <Text size="2" weight="medium">
            Target Folder
          </Text>
          <PathAutocomplete
            placeholder="~/code"
            value={targetDirInputValue}
            onValueChange={handleTargetDirChange}
            onSubmit={handleTargetDirChange}
            fetchDirectories={fetchDirectories}
            disabled={disabled}
            suffix={targetSuffix}
          />
          <Text size="2" className={styles.browseHint}>
            Or{" "}
            <button type="button" className={styles.browseLink} onClick={handleBrowseClick} disabled={disabled}>
              browse
            </button>{" "}
            for a folder
          </Text>
        </Flex>
      );
    }

    return (
      <Flex direction="column" gap="2">
        <Flex align="center" gap="2" asChild>
          <label>
            <Checkbox
              checked={isUsingCustomTarget}
              onCheckedChange={(checked) => handleCustomTargetToggle(checked === true)}
              disabled={disabled}
            />
            <Text size="2">Use a custom target folder</Text>
          </label>
        </Flex>
        {isUsingCustomTarget && (
          <PathAutocomplete
            placeholder={defaultTargetDir ?? "~/code"}
            value={targetDirInputValue}
            onValueChange={handleTargetDirChange}
            onSubmit={handleTargetDirChange}
            fetchDirectories={fetchDirectories}
            disabled={disabled}
            suffix={targetSuffix}
          />
        )}
      </Flex>
    );
  };

  return (
    <Flex direction="column" gap="3">
      {view === "search" ? (
        <Flex direction="column" gap="2">
          {isWaitingForFirstStatus ? (
            <Flex align="center" justify="center" py="5" gap="2">
              <Spinner size="2" />
              <Text size="2" color="gray">
                Checking gh CLI…
              </Text>
            </Flex>
          ) : isConfigured ? (
            <>
              <Text size="2" weight="medium">
                Repository
              </Text>
              {selectedRepo ? (
                <Flex align="center" justify="between" gap="3" className={styles.selectedCard}>
                  <Flex direction="column" gap="1" minWidth="0">
                    <Link
                      href={selectedRepo.cloneUrl.replace(/\.git$/, "")}
                      target="_blank"
                      rel="noreferrer"
                      size="2"
                      weight="medium"
                      color="gray"
                      highContrast
                      underline="hover"
                      className={styles.selectedName}
                    >
                      {selectedRepo.fullName}
                    </Link>
                    <Text size="1" color="gray">
                      Selected
                    </Text>
                  </Flex>
                  <Button variant="surface" onClick={handleClearSelectedRepo} disabled={disabled}>
                    Change
                  </Button>
                </Flex>
              ) : (
                <RemoteRepoCombobox
                  provider={provider}
                  onSelect={handleSelectRepo}
                  onNotConfigured={handleNotConfigured}
                />
              )}
              <Box>
                <button
                  type="button"
                  className={styles.toggleLink}
                  onClick={() => handleViewChange("url")}
                  disabled={disabled}
                  data-testid={ElementIds.ADD_REPO_REMOTE_URL_TOGGLE}
                >
                  I&apos;ll paste a URL instead
                </button>
              </Box>
            </>
          ) : (
            <NotConfiguredSection
              provider={provider}
              footer={
                <button
                  type="button"
                  className={styles.toggleLink}
                  onClick={() => handleViewChange("url")}
                  disabled={disabled}
                  data-testid={ElementIds.ADD_REPO_REMOTE_URL_TOGGLE}
                >
                  I&apos;ll paste a URL instead
                </button>
              }
            />
          )}
        </Flex>
      ) : (
        <Flex direction="column" gap="2">
          <Text size="2" weight="medium">
            Repository URL
          </Text>
          <TextField.Root
            placeholder="https://github.com/owner/repo.git"
            value={urlInput}
            onChange={(event) => handleUrlChange(event.target.value)}
            disabled={disabled}
            data-testid={ElementIds.ADD_REPO_REMOTE_URL_INPUT}
          />
          <Box>
            <button
              type="button"
              className={styles.toggleLink}
              onClick={() => handleViewChange("search")}
              disabled={disabled}
              data-testid={ElementIds.ADD_REPO_REMOTE_URL_TOGGLE}
            >
              Search my repositories instead
            </button>
          </Box>
        </Flex>
      )}

      {!isShowingNotConfiguredSection && !isWaitingForFirstStatus && (
        <>
          <Flex direction="column" gap="2">
            <Text size="2" weight="medium">
              Repo Name
            </Text>
            <TextField.Root
              placeholder="repository"
              value={name}
              onChange={(event) => handleNameChange(event.target.value)}
              disabled={disabled}
              data-testid={ElementIds.ADD_REPO_REMOTE_NAME_INPUT}
            />
          </Flex>

          {renderTargetFolderInput()}
        </>
      )}
    </Flex>
  );
};
