import { CheckCircledIcon, CrossCircledIcon, ExclamationTriangleIcon, InfoCircledIcon } from "@radix-ui/react-icons";
import {
  Box,
  Button,
  Callout,
  Code,
  Flex,
  IconButton,
  Link,
  Progress,
  Select,
  Spinner,
  Text,
  TextField,
  Tooltip,
} from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { TrashIcon } from "lucide-react";
import { type ReactElement, useCallback, useMemo, useState } from "react";

import { ElementIds, UserConfigField } from "../../../api";
import { dependenciesStatusAtom } from "../../../common/state/atoms/dependenciesStatus";
import { isPiAgentEnabledAtom, userConfigAtom } from "../../../common/state/atoms/userConfig";
import { useManagedDependency } from "../hooks/useManagedDependency";
import { PiProvidersArea } from "./PiProvidersArea.tsx";
import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";

type PiSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
  onNavigateToExperimental?: () => void;
};

export const PiSettingsSection = ({
  onSettingChange,
  onNavigateToExperimental,
}: PiSettingsSectionProps): ReactElement => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const userConfig = useAtomValue(userConfigAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const {
    info: pi,
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
  } = useManagedDependency({ tool: "PI", onSettingChange });

  const envVarNames: ReadonlyArray<string> = useMemo(
    () => userConfig?.pi?.apiKeyEnvVarNames ?? ["ANTHROPIC_API_KEY"],
    [userConfig?.pi?.apiKeyEnvVarNames],
  );
  const [newEnvVarName, setNewEnvVarName] = useState<string>("");

  const handleAddEnvVarName = useCallback((): void => {
    const trimmed = newEnvVarName.trim();
    if (!trimmed) return;
    if (envVarNames.includes(trimmed)) {
      setNewEnvVarName("");
      return;
    }
    onSettingChange(UserConfigField.PI, { apiKeyEnvVarNames: [...envVarNames, trimmed] });
    setNewEnvVarName("");
  }, [envVarNames, newEnvVarName, onSettingChange]);

  const handleRemoveEnvVarName = useCallback(
    (name: string): void => {
      const next = envVarNames.filter((value) => value !== name);
      onSettingChange(UserConfigField.PI, { apiKeyEnvVarNames: next });
    },
    [envVarNames, onSettingChange],
  );

  const pinnedVersion = pi?.versionRange?.recommendedVersion ?? null;
  const statusTooltip = pi?.versionRange ? `Pinned version: ${pi.versionRange.recommendedVersion}` : undefined;
  const customInstallWarning =
    "Not recommended — Sculptor ships pi for you. Switch Binary Source to Managed to install the " +
    "pinned version automatically. A self-installed pi must match the pinned version" +
    (pinnedVersion ? ` (${pinnedVersion})` : "") +
    " exactly, or Sculptor will refuse to run it.";

  return (
    <SettingsSectionLayout>
      {!isPiAgentEnabled && (
        <Callout.Root color="yellow" data-testid={ElementIds.PI_SETTINGS_DISABLED_BANNER}>
          <Callout.Icon>
            <InfoCircledIcon />
          </Callout.Icon>
          <Callout.Text>
            You have not enabled the pi agent. Enable it in{" "}
            {onNavigateToExperimental ? (
              <Link
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  onNavigateToExperimental();
                }}
              >
                Experimental
              </Link>
            ) : (
              "Experimental"
            )}
            . If you have any pi agents active, you can configure them here.
          </Callout.Text>
        </Callout.Root>
      )}

      <SettingRow title="Binary Source" description="Choose how Sculptor locates the pi binary.">
        <Flex align="center" gap="2">
          <Select.Root value={displayMode} onValueChange={handleModeChange}>
            <Select.Trigger variant="soft" data-testid={ElementIds.PI_MODE_SELECTOR} />
            <Select.Content>
              <Select.Item value="MANAGED" data-testid={ElementIds.PI_MODE_OPTION_MANAGED}>
                Managed
              </Select.Item>
              <Select.Item value="CUSTOM" data-testid={ElementIds.PI_MODE_OPTION_CUSTOM}>
                Custom
              </Select.Item>
            </Select.Content>
          </Select.Root>
          {isModeSettling && <Spinner size="1" />}
        </Flex>
      </SettingRow>

      <SettingRow title="Status" description="Whether the configured pi binary is installed and at the pinned version.">
        <Flex align="center" gap="2" data-testid={ElementIds.PI_STATUS}>
          {dependenciesStatus === null || isModeSettling ? (
            <Spinner size="1" />
          ) : pi?.isVersionInRange === true ? (
            <Tooltip content={statusTooltip}>
              <Flex align="center" gap="2">
                <CheckCircledIcon color="var(--green-9)" />
                <Text size="2" color="green" data-testid={ElementIds.PI_UP_TO_DATE}>
                  v{pi.version} — Pinned
                </Text>
              </Flex>
            </Tooltip>
          ) : pi?.isVersionInRange === false ? (
            <Tooltip content={statusTooltip}>
              <Flex align="center" gap="2">
                <ExclamationTriangleIcon color="var(--orange-9)" />
                <Text size="2" color="orange">
                  v{pi.version} — Outside pinned version
                </Text>
              </Flex>
            </Tooltip>
          ) : displayMode === "CUSTOM" && !pi?.path ? (
            <Text size="2" color="gray">
              No path configured
            </Text>
          ) : (
            <Flex align="center" gap="2">
              <CrossCircledIcon color="var(--red-9)" />
              <Text size="2" color="red">
                Not installed
              </Text>
            </Flex>
          )}
        </Flex>
      </SettingRow>

      {displayMode === "MANAGED" && (
        <SettingRow title="Managed Installation" description="Install or update the managed pi binary.">
          <Box>
            {isInstalling || installProgress ? (
              <Flex direction="column" gap="2" minWidth="200px" data-testid={ElementIds.PI_INSTALL_PROGRESS}>
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
                <Button variant="soft" onClick={handleInstall} data-testid={ElementIds.PI_INSTALL_BUTTON}>
                  Retry
                </Button>
              </Flex>
            ) : isManagedUpToDate ? (
              <Text size="2" color="green">
                Up to date
              </Text>
            ) : (
              <Button variant="soft" onClick={handleInstall} data-testid={ElementIds.PI_INSTALL_BUTTON}>
                Install pi
              </Button>
            )}
          </Box>
        </SettingRow>
      )}

      <SettingRow title="Pinned version" description="Sculptor only runs pi at this exact version.">
        <Text size="2" data-testid={ElementIds.PI_PINNED_VERSION}>
          {pinnedVersion ?? "—"}
        </Text>
      </SettingRow>

      <SettingRow title="Detected version" description="Version reported by `pi --version`.">
        <Text size="2" data-testid={ElementIds.PI_VERSION}>
          {pi?.version ?? "Not installed"}
        </Text>
      </SettingRow>

      <SettingRow title="Active path" description="Resolved path to the pi binary in use.">
        <Text size="2" style={{ wordBreak: "break-all" }}>
          {pi?.path ?? "—"}
        </Text>
      </SettingRow>

      {displayMode === "CUSTOM" && (
        <SettingRow title="Binary path" description="Absolute path or command name (e.g. /usr/local/bin/pi or pi).">
          <Flex gap="2" align="center">
            <TextField.Root
              placeholder="/usr/local/bin/pi or pi"
              value={customPathInput}
              onChange={(e) => setCustomPathInput(e.target.value)}
              data-testid={ElementIds.PI_BINARY_PATH_INPUT}
              style={{ minWidth: "300px" }}
            />
            <Button variant="soft" onClick={handleApplyCustomPath} data-testid={ElementIds.PI_BINARY_PATH_APPLY}>
              Apply
            </Button>
          </Flex>
        </SettingRow>
      )}

      <SettingRow
        title="API key env vars"
        description="Names of environment variables read from the user's process environment and injected into the pi subprocess at launch. Values are never persisted in this config."
      >
        <Flex direction="column" gap="2" data-testid={ElementIds.PI_ENV_VAR_NAMES_LIST}>
          {envVarNames.map((name) => (
            <Flex key={name} align="center" gap="2">
              <Code size="2">{name}</Code>
              <IconButton
                variant="ghost"
                size="1"
                onClick={() => handleRemoveEnvVarName(name)}
                data-testid={`${ElementIds.PI_ENV_VAR_NAME_REMOVE}-${name}`}
                aria-label={`Remove ${name}`}
              >
                <TrashIcon size={14} />
              </IconButton>
            </Flex>
          ))}
          <Flex gap="2" align="center">
            <TextField.Root
              placeholder="ENV_VAR_NAME"
              value={newEnvVarName}
              onChange={(e) => setNewEnvVarName(e.target.value)}
              data-testid={ElementIds.PI_ENV_VAR_NAME_INPUT}
            />
            <Button
              variant="soft"
              onClick={handleAddEnvVarName}
              disabled={!newEnvVarName.trim()}
              data-testid={ElementIds.PI_ENV_VAR_NAME_ADD}
            >
              Add
            </Button>
          </Flex>
        </Flex>
      </SettingRow>

      <PiProvidersArea />

      {displayMode === "CUSTOM" && (
        <SettingRow
          title="Install pi"
          description="Managed mode installs and version-pins pi for you. Only self-install if you have a specific reason."
        >
          <Box>
            <Flex direction="column" gap="2">
              <Callout.Root color="orange">
                <Callout.Icon>
                  <ExclamationTriangleIcon />
                </Callout.Icon>
                <Callout.Text>{customInstallWarning}</Callout.Text>
              </Callout.Root>
              {pinnedVersion ? (
                <Code size="2">npm install -g @earendil-works/pi-coding-agent@{pinnedVersion}</Code>
              ) : (
                <Text size="2" color="gray">
                  Pinned version unavailable — use Managed mode to install pi.
                </Text>
              )}
            </Flex>
          </Box>
        </SettingRow>
      )}
    </SettingsSectionLayout>
  );
};
