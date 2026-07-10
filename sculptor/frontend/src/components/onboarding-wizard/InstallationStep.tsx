import { Button, Flex, Link, Text, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import {
  ElementIds,
  getDependenciesStatus,
  getUserConfig,
  installDependency,
  startDependencyAuth,
  submitDependencyAuthCode,
  updateUserConfig,
} from "~/api";
import { HTTPException } from "~/common/Errors.ts";
import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { useInterval } from "~/common/useInterval.ts";
import { usePollingInterval } from "~/common/usePollingInterval.ts";

import { DependencyCard } from "./DependencyCard.tsx";
import type { DependencyStatus } from "./dependencyTypes.ts";
import styles from "./OnboardingWizard.module.scss";

// Normal cadence for re-checking dependency status while not actively installing.
const NORMAL_POLL_INTERVAL_MS = 30_000;

const deriveClaudeStatus = (
  info: DependencyInfo | undefined,
  isInstalling: boolean,
  isAuthenticating: boolean,
  installError: string | null,
): DependencyStatus => {
  if (!info) return { state: "loading" };
  if (isInstalling) return { state: "installing" };
  if (installError) return { state: "error", message: installError };
  if (isAuthenticating && info.path && info.version) {
    return { state: "authenticating", path: info.path, version: info.version };
  }
  if (!info.installed) return { state: "not-installed" };
  if (info.isVersionInRange === false) {
    return {
      state: "wrong-version",
      path: info.path ?? "—",
      version: info.version ?? "—",
      requiredVersion: info.versionRange
        ? `${info.versionRange.minVersion} – ${info.versionRange.maxVersion}`
        : "unknown",
    };
  }

  if (info.isAuthenticated === false) {
    return { state: "needs-auth", path: info.path ?? "—", version: info.version ?? "—" };
  }
  return { state: "installed", path: info.path ?? "—", version: info.version ?? "—", isOverride: info.isOverride };
};

const deriveGitStatus = (info: DependencyInfo | undefined): DependencyStatus => {
  if (!info) return { state: "loading" };
  if (!info.installed) return { state: "not-installed" };
  return { state: "installed", path: info.path ?? "—", version: info.version ?? "—", isOverride: info.isOverride };
};

const deriveOptionalCliStatus = (info: DependencyInfo | undefined): DependencyStatus => {
  if (!info) return { state: "loading" };
  if (!info.installed) return { state: "not-installed" };
  if (info.isAuthenticated === false) {
    return { state: "needs-auth", path: info.path ?? "—", version: info.version ?? "—" };
  }
  return { state: "installed", path: info.path ?? "—", version: info.version ?? "—", isOverride: info.isOverride };
};

const derivePiStatus = (
  info: DependencyInfo | undefined,
  isInstalling: boolean,
  installError: string | null,
): DependencyStatus => {
  if (!info) return { state: "loading" };
  if (isInstalling) return { state: "installing" };
  if (installError) return { state: "error", message: installError };
  if (!info.installed) return { state: "not-installed" };
  if (info.isVersionInRange === false) {
    return {
      state: "wrong-version",
      path: info.path ?? "—",
      version: info.version ?? "—",
      // pi pins one exact version (min == max), so show it bare rather than as a range.
      requiredVersion: info.versionRange?.recommendedVersion ?? "unknown",
    };
  }
  return { state: "installed", path: info.path ?? "—", version: info.version ?? "—", isOverride: info.isOverride };
};

type InstallationStepProps = {
  onComplete: () => void;
  isLoading: boolean;
  error: string | null;
};

/** The InstallationStep is the second step of the OnboardingWizard where we verify that users have
 * the necessary dependencies installed.
 *
 * It is a key requirement of this page to track the appropriate PostHog events granularly as users complete the various
 * steps so that we can identify where users are dropping off in the onboarding process.
 */
export const InstallationStep = ({ onComplete, isLoading, error }: InstallationStepProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const [dependencies, setDependencies] = useState<DependenciesStatus | null>(null);
  const [isDependenciesLoading, setIsDependenciesLoading] = useState(true);
  const [dependenciesError, setDependenciesError] = useState<string | null>(null);
  const [isInstalling, setIsInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [hasTriggeredInstall, setHasTriggeredInstall] = useState(false);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  // The sign-in URL returned by start; while set, the Claude card shows the
  // "open this link, then paste the code" UI for headless/remote deployments.
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  // gh device-flow sign-in state: the one-time code + verification URL shown on
  // the gh card while we poll for the user to authorize in their browser.
  const [ghAuthUrl, setGhAuthUrl] = useState<string | null>(null);
  const [ghUserCode, setGhUserCode] = useState<string | null>(null);
  const [ghAuthError, setGhAuthError] = useState<string | null>(null);
  const [isRechecking, setIsRechecking] = useState(false);
  const { startPolling, stopPolling } = usePollingInterval();
  // pi's optional managed install runs on its own polling instance so it can't
  // stomp the Claude install / gh auth poll (and vice versa).
  const [isPiInstalling, setIsPiInstalling] = useState(false);
  const [piInstallError, setPiInstallError] = useState<string | null>(null);
  const { startPolling: startPiPolling, stopPolling: stopPiPolling } = usePollingInterval();

  const loadDependencies = useCallback(async (silent = false): Promise<void> => {
    try {
      if (!silent) setIsDependenciesLoading(true);
      const { data: dependenciesStatus } = await getDependenciesStatus();
      setDependencies(dependenciesStatus);
    } catch (err) {
      let errorMessage = "Failed to complete onboarding";
      if (err instanceof HTTPException) {
        errorMessage = err.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      setDependenciesError(errorMessage);
      setDependencies(null);
      console.error("Failed to load dependencies:", errorMessage);
    } finally {
      if (!silent) setIsDependenciesLoading(false);
    }
  }, []);

  const triggerInstall = useCallback(async (): Promise<void> => {
    setIsInstalling(true);
    setInstallError(null);
    setHasTriggeredInstall(true);
    try {
      // The install endpoint is fire-and-forget and opens no request transaction, so it
      // never acks on the unified stream; skipWsAck avoids a spurious 10s timeout while
      // the download runs — completion is tracked by the poll below.
      const response = await installDependency({ query: { tool: "CLAUDE" }, meta: { skipWsAck: true } });
      if (!response.data?.success) {
        setInstallError(response.data?.error ?? "Installation failed");
        setIsInstalling(false);
        return;
      }
      // Poll more frequently during install to detect completion
      startPolling(async () => {
        try {
          const { data: newDeps } = await getDependenciesStatus();
          setDependencies(newDeps);
          // A failed download surfaces install_error and leaves the stale binary
          // in place (so claude.installed can stay true). Stop polling and let the
          // error render instead of spinning forever.
          if (newDeps?.claude?.installError) {
            stopPolling();
            setIsInstalling(false);
            return;
          }

          if (newDeps?.claude?.installed && !newDeps?.claude?.installProgress) {
            stopPolling();
            setIsInstalling(false);
          }
        } catch {
          // Continue polling on error
        }
      });
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "Installation failed");
      setIsInstalling(false);
    }
  }, [startPolling, stopPolling]);

  const triggerPiInstall = useCallback(async (): Promise<void> => {
    setIsPiInstalling(true);
    setPiInstallError(null);
    try {
      // The managed copy is only used while pi's mode is MANAGED; a migrated
      // config may pin a CUSTOM path, so opting in flips the mode back first.
      if (dependencies?.pi?.mode === "CUSTOM") {
        const { data: currentConfig } = await getUserConfig({ meta: { skipWsAck: true } });
        if (currentConfig) {
          await updateUserConfig({
            body: {
              userConfig: {
                ...currentConfig,
                dependencyPaths: { ...(currentConfig.dependencyPaths ?? {}), pi: "MANAGED" },
              },
            },
            meta: { skipWsAck: true },
          });
        }
      }
      // Fire-and-forget install (see triggerInstall); completion is tracked by
      // the poll below.
      const response = await installDependency({ query: { tool: "PI" }, meta: { skipWsAck: true } });
      if (!response.data?.success) {
        setPiInstallError(response.data?.error ?? "Installation failed");
        setIsPiInstalling(false);
        return;
      }
      startPiPolling(async () => {
        try {
          const { data: newDeps } = await getDependenciesStatus();
          setDependencies(newDeps);
          if (newDeps?.pi?.installError) {
            stopPiPolling();
            setIsPiInstalling(false);
            return;
          }

          // A PATH-fallback pi reports installed before the download finishes,
          // so completion is the managed copy becoming the active binary.
          if (newDeps?.pi?.source === "MANAGED" && !newDeps?.pi?.installProgress) {
            stopPiPolling();
            setIsPiInstalling(false);
          }
        } catch {
          // Continue polling on error
        }
      });
    } catch (err) {
      setPiInstallError(err instanceof Error ? err.message : "Installation failed");
      setIsPiInstalling(false);
    }
  }, [dependencies?.pi?.mode, startPiPolling, stopPiPolling]);

  const handleModeSwitch = async (newMode: string): Promise<void> => {
    try {
      const { data: currentConfig } = await getUserConfig({ meta: { skipWsAck: true } });
      if (!currentConfig) return;
      const updatedConfig = {
        ...currentConfig,
        dependencyPaths: { ...(currentConfig.dependencyPaths ?? {}), claude: newMode },
      };
      await updateUserConfig({ body: { userConfig: updatedConfig }, meta: { skipWsAck: true } });
      const { data: newDeps } = await getDependenciesStatus();
      // Batch all state updates together to avoid a race where the auto-install
      // effect sees the reset flag with stale deps and re-triggers install.
      setInstallError(null);
      setHasTriggeredInstall(false);
      setDependencies(newDeps);
    } catch (err) {
      console.error("Failed to switch mode:", err);
    }
  };

  // Step 1 of sign-in: ask the backend to start `claude auth login`. It returns
  // the sign-in URL (and keeps the CLI waiting for a pasted code). On a machine
  // with a usable local browser the flow self-completes (success) and no code
  // is needed.
  const triggerAuth = async (): Promise<void> => {
    setIsAuthenticating(true);
    setAuthError(null);
    setAuthUrl(null);
    try {
      const response = await startDependencyAuth({ query: { tool: "CLAUDE" } });
      if (response.data?.success) {
        await loadDependencies();
      } else if (response.data?.needsCode && response.data.authUrl) {
        setAuthUrl(response.data.authUrl);
      } else {
        setAuthError(response.data?.error ?? "Sign-in failed. Please try again.");
      }
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Sign-in failed. Please try again.");
    } finally {
      setIsAuthenticating(false);
    }
  };

  // Step 2 of sign-in: send the code the user pasted from the sign-in page to
  // the still-running CLI, then refresh status.
  const submitAuthCode = async (code: string): Promise<void> => {
    setAuthError(null);
    try {
      const response = await submitDependencyAuthCode({ body: { tool: "CLAUDE", code } });
      if (response.data?.success) {
        setAuthUrl(null);
        await loadDependencies();
      } else {
        setAuthError(response.data?.error ?? "Sign-in failed. Please try again.");
      }
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Sign-in failed. Please try again.");
    }
  };

  // gh sign-in: a browser device flow. Start returns a one-time code + URL; the
  // user enters the code at github.com/login/device and gh completes on its own,
  // so we poll the dependency status until gh reports authenticated (no paste-back).
  const triggerGhAuth = async (): Promise<void> => {
    setGhAuthError(null);
    setGhAuthUrl(null);
    setGhUserCode(null);
    try {
      const response = await startDependencyAuth({ query: { tool: "GH" } });
      if (response.data?.success) {
        await loadDependencies();
        return;
      }

      if (response.data?.authUrl && response.data?.userCode) {
        setGhAuthUrl(response.data.authUrl);
        setGhUserCode(response.data.userCode);
        startPolling(async () => {
          try {
            const { data: newDeps } = await getDependenciesStatus({ meta: { skipWsAck: true } });
            if (newDeps) setDependencies(newDeps);
            if (newDeps?.gh?.isAuthenticated === true) {
              stopPolling();
            }
          } catch {
            // Keep polling on a transient error.
          }
        });
        return;
      }
      setGhAuthError(response.data?.error ?? "Sign-in failed. Please try again.");
    } catch (err) {
      setGhAuthError(err instanceof Error ? err.message : "Sign-in failed. Please try again.");
    }
  };

  // Initial load
  useEffect(() => {
    // Genuine mount-time fetch from the backend; the synchronous setState is
    // only the loading flag flip on an external-system sync, not derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadDependencies();
  }, [loadDependencies]);

  // Auto-trigger install in managed mode when Claude is not installed or out of range
  useEffect(() => {
    if (
      !hasTriggeredInstall &&
      !isInstalling &&
      dependencies?.claude &&
      dependencies.claude.mode === "MANAGED" &&
      (!dependencies.claude.installed || dependencies.claude.isVersionInRange === false)
    ) {
      // Reactive to backend-polled `dependencies`, not a user action, so this
      // install-kickoff side effect can't move to an event handler.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      triggerInstall();
    }
  }, [dependencies, hasTriggeredInstall, isInstalling, triggerInstall]);

  // Poll every 30 seconds (normal rate) when not installing.
  // Use silent mode so the UI doesn't flash loading state on each poll.
  useInterval(() => {
    if (!isDependenciesLoading && !isInstalling) {
      loadDependencies(true);
    }
  }, NORMAL_POLL_INTERVAL_MS);

  // Dismiss the sign-in prompt once Claude reports authenticated — e.g. when a
  // local loopback login completed in the background and the poll picked it up.
  // Derived during render so there's no extra render cycle (and no stale frame
  // showing the prompt) when the background poll reports success.
  const isClaudeAuthenticated = dependencies?.claude?.isAuthenticated === true;
  const displayedAuthUrl = isClaudeAuthenticated ? null : authUrl;
  const displayedAuthError = isClaudeAuthenticated ? null : authError;

  // Hide the gh device-flow prompt once gh reports authenticated (the poll in
  // triggerGhAuth, or the background 30s poll, picked up the completed sign-in).
  // Derived during render so there's no extra render cycle (and no stale frame
  // showing the prompt) when the background poll reports success.
  const isGhAuthenticated = dependencies?.gh?.isAuthenticated === true;
  const displayedGhAuthUrl = isGhAuthenticated ? null : ghAuthUrl;
  const displayedGhUserCode = isGhAuthenticated ? null : ghUserCode;
  const displayedGhAuthError = isGhAuthenticated ? null : ghAuthError;

  // Tear down the device-flow poll once gh authenticates. The prompt is already
  // hidden via the derived values above; this only stops the interval (a
  // genuine external-system side effect, idempotent). The device-flow poll also
  // stops itself, so this just covers the case where the background 30s poll is
  // what flips the flag.
  useEffect(() => {
    if (ghAuthUrl && isGhAuthenticated) {
      stopPolling();
    }
  }, [ghAuthUrl, isGhAuthenticated, stopPolling]);

  /* We can only submit if all the dependencies are installed, in range, and authenticated */
  const canSubmit = (): boolean => {
    return (
      !isLoading &&
      !isDependenciesLoading &&
      !isInstalling &&
      !isAuthenticating &&
      dependencies !== null &&
      dependencies.git.installed &&
      dependencies.claude.installed &&
      dependencies.claude.isVersionInRange !== false &&
      dependencies.claude.isAuthenticated !== false
    );
  };

  const handleSubmit = (): void => {
    onComplete();
  };

  // Allow Enter to trigger Continue, unless focus is in a text input (e.g. the override path field).
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key !== "Enter") return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (!canSubmit()) return;
      handleSubmit();
    };
    window.addEventListener("keydown", handleKeyDown);
    return (): void => window.removeEventListener("keydown", handleKeyDown);
  });

  const handleOverride = async (depKey: "claude" | "git" | "gh" | "pi", path: string): Promise<void> => {
    const { data: currentConfig } = await getUserConfig({ meta: { skipWsAck: true } });
    if (!currentConfig) throw new Error("Config not loaded");

    const updatedConfig = {
      ...currentConfig,
      dependencyPaths: {
        ...(currentConfig.dependencyPaths ?? {}),
        [depKey]: path,
      },
    };

    await updateUserConfig({
      body: { userConfig: updatedConfig },
      meta: { skipWsAck: true },
    });

    const { data: newDeps } = await getDependenciesStatus();
    if (!newDeps?.[depKey]?.installed) {
      throw new Error("No executable found at this path");
    }
    setDependencies(newDeps);
  };

  // A background download failure (e.g. on startup) surfaces via the backend
  // status, not the local install call, so fold it in alongside installError.
  // The backend error is process-lifetime, so ignore it once the binary is
  // usable — otherwise a stale error would mask a now-healthy state (e.g. after
  // switching binary mode).
  const claudeInfo = dependencies?.claude;
  const isClaudeUsable =
    claudeInfo?.installed === true && claudeInfo.isVersionInRange !== false && claudeInfo.isAuthenticated !== false;
  const backendInstallError = isClaudeUsable ? null : (dependencies?.claude?.installError ?? null);
  const claudeStatus = deriveClaudeStatus(
    claudeInfo,
    isInstalling,
    isAuthenticating,
    installError ?? backendInstallError,
  );
  const gitStatus = deriveGitStatus(dependencies?.git);
  const ghStatus = deriveOptionalCliStatus(dependencies?.gh);
  const canInstallOptionalClis = getBackendCapabilities().canSelectLocalDir;

  const claudeMode = dependencies?.claude?.mode ?? null;
  const claudeModeControls =
    claudeMode === "MANAGED"
      ? [{ label: "Use System PATH", mode: "CUSTOM" }]
      : claudeMode !== null
        ? [{ label: "Use Managed", mode: "MANAGED" }]
        : undefined;

  // The backend install error is process-lifetime; ignore it once the managed
  // copy is the healthy active binary (a healthy PATH-fallback pi must not hide
  // a failed managed download the user asked for).
  const piInfo = dependencies?.pi;
  const isPiManagedHealthy = piInfo?.source === "MANAGED" && piInfo.isVersionInRange !== false;
  const backendPiInstallError = isPiManagedHealthy ? null : (piInfo?.installError ?? null);
  const piStatus = derivePiStatus(piInfo, isPiInstalling, piInstallError ?? backendPiInstallError);
  // A detected system-PATH pi is shown and used as-is; the expanded details
  // still offer the managed, version-pinned download as an explicit opt-in.
  const piModeControls =
    piInfo?.installed && piInfo.source === "EXTERNAL" && !isPiInstalling
      ? [{ label: "Install managed pi", mode: "MANAGED" }]
      : undefined;

  return (
    <Flex direction="column" gap="2" data-testid={ElementIds.ONBOARDING_INSTALLATION_STEP}>
      <Text className={styles.titleText}>Let&apos;s get you set up</Text>
      <Text color="gray" className={styles.secondaryText}>
        The following are required to use Sculptor
      </Text>

      {/* Required dependencies */}
      <Flex direction="column" gap="3">
        <DependencyCard
          name="Claude Code CLI"
          cliName="claude"
          status={claudeStatus}
          installUrl="https://docs.anthropic.com/en/docs/claude-code/getting-started"
          brewPackage="claude-code"
          helpText="Sculptor installs a pinned version of Claude Code. It does not interfere with your existing"
          onModeSwitch={handleModeSwitch}
          modeControls={claudeModeControls}
          onAuthenticate={triggerAuth}
          authUrl={displayedAuthUrl}
          authError={displayedAuthError}
          onSubmitAuthCode={submitAuthCode}
          onApplyOverride={(path) => handleOverride("claude", path)}
          installProgress={dependencies?.claude?.installProgress ?? null}
        />

        <DependencyCard
          name="Git"
          cliName="git"
          status={gitStatus}
          installUrl="https://git-scm.com/downloads"
          brewPackage="git"
          onApplyOverride={(path) => handleOverride("git", path)}
        />
      </Flex>

      {/* Optional dependencies — onboarding continues without them. */}
      <Text size="2" mt="2" color="gray" data-testid={ElementIds.ONBOARDING_OPTIONAL_DEPENDENCIES_HEADER}>
        Optional
      </Text>
      <Flex direction="column" gap="3">
        {/* Optional CLI for cloning from GitHub. Hidden in web-remote mode since
            the user can't install binaries on the backend host. */}
        {canInstallOptionalClis && (
          <Flex direction="column" gap="1">
            <Text size="1" color="gray">
              Recommended for{" "}
              <Tooltip
                content={
                  <Flex direction="column" gap="2" style={{ maxWidth: 280 }}>
                    <Text size="2" weight="medium">
                      Sculptor uses gh (GitHub CLI) to:
                    </Text>
                    <Flex direction="column" gap="1">
                      <Text size="1">• Create projects from your GitHub repos</Text>
                      <Text size="1">• Create workspaces from your remote branches</Text>
                      <Text size="1">• Warn when local and remote diverge</Text>
                    </Flex>
                    <Button asChild size="1" variant="surface" mt="1">
                      <a href="https://github.com/cli/cli#installation" target="_blank" rel="noreferrer">
                        Read GitHub CLI docs
                      </a>
                    </Button>
                  </Flex>
                }
              >
                <Link href="https://github.com/cli/cli#installation" target="_blank" className={styles.inlineLink}>
                  GitHub
                </Link>
              </Tooltip>
            </Text>
            <DependencyCard
              name="GitHub CLI"
              cliName="gh"
              optional
              status={ghStatus}
              installUrl="https://github.com/cli/cli#installation"
              brewPackage="gh"
              helpText="Used to clone GitHub repos from inside Sculptor."
              onApplyOverride={(path) => handleOverride("gh", path)}
              onAuthenticate={triggerGhAuth}
              authUrl={displayedGhAuthUrl}
              userCode={displayedGhUserCode}
              authError={displayedGhAuthError}
            />
          </Flex>
        )}

        {/* pi, Sculptor's optional second harness. A pi already on the PATH is
            used as-is; Install downloads Sculptor's managed, version-pinned copy. */}
        <Flex direction="column" gap="1">
          <Text size="1" color="gray">
            For the{" "}
            <Link href="https://github.com/earendil-works/pi" target="_blank" className={styles.inlineLink}>
              Pi
            </Link>{" "}
            harness — an alternative harness supporting many model providers
          </Text>
          <DependencyCard
            name="Pi"
            cliName="pi"
            optional
            status={piStatus}
            installUrl="https://github.com/earendil-works/pi"
            onInstall={() => void triggerPiInstall()}
            onApplyOverride={(path) => handleOverride("pi", path)}
            onModeSwitch={() => void triggerPiInstall()}
            modeControls={piModeControls}
            installProgress={dependencies?.pi?.installProgress ?? null}
          />
        </Flex>
      </Flex>

      {error && (
        <Text size="2" color={dangerColor} className={styles.error}>
          {error}
        </Text>
      )}

      {dependenciesError && (
        <Text size="2" color={dangerColor} className={styles.error}>
          {dependenciesError}
        </Text>
      )}

      <Flex mt="1">
        {isRechecking ? (
          <Text size="2" style={{ color: "var(--accent-10)" }}>
            Checking…
          </Text>
        ) : (
          <Text
            size="2"
            className={styles.inlineLink}
            onClick={async () => {
              setIsRechecking(true);
              await loadDependencies(true);
              setIsRechecking(false);
            }}
          >
            Click to check again
          </Text>
        )}
      </Flex>

      <Button
        mt="1"
        size="3"
        variant="solid"
        disabled={!canSubmit()}
        onClick={handleSubmit}
        className={styles.primaryButton}
        data-testid={ElementIds.ONBOARDING_COMPLETE_BUTTON}
      >
        Continue
      </Button>
    </Flex>
  );
};
