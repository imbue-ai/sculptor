import { CheckCircledIcon, CrossCircledIcon, ExclamationTriangleIcon } from "@radix-ui/react-icons";
import {
  Box,
  Button,
  Code,
  Flex,
  Link,
  Progress,
  Select,
  Separator,
  Spinner,
  Text,
  TextField,
  Tooltip,
} from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { type ReactElement, useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { type DependencyInfo, ElementIds, type UserConfigField } from "../../../api";
import { getBackendCapabilities } from "../../../common/state/atoms/backendCapabilities";
import { dependenciesStatusAtom } from "../../../common/state/atoms/dependenciesStatus";
import { useManagedDependency } from "../../../common/useManagedDependency";
import { SettingRow } from "./SettingRow.tsx";
import { SectionTitle, SettingsSectionLayout } from "./SettingsSection.tsx";

type OptionalCliSectionProps = {
  title: string;
  cliName: string;
  authCommand: string;
  installUrl: string;
  info: DependencyInfo | null;
  loading: boolean;
};

const OptionalCliSection = ({
  title,
  cliName,
  authCommand,
  installUrl,
  info,
  loading,
}: OptionalCliSectionProps): ReactElement => {
  const isInstalled = info?.installed === true;
  const isAuthenticated = info?.isAuthenticated;
  const isUnauthed = isInstalled && isAuthenticated === false;

  return (
    <div data-cli-section={cliName}>
      <SectionTitle>{title}</SectionTitle>

      <SettingRow title="Status" description={`Whether ${cliName} is available on your PATH.`}>
        <Flex align="center" gap="2">
          {loading ? (
            <Spinner size="1" />
          ) : !isInstalled ? (
            <>
              <CrossCircledIcon color="var(--red-9)" />
              <Text size="2" color="red">
                Not installed —{" "}
                <Link href={installUrl} target="_blank" rel="noreferrer">
                  install {cliName}
                </Link>
              </Text>
            </>
          ) : isUnauthed ? (
            <>
              <ExclamationTriangleIcon color="var(--orange-9)" />
              <Text size="2" color="orange">
                Not signed in — run <Code>{authCommand}</Code>
              </Text>
            </>
          ) : (
            <>
              <CheckCircledIcon color="var(--green-9)" />
              <Text size="2" color="green">
                v{info?.version} — Installed
              </Text>
            </>
          )}
        </Flex>
      </SettingRow>

      <SettingRow title="Active Version" description={`Currently resolved ${cliName} version.`}>
        <Text size="2">{info?.version ?? "Not installed"}</Text>
      </SettingRow>

      <SettingRow title="Active Path" description={`Path to the active ${cliName} binary.`}>
        <Text size="2" style={{ wordBreak: "break-all" }}>
          {info?.path ?? "—"}
        </Text>
      </SettingRow>
    </div>
  );
};

type DependenciesSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const DependenciesSettingsSection = ({ onSettingChange }: DependenciesSettingsSectionProps): ReactElement => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const git = dependenciesStatus?.git ?? null;
  const gh = dependenciesStatus?.gh ?? null;
  const canInstallOptionalClis = getBackendCapabilities().canSelectLocalDir;
  const {
    info: claude,
    mode,
    displayMode,
    isModeSettling,
    handleModeChange,
    isInstalling,
    handleInstall,
    installProgress,
    progressPercent,
    isManagedUpToDate,
    effectiveInstallError,
    customPathInput,
    setCustomPathInput,
    handleApplyCustomPath,
  } = useManagedDependency({ tool: "CLAUDE", onSettingChange });

  // Deep-link from onboarding ("?cli=gh") scrolls to that CLI section.
  const [searchParams] = useSearchParams();
  const targetCli = searchParams.get("cli");

  useEffect(() => {
    if (!targetCli) return;
    const section = document.querySelector(`[data-cli-section="${CSS.escape(targetCli)}"]`);
    if (section instanceof HTMLElement) {
      section.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [targetCli]);

  const statusTooltip = claude?.versionRange
    ? `Supported range: ${claude.versionRange.minVersion} \u2013 ${claude.versionRange.maxVersion}`
    : undefined;

  const isClaudeHealthy = isManagedUpToDate && !isInstalling && !effectiveInstallError && !installProgress;
  const isGitHealthy = git?.installed === true;

  return (
    <SettingsSectionLayout description="Manage external tool dependencies used by Sculptor.">
      <SectionTitle>Claude</SectionTitle>

      <SettingRow title="Binary Source" description="Choose how Sculptor locates the Claude CLI binary.">
        <Flex align="center" gap="2">
          <Select.Root value={displayMode} onValueChange={handleModeChange}>
            <Select.Trigger variant="soft" data-testid={ElementIds.CLAUDE_CLI_MODE_SELECTOR} />
            <Select.Content>
              <Select.Item value="MANAGED" data-testid={ElementIds.CLAUDE_CLI_MODE_OPTION_MANAGED}>
                Managed
              </Select.Item>
              <Select.Item value="CUSTOM" data-testid={ElementIds.CLAUDE_CLI_MODE_OPTION_CUSTOM}>
                Custom
              </Select.Item>
            </Select.Content>
          </Select.Root>
          {isModeSettling && <Spinner size="1" data-testid={ElementIds.CLAUDE_CLI_MODE_SETTLING} />}
        </Flex>
      </SettingRow>

      {isClaudeHealthy && !isModeSettling ? (
        // Compact status when managed and up-to-date
        <SettingRow title="Status" description="Managed Claude CLI binary.">
          <Flex align="center" gap="2" data-testid={ElementIds.CLAUDE_CLI_STATUS}>
            <CheckCircledIcon color="var(--green-9)" />
            <Tooltip content={statusTooltip}>
              <Text size="2" color="green" data-testid={ElementIds.CLAUDE_CLI_UP_TO_DATE}>
                v{claude?.version} — Up to date
              </Text>
            </Tooltip>
          </Flex>
        </SettingRow>
      ) : (
        // Full detail rows
        <>
          <SettingRow title="Status" description="Whether the active version is within the supported range.">
            <Flex align="center" gap="2" data-testid={ElementIds.CLAUDE_CLI_STATUS}>
              {dependenciesStatus === null || isModeSettling ? (
                <Spinner size="1" />
              ) : claude?.isVersionInRange === true ? (
                <Tooltip content={statusTooltip}>
                  <Flex align="center" gap="2">
                    <CheckCircledIcon color="var(--green-9)" />
                    <Text size="2" color="green">
                      Version in range
                    </Text>
                  </Flex>
                </Tooltip>
              ) : claude?.isVersionInRange === false ? (
                <Tooltip content={statusTooltip}>
                  <Flex align="center" gap="2">
                    <ExclamationTriangleIcon color="var(--orange-9)" />
                    <Text size="2" color="orange">
                      Out of range
                    </Text>
                  </Flex>
                </Tooltip>
              ) : mode === "CUSTOM" && !claude?.path ? (
                <Text size="2" color="gray">
                  No path configured
                </Text>
              ) : !claude?.installed ? (
                <>
                  <CrossCircledIcon color="var(--red-9)" />
                  <Text size="2" color="red">
                    Not installed
                  </Text>
                </>
              ) : null}
            </Flex>
          </SettingRow>

          {displayMode === "MANAGED" && (
            <SettingRow title="Managed Installation" description="Install or update the managed Claude CLI binary.">
              <Box>
                {isInstalling || installProgress ? (
                  <Flex direction="column" gap="2" minWidth="200px" data-testid={ElementIds.CLAUDE_CLI_PROGRESS}>
                    <Flex align="center" gap="2">
                      <Spinner size="1" />
                      <Text size="2">Installing...</Text>
                    </Flex>
                    {progressPercent !== null && <Progress value={progressPercent} />}
                  </Flex>
                ) : effectiveInstallError ? (
                  <Flex direction="column" gap="2">
                    <Text size="2" color="red">
                      {effectiveInstallError}
                    </Text>
                    <Button variant="soft" onClick={handleInstall} data-testid={ElementIds.CLAUDE_CLI_INSTALL_BUTTON}>
                      Retry
                    </Button>
                  </Flex>
                ) : isManagedUpToDate ? (
                  <Text size="2" color="green" data-testid={ElementIds.CLAUDE_CLI_UP_TO_DATE}>
                    Up to date
                  </Text>
                ) : (
                  <Button variant="soft" onClick={handleInstall} data-testid={ElementIds.CLAUDE_CLI_INSTALL_BUTTON}>
                    Install Claude CLI
                  </Button>
                )}
              </Box>
            </SettingRow>
          )}

          <SettingRow title="Active Version" description="Currently resolved Claude CLI version.">
            <Text size="2" data-testid={ElementIds.CLAUDE_CLI_VERSION}>
              {claude?.version ?? "Not installed"}
            </Text>
          </SettingRow>

          <SettingRow title="Active Path" description="Path to the active Claude CLI binary.">
            {displayMode === "CUSTOM" ? (
              <Flex gap="2" align="center">
                <TextField.Root
                  placeholder="/usr/local/bin/claude or claude"
                  value={customPathInput}
                  onChange={(e) => setCustomPathInput(e.target.value)}
                  data-testid={ElementIds.CLAUDE_CLI_CUSTOM_PATH_INPUT}
                  style={{ minWidth: "220px" }}
                />
                <Button
                  variant="soft"
                  onClick={handleApplyCustomPath}
                  data-testid={ElementIds.CLAUDE_CLI_CUSTOM_PATH_APPLY}
                >
                  Apply
                </Button>
              </Flex>
            ) : (
              <Text size="2" style={{ wordBreak: "break-all" }}>
                {claude?.path ?? "\u2014"}
              </Text>
            )}
          </SettingRow>
        </>
      )}

      <Separator size="4" my="5" />

      <SectionTitle>Git</SectionTitle>

      <SettingRow title="Status" description="Git must be available on your PATH.">
        <Flex align="center" gap="2" data-testid={ElementIds.SETTINGS_GIT_DEP_STATUS}>
          {dependenciesStatus === null ? (
            <Spinner size="1" />
          ) : isGitHealthy ? (
            <>
              <CheckCircledIcon color="var(--green-9)" />
              <Text size="2" color="green">
                v{git?.version} — Installed
              </Text>
            </>
          ) : (
            <>
              <CrossCircledIcon color="var(--red-9)" />
              <Text size="2" color="red">
                Not installed — install Git and ensure it is on your PATH
              </Text>
            </>
          )}
        </Flex>
      </SettingRow>

      {canInstallOptionalClis && (
        <>
          <Separator size="4" my="5" />
          <OptionalCliSection
            title="GitHub CLI"
            cliName="gh"
            authCommand="gh auth login"
            installUrl="https://github.com/cli/cli#installation"
            info={gh}
            loading={dependenciesStatus === null}
          />
        </>
      )}
    </SettingsSectionLayout>
  );
};
