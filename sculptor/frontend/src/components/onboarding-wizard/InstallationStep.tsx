import { Button, Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import {
  authenticateDependency,
  ElementIds,
  getDependenciesStatus,
  getUserConfig,
  installDependency,
  updateUserConfig,
} from "~/api";
import { HTTPException } from "~/common/Errors.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { useInterval } from "~/common/useInterval.ts";
import { usePollingInterval } from "~/common/usePollingInterval.ts";

import { DependencyCard } from "./DependencyCard.tsx";
import type { DependencyStatus } from "./dependencyTypes.ts";
import styles from "./OnboardingWizard.module.scss";

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

type InstallationStepProps = {
  onComplete: () => void;
  isLoading: boolean;
  error: string | null;
};

/** The InstallationStep is the second step of the OnboardingWizard where we verify that users have
 * the necessary dependencies installed.
 *
 * It is a key requirement of this page to track the appropriate PostHog events granurlaly as users complete the verious
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
  const [isRechecking, setIsRechecking] = useState(false);
  const { startPolling, stopPolling } = usePollingInterval();

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

  const triggerAuth = async (): Promise<void> => {
    setIsAuthenticating(true);
    try {
      const response = await authenticateDependency({ query: { tool: "CLAUDE" } });
      if (response.data?.success) {
        await loadDependencies();
      }
    } catch (err) {
      console.error("Authentication failed:", err);
    } finally {
      setIsAuthenticating(false);
    }
  };

  // Initial load
  useEffect(() => {
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
      triggerInstall();
    }
  }, [dependencies, hasTriggeredInstall, isInstalling, triggerInstall]);

  // Poll every 30 seconds (normal rate) when not installing.
  // Use silent mode so the UI doesn't flash loading state on each poll.
  useInterval(() => {
    if (!isDependenciesLoading && !isInstalling) {
      loadDependencies(true);
    }
  }, 30_000);

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

  const handleOverride = async (depKey: "claude" | "git", path: string): Promise<void> => {
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

  const claudeMode = dependencies?.claude?.mode ?? null;
  const claudeModeControls =
    claudeMode === "MANAGED"
      ? [{ label: "Use System PATH", mode: "CUSTOM" }]
      : claudeMode !== null
        ? [{ label: "Use Managed", mode: "MANAGED" }]
        : undefined;

  return (
    <Flex direction="column" gap="2" data-testid={ElementIds.ONBOARDING_INSTALLATION_STEP}>
      <Text className={styles.titleText}>Let&apos;s get you set up</Text>
      <Text color="gray" className={styles.secondaryText}>
        The following are required to use Sculptor
      </Text>

      {/* Dependencies Section */}
      <Flex direction="column" gap="3">
        {/* Claude CLI */}
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
          onApplyOverride={(path) => handleOverride("claude", path)}
          installProgress={dependencies?.claude?.installProgress ?? null}
        />

        {/* Git */}
        <DependencyCard
          name="Git"
          cliName="git"
          status={gitStatus}
          installUrl="https://git-scm.com/downloads"
          brewPackage="git"
          onApplyOverride={(path) => handleOverride("git", path)}
        />
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
        <Text size="2" style={{ color: "var(--accent-10)" }}>
          {isRechecking ? (
            "Checking…"
          ) : (
            <>
              Click{" "}
              <Text
                className={styles.recheckLink}
                onClick={async () => {
                  setIsRechecking(true);
                  await loadDependencies(true);
                  setIsRechecking(false);
                }}
              >
                here
              </Text>{" "}
              to check again
            </>
          )}
        </Text>
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
