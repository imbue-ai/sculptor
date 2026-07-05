import { Box, Button, Flex, SegmentedControl, Select, Separator, Spinner, Switch } from "@radix-ui/themes";
import { useAtom, useAtomValue } from "jotai";
import { atomWithStorage } from "jotai/utils";
import { Monitor, Moon, Sun } from "lucide-react";
import { type ReactElement, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useInstallUpdate } from "~/app/hooks/useInstallUpdate.ts";
import { autoUpdateStatusAtom, updateChannelAtom } from "~/common/state/atoms/autoUpdate.ts";
import { healthCheckDataAtom } from "~/common/state/atoms/backend.ts";
import { themeBuilderSettingsAtom } from "~/common/state/atoms/themeBuilder.ts";
import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";
import type { UpdateChannel } from "~/common/types/backend.ts";
import { getUpdateStatusText } from "~/common/utils/autoUpdate.ts";
import { ModelSelectOptions } from "~/components/ModelSelectOptions.tsx";

import { ElementIds, UserConfigField } from "../../api";
import {
  configuredDefaultModelAtom,
  defaultEffortLevelAtom,
  isAlwaysInterruptAndSendAtom,
  isCloneWorkspacesEnabledAtom,
  isDefaultFastModeAtom,
  isEntityMentionsEnabledAtom,
  isInPlaceWorkspacesEnabledAtom,
  isPiAgentEnabledAtom,
  isSmoothStreamingUserPreferenceAtom,
  userEmailAtom,
} from "../../common/state/atoms/userConfig.ts";
import { useUserConfig } from "../../common/state/hooks/useUserConfig.ts";
import { mergeClasses } from "../../common/utils/classNames.ts";
import { optional } from "../../common/utils/optional.ts";
import { EFFORT_DISPLAY_NAMES, EFFORT_OPTIONS } from "../../components/effortConstants.ts";
import { Toast } from "../../components/Toast.tsx";
import { AccountFieldRow } from "./components/AccountFieldRow.tsx";
import { ActionsSettingsSection } from "./components/ActionsSettingsSection.tsx";
import { CustomBackendSection } from "./components/AdvancedSection.tsx";
import { CIBabysitterSettingsSection } from "./components/CIBabysitterSettingsSection.tsx";
import { DependenciesSettingsSection } from "./components/DependenciesSettingsSection.tsx";
import { EnvironmentVariablesSection } from "./components/EnvironmentVariablesSection.tsx";
import { FileBrowserSettingsSection } from "./components/FileBrowserSettingsSection.tsx";
import { GitSettingsSection } from "./components/GitSettingsSection.tsx";
import { KeybindingsSection } from "./components/KeybindingsSection.tsx";
import { PiSettingsSection } from "./components/PiSettingsSection.tsx";
import { PluginsSettingsSection } from "./components/PluginsSettingsSection.tsx";
import { ReposSection } from "./components/ReposSection.tsx";
import { SettingRow } from "./components/SettingRow.tsx";
import { SettingsSectionLayout } from "./components/SettingsSection.tsx";
import { TelemetryRow } from "./components/TelemetryRow.tsx";
import { ThemeBuilderSection } from "./components/ThemeBuilderSection.tsx";
import { SETTINGS_SECTIONS, SettingsSection, type SettingsSectionId } from "./sections.ts";
import styles from "./SettingsPage.module.scss";

type SettingsSection = SettingsSectionId;

// Both maps are pure projections of the module-level SETTINGS_SECTIONS
// registry, so they're hoisted out of the component to avoid rebuilding
// them on every render.
const SECTION_DISPLAY_NAMES: Partial<Record<SettingsSection, string>> = Object.fromEntries(
  SETTINGS_SECTIONS.map((s) => [s.id, s.displayName]),
);
const SECTION_TEST_IDS: Partial<Record<SettingsSection, string>> = Object.fromEntries(
  SETTINGS_SECTIONS.map((s) => [s.id, s.testId]),
);
const getDisplayName = (section: SettingsSection): string => SECTION_DISPLAY_NAMES[section] ?? section;

const activeSectionAtom = atomWithStorage<SettingsSection>("sculptor-settings-active-section", SettingsSection.GENERAL);

