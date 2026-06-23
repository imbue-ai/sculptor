import { Button, Flex, Switch, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { RefreshCw } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import type { ProjectEnvVarNames } from "~/api";
import { ElementIds, getEnvVarNames, UserConfigField } from "~/api";
import { envVarOverrideEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { Code } from "~/components/Code.tsx";

import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";
import { inlineCodeStyle } from "./settingsStyles.ts";

type EnvironmentVariablesSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

type EnvData = {
  globalVarNames: Array<string>;
  globalEnvPath: string;
  projects: Array<ProjectEnvVarNames>;
};

export const EnvironmentVariablesSection = ({ onSettingChange }: EnvironmentVariablesSectionProps): ReactElement => {
  const isEnvVarOverrideEnabled = useAtomValue(envVarOverrideEnabledAtom);
  const [envData, setEnvData] = useState<EnvData | null>(null);
  const globalEnvPath = envData?.globalEnvPath ?? "~/.sculptor/.env";

  const fetchData = useCallback(async () => {
    try {
      const response = await getEnvVarNames({ meta: { skipWsAck: true } });
      if (response.data) {
        setEnvData({
          globalVarNames: response.data.globalVarNames,
          globalEnvPath: response.data.globalEnvPath,
          projects: response.data.projects,
        });
      }
    } catch {
      setEnvData(null);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const hasGlobalVars = envData !== null && envData.globalVarNames.length > 0;
  const hasProjectVars = envData !== null && envData.projects.length > 0;
  const hasAnyVars = hasGlobalVars || hasProjectVars;

  return (
    <SettingsSectionLayout description="View environment variables available to agents.">
      <SettingRow
        title="Environment variables"
        description={`Load environment variables from .env files. Global variables are set in ${globalEnvPath} and apply to all repos. Repo-specific variables are set in .sculptor/.env at your repository root and override global ones.`}
        footer={
          <Flex direction="column" gap="1" mt="2">
            <Text size="2" as="p" style={{ color: "var(--gray-11)" }}>
              <Text weight="bold">Global (all repos):</Text> Place a{" "}
              <Code size="2" style={inlineCodeStyle}>
                .env
              </Code>{" "}
              file at{" "}
              <Code size="2" style={inlineCodeStyle}>
                {globalEnvPath}
              </Code>{" "}
              with{" "}
              <Code size="2" style={inlineCodeStyle}>
                VAR=VALUE
              </Code>{" "}
              entries.
            </Text>
            <Text size="2" as="p" style={{ color: "var(--gray-11)" }}>
              <Text weight="bold">Per-repo:</Text> Place a{" "}
              <Code size="2" style={inlineCodeStyle}>
                .env
              </Code>{" "}
              file at{" "}
              <Code size="2" style={inlineCodeStyle}>
                .sculptor/.env
              </Code>{" "}
              in your repository root. Add it to your{" "}
              <Code size="2" style={inlineCodeStyle}>
                .gitignore
              </Code>
              .
            </Text>
          </Flex>
        }
      >
        <span />
      </SettingRow>

      <SettingRow
        title="Override existing variables"
        description="When enabled, values from .sculptor/.env take precedence over shell environment variables. This applies to all repos."
      >
        <Switch
          checked={isEnvVarOverrideEnabled}
          onCheckedChange={(checked) => onSettingChange(UserConfigField.ENV_VAR_OVERRIDE_ENABLED, checked)}
          data-testid={ElementIds.SETTINGS_ENV_VAR_OVERRIDE_TOGGLE}
        />
      </SettingRow>

      <SettingRow title="Loaded variables" description="Variables loaded from .env files across your repos.">
        <Button variant="soft" onClick={() => void fetchData()}>
          <RefreshCw size={14} />
          Refresh
        </Button>
      </SettingRow>

      <Flex direction="column" gap="4" pt="4" data-testid={ElementIds.SETTINGS_ENV_VAR_NAMES_LIST}>
        {envData === null ? null : !hasAnyVars ? (
          <Text size="2" color="gray">
            No variables loaded
          </Text>
        ) : (
          <>
            {hasGlobalVars ? (
              <Flex direction="column" gap="2" align="start">
                <Text size="2" weight="medium">
                  Variables defined across all repos
                </Text>
                <Flex direction="column" gap="1" align="start">
                  {envData.globalVarNames.map((name: string) => (
                    <Code key={name} size="2" style={inlineCodeStyle}>
                      {name}
                    </Code>
                  ))}
                </Flex>
              </Flex>
            ) : null}
            {hasProjectVars ? (
              <Flex direction="column" gap="3" align="start">
                <Flex direction="column">
                  <Text size="2" weight="medium">
                    Repo-specific variables
                  </Text>
                  <Text size="2" style={{ color: "var(--gray-11)" }}>
                    Variables defined per repo
                  </Text>
                </Flex>
                {envData.projects.map((project) => (
                  <Flex key={project.projectPath} direction="column" gap="1" align="start">
                    <Text size="2" weight="medium">
                      {project.projectName}{" "}
                      <Code size="2" style={inlineCodeStyle}>
                        {project.projectPath}
                      </Code>
                    </Text>
                    <Flex direction="column" gap="1" align="start">
                      {project.varNames.map((name: string) => (
                        <Code key={name} size="2" style={inlineCodeStyle}>
                          {name}
                        </Code>
                      ))}
                    </Flex>
                  </Flex>
                ))}
              </Flex>
            ) : null}
          </>
        )}
      </Flex>
    </SettingsSectionLayout>
  );
};
