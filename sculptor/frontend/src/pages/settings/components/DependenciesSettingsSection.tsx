import { CheckCircledIcon, CrossCircledIcon, ExclamationTriangleIcon } from "@radix-ui/react-icons";
import { Box, Button, Flex, Progress, Select, Separator, Spinner, Text, TextField, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import type { UserConfigField } from "../../../api";
import { ElementIds } from "../../../api";
import { dependenciesStatusAtom } from "../../../common/state/atoms/dependenciesStatus";
import { useManagedDependency } from "../../../common/useManagedDependency";
import { SettingRow } from "./SettingRow.tsx";
import { SectionTitle, SettingsSectionLayout } from "./SettingsSection.tsx";

type DependenciesSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const DependenciesSettingsSection = ({ onSettingChange }: DependenciesSettingsSectionProps): ReactElement => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const git = dependenciesStatus?.git ?? null;
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
            <Text size="2" style={{ wordBreak: "break-all" }}>
              {claude?.path ?? "\u2014"}
            </Text>
          </SettingRow>

          {displayMode === "CUSTOM" && (
            <SettingRow
              title="Custom Path"
              description="Absolute path or command name (e.g. /usr/local/bin/claude or claude)."
            >
              <Flex gap="2" align="center">
                <TextField.Root
                  placeholder="/usr/local/bin/claude or claude"
                  value={customPathInput}
                  onChange={(e) => setCustomPathInput(e.target.value)}
                  data-testid={ElementIds.CLAUDE_CLI_CUSTOM_PATH_INPUT}
                  style={{ minWidth: "300px" }}
                />
                <Button variant="soft" onClick={handleApplyCustomPath} data-testid="claude-cli-custom-path-apply">
                  Apply
                </Button>
              </Flex>
            </SettingRow>
          )}
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
    </SettingsSectionLayout>
  );
};