export const SettingsPage = (): ReactElement => {
  const [storedSection, setActiveSection] = useAtom(activeSectionAtom);
  // A persisted section id can outlive the section it names (e.g. a section that
  // existed in an earlier build is gone here). An unknown value would leave the
  // nav unhighlighted, the mobile Select trigger blank, and every content branch
  // false — so fall back to General, mirroring the ?section= guard below.
  const activeSection: SettingsSection = (Object.values(SettingsSection) as Array<string>).includes(storedSection)
    ? storedSection
    : SettingsSection.GENERAL;
  const [searchParams] = useSearchParams();
  const { install, isInstalling } = useInstallUpdate();

  // Apply ?section= query param once on mount (e.g. when linked from an error block).
  useEffect(() => {
    const sectionParam = searchParams.get("section");
    if (sectionParam && (Object.values(SettingsSection) as Array<string>).includes(sectionParam)) {
      setActiveSection(sectionParam as SettingsSection);
    }
  }, [searchParams, setActiveSection]);
  const [themeSettings, setThemeSettings] = useAtom(themeBuilderSettingsAtom);
  const configuredDefaultModel = useAtomValue(configuredDefaultModelAtom);
  const userEmail = useAtomValue(userEmailAtom);
  const isAlwaysInterruptAndSend = useAtomValue(isAlwaysInterruptAndSendAtom);
  const isInPlaceWorkspacesEnabled = useAtomValue(isInPlaceWorkspacesEnabledAtom);
  const isCloneWorkspacesEnabled = useAtomValue(isCloneWorkspacesEnabledAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const isEntityMentionsEnabled = useAtomValue(isEntityMentionsEnabledAtom);
  const isSmoothStreamingEnabled = useAtomValue(isSmoothStreamingUserPreferenceAtom);
  const isDefaultFastMode = useAtomValue(isDefaultFastModeAtom);
  const defaultEffortLevel = useAtomValue(defaultEffortLevelAtom);
  const autoUpdateStatus = useAtomValue(autoUpdateStatusAtom);
  const [updateChannel, setUpdateChannel] = useAtom(updateChannelAtom);
  const healthCheckData = useAtomValue(healthCheckDataAtom);
  const [isChannelSwitching, setIsChannelSwitching] = useState(false);
  const [toast, setToast] = useState<ToastContent | null>(null);

  const { updateField } = useUserConfig();

  const handleSettingChange = async (fieldConstant: UserConfigField, value: unknown): Promise<void> => {
    try {
      await updateField(fieldConstant, value);
      setToast({
        type: ToastType.SUCCESS,
        title: "Setting updated",
      });
    } catch (error) {
      console.error(`Failed to update ${fieldConstant}:`, error);
      setToast({
        type: ToastType.ERROR,
        title: `Failed to update setting`,
      });
    }
  };

  const handleUpdateChannelChange = async (channel: UpdateChannel): Promise<void> => {
    if (!window.sculptor) return;
    setIsChannelSwitching(true);
    try {
      await window.sculptor.setUpdateChannel(channel);
      setUpdateChannel(channel);
    } catch (error) {
      console.error("Failed to set update channel:", error);
      setToast({
        type: ToastType.ERROR,
        title: "Failed to change update channel",
      });
    } finally {
      setIsChannelSwitching(false);
    }
  };

  const handleCheckForUpdates = async (): Promise<void> => {
    if (!window.sculptor) return;
    try {
      await window.sculptor.checkForUpdate();
    } catch (error) {
      console.error("Failed to check for updates:", error);
    }
  };

  return (
    <>
      <Flex
        direction="column"
        className={styles.container}
        style={{ containerName: "settings-page", containerType: "inline-size" }}
      >
        <Flex position="relative" flexGrow="1" data-testid={ElementIds.SETTINGS_PAGE} minHeight="0" overflow="hidden">
          <Flex direction="column" px="6" pt="8" pb="4" className={styles.sidebar}>
            <Flex direction="column" gap="2">
              {SETTINGS_SECTIONS.map(({ id }) => (
                <Box key={id}>
                  {id === SettingsSection.EXPERIMENTAL && <Separator size="4" my="2" className={styles.navSeparator} />}
                  <Box
                    className={mergeClasses(styles.navItem, optional(activeSection === id, styles.active))}
                    onClick={() => setActiveSection(id)}
                    px="3"
                    py="2"
                    data-testid={SECTION_TEST_IDS[id] ?? ""}
                  >
                    {getDisplayName(id)}
                  </Box>
                </Box>
              ))}
            </Flex>
          </Flex>
          <div className={styles.contentScroll} data-testid={ElementIds.SETTINGS_CONTENT}>
            <Flex direction="column" className={styles.mobileNav} px="5" pt="5">
              <Select.Root value={activeSection} onValueChange={(value) => setActiveSection(value as SettingsSection)}>
                <Select.Trigger variant="soft" />
                <Select.Content>
                  {SETTINGS_SECTIONS.map(({ id }) => (
                    <Select.Item key={id} value={id} data-testid={SECTION_TEST_IDS[id] ?? ""}>
                      {getDisplayName(id)}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Flex>
            <Flex className={styles.contentArea}>
              {activeSection === SettingsSection.GENERAL && (
                <SettingsSectionLayout description="General application preferences.">
                  <SettingRow title="Theme" description="Control the appearance of Sculptor">
                    <SegmentedControl.Root
                      value={themeSettings.appearance}
                      onValueChange={(value) =>
                        setThemeSettings((prev) => ({
                          ...prev,
                          appearance: value as "light" | "dark" | "system",
                        }))
                      }
                      size="2"
                      className={styles.themeToggle}
                      data-testid={ElementIds.SETTINGS_THEME_SELECT}
                    >
                      <SegmentedControl.Item value="light">
                        <Flex align="center" gap="1">
                          <Sun size={16} />
                          Light
                        </Flex>
                      </SegmentedControl.Item>
                      <SegmentedControl.Item value="dark">
                        <Flex align="center" gap="1">
                          <Moon size={16} />
                          Dark
                        </Flex>
                      </SegmentedControl.Item>
                      <SegmentedControl.Item value="system">
                        <Flex align="center" gap="1">
                          <Monitor size={16} />
                          System
                        </Flex>
                      </SegmentedControl.Item>
                    </SegmentedControl.Root>
                  </SettingRow>

                  <SettingRow
                    title="Software Updates"
                    description={getUpdateStatusText(autoUpdateStatus, updateChannel, healthCheckData?.version)}
                  >
                    <Flex align="center" gap="2">
                      <Select.Root
                        value={updateChannel ?? ""}
                        onValueChange={(value) => handleUpdateChannelChange(value as UpdateChannel)}
                        disabled={
                          !window.sculptor ||
                          isChannelSwitching ||
                          updateChannel === null ||
                          autoUpdateStatus?.type === "disabled"
                        }
                      >
                        <Select.Trigger
                          variant="soft"
                          data-testid={ElementIds.SETTINGS_UPDATE_CHANNEL_SELECT}
                          placeholder="N/A"
                        />
                        <Select.Content>
                          <Select.Item value="STABLE" data-testid={ElementIds.SETTINGS_UPDATE_CHANNEL_OPTION_STABLE}>
                            Stable
                          </Select.Item>
                          <Select.Item value="RC" data-testid={ElementIds.SETTINGS_UPDATE_CHANNEL_OPTION_RC}>
                            Latest
                          </Select.Item>
                        </Select.Content>
                      </Select.Root>
                      {autoUpdateStatus?.type === "ready" && (
                        <Button
                          variant="soft"
                          disabled={isInstalling}
                          onClick={install}
                          data-testid={ElementIds.SETTINGS_INSTALL_UPDATE_BUTTON}
                        >
                          {isInstalling ? "Restarting..." : "Install and restart"}
                        </Button>
                      )}
                      <Button
                        variant="soft"
                        onClick={handleCheckForUpdates}
                        disabled={
                          !window.sculptor ||
                          autoUpdateStatus === null ||
                          autoUpdateStatus.type === "checking" ||
                          autoUpdateStatus.type === "disabled"
                        }
                        data-testid={ElementIds.SETTINGS_CHECK_FOR_UPDATES_BUTTON}
                      >
                        {autoUpdateStatus?.type === "checking" ? (
                          <Flex align="center" gap="2">
                            <Spinner size="1" />
                            Checking...
                          </Flex>
                        ) : (
                          "Check for updates"
                        )}
                      </Button>
                    </Flex>
                  </SettingRow>
                </SettingsSectionLayout>
              )}
              {activeSection === SettingsSection.AGENT && (
                <SettingsSectionLayout description="Configure default agent behavior and model preferences.">
                  <SettingRow title="Default Model" description="Select the default model for new agents.">
                    <Select.Root
                      value={configuredDefaultModel ?? "None"}
                      onValueChange={(value) => {
                        if (value === "None") {
                          handleSettingChange(UserConfigField.DEFAULT_LLM, null);
                        } else {
                          handleSettingChange(UserConfigField.DEFAULT_LLM, value);
                        }
                      }}
                    >
                      <Select.Trigger
                        variant="soft"
                        className={styles.settingControl}
                        data-testid={ElementIds.SETTINGS_DEFAULT_MODEL_SELECT}
                      />
                      <Select.Content>
                        <Select.Item key="None" value="None">
                          Most Recently Used
                        </Select.Item>
                        <ModelSelectOptions optionTestId={ElementIds.SETTINGS_DEFAULT_MODEL_OPTION} />
                      </Select.Content>
                    </Select.Root>
                  </SettingRow>

                  <SettingRow
                    title="Fast Mode"
                    description="When enabled, new agents default to fast mode for faster output."
                  >
                    <Switch
                      checked={isDefaultFastMode}
                      onCheckedChange={(checked) => handleSettingChange(UserConfigField.DEFAULT_FAST_MODE, checked)}
                      data-testid={ElementIds.SETTINGS_DEFAULT_FAST_MODE_TOGGLE}
                    />
                  </SettingRow>

                  <SettingRow title="Effort Level" description="Default thinking effort level for new agents.">
                    <Select.Root
                      value={defaultEffortLevel}
                      onValueChange={(value) => handleSettingChange(UserConfigField.DEFAULT_EFFORT_LEVEL, value)}
                    >
                      <Select.Trigger
                        variant="soft"
                        className={styles.settingControl}
                        data-testid={ElementIds.SETTINGS_DEFAULT_EFFORT_LEVEL_SELECT}
                      />
                      <Select.Content>
                        {EFFORT_OPTIONS.map((level) => (
                          <Select.Item
                            key={level}
                            value={level}
                            data-testid={ElementIds.SETTINGS_DEFAULT_EFFORT_LEVEL_OPTION}
                          >
                            {EFFORT_DISPLAY_NAMES[level]}
                          </Select.Item>
                        ))}
                      </Select.Content>
                    </Select.Root>
                  </SettingRow>
                </SettingsSectionLayout>
              )}
              {activeSection === SettingsSection.DEPENDENCIES && (
                <DependenciesSettingsSection onSettingChange={handleSettingChange} />
              )}
              {activeSection === SettingsSection.PI && (
                <PiSettingsSection
                  onSettingChange={handleSettingChange}
                  onNavigateToExperimental={() => setActiveSection(SettingsSection.EXPERIMENTAL)}
                />
              )}
              {activeSection === SettingsSection.KEYBINDINGS && (
                <KeybindingsSection onSettingChange={handleSettingChange} />
              )}
              {activeSection === SettingsSection.PLUGINS && (
                <PluginsSettingsSection onSettingChange={handleSettingChange} />
              )}
              {activeSection === SettingsSection.PRIVACY && (
                <SettingsSectionLayout description="Your email and telemetry preferences.">
                  <AccountFieldRow
                    title="Email Address"
                    description="Email address associated with your account"
                    value={userEmail ?? ""}
                    elementId={ElementIds.SETTINGS_EMAIL_FIELD}
                  />
                  <TelemetryRow setToast={setToast} />
                </SettingsSectionLayout>
              )}
              {activeSection === SettingsSection.THEME_BUILDER && <ThemeBuilderSection />}
              {activeSection === SettingsSection.REPOSITORIES && <ReposSection setToast={setToast} />}
              {activeSection === SettingsSection.ACTIONS && <ActionsSettingsSection setToast={setToast} />}
              {activeSection === SettingsSection.GIT && <GitSettingsSection onSettingChange={handleSettingChange} />}
              {activeSection === SettingsSection.CI && (
                <CIBabysitterSettingsSection onSettingChange={handleSettingChange} />
              )}
              {activeSection === SettingsSection.FILE_BROWSER && (
                <FileBrowserSettingsSection onSettingChange={handleSettingChange} />
              )}
              {activeSection === SettingsSection.PROJECT_ENV_VARS && (
                <EnvironmentVariablesSection onSettingChange={handleSettingChange} />
              )}
              {activeSection === SettingsSection.EXPERIMENTAL && (
                <SettingsSectionLayout description="Features that are still being developed. These may change or be removed.">
                  <SettingRow
                    title="Always interrupt and send"
                    description="When enabled, new messages immediately interrupt the agent instead of being queued."
                  >
                    <Select.Root
                      value={isAlwaysInterruptAndSend ? "true" : "false"}
                      onValueChange={(value) =>
                        handleSettingChange(UserConfigField.IS_ALWAYS_INTERRUPT_AND_SEND, value === "true")
                      }
                    >
                      <Select.Trigger variant="soft" data-testid={ElementIds.SETTINGS_ALWAYS_INTERRUPT_SELECT} />
                      <Select.Content>
                        <Select.Item value="false" data-testid={ElementIds.SETTINGS_ALWAYS_INTERRUPT_DISABLED_OPTION}>
                          Disabled
                        </Select.Item>
                        <Select.Item value="true" data-testid={ElementIds.SETTINGS_ALWAYS_INTERRUPT_OPTION}>
                          Enabled
                        </Select.Item>
                      </Select.Content>
                    </Select.Root>
                  </SettingRow>
                  <SettingRow
                    title="Smooth Streaming"
                    description="Smoothly animate text as it streams in, rather than showing it in bursts."
                  >
                    <Switch
                      checked={isSmoothStreamingEnabled}
                      onCheckedChange={(checked) =>
                        handleSettingChange(UserConfigField.IS_SMOOTH_STREAMING_ENABLED, checked)
                      }
                    />
                  </SettingRow>
                  <SettingRow
                    title="In-place workspaces"
                    description="Allow creating in-place workspaces that operate directly in your repository instead of a clone."
                  >
                    <Switch
                      checked={isInPlaceWorkspacesEnabled}
                      onCheckedChange={(checked) =>
                        handleSettingChange(UserConfigField.ENABLE_IN_PLACE_WORKSPACES, checked)
                      }
                      data-testid={ElementIds.SETTINGS_ENABLE_IN_PLACE_WORKSPACES_TOGGLE}
                    />
                  </SettingRow>
                  <SettingRow
                    title="Clone workspaces"
                    description="Worktree workspaces are now the default. Enable this to also offer the older clone mode (full git clone with a separate `local` remote and explicit sync-back) in the Add Workspace mode picker."
                  >
                    <Switch
                      checked={isCloneWorkspacesEnabled}
                      onCheckedChange={(checked) =>
                        handleSettingChange(UserConfigField.ENABLE_CLONE_WORKSPACES, checked)
                      }
                      data-testid={ElementIds.SETTINGS_ENABLE_CLONE_WORKSPACES_TOGGLE}
                    />
                  </SettingRow>
                  <SettingRow
                    title="Entity Mentions"
                    description="Type + in the chat input to mention repositories, workspaces, and agents."
                  >
                    <Switch
                      checked={isEntityMentionsEnabled}
                      onCheckedChange={(checked) =>
                        handleSettingChange(UserConfigField.ENABLE_ENTITY_MENTIONS, checked)
                      }
                      data-testid={ElementIds.SETTINGS_ENABLE_ENTITY_MENTIONS_TOGGLE}
                    />
                  </SettingRow>
                  <SettingRow
                    title="Pi agent"
                    description="Offer the experimental pi agent as a choice when creating new agents."
                  >
                    <Switch
                      checked={isPiAgentEnabled}
                      onCheckedChange={(checked) => handleSettingChange(UserConfigField.ENABLE_PI_AGENT, checked)}
                      data-testid={ElementIds.SETTINGS_ENABLE_PI_AGENT_TOGGLE}
                    />
                  </SettingRow>
                  <CustomBackendSection setToast={setToast} />
                </SettingsSectionLayout>
              )}
            </Flex>
          </div>
        </Flex>
      </Flex>
      <Toast
        open={!!toast}
        onOpenChange={(open) => !open && setToast(null)}
        title={toast?.title}
        description={toast?.description}
        type={toast?.type}
      />
    </>
  );
};
