import { Switch, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { ElementIds, UserConfigField } from "../../../api";
import {
  defaultCloneTargetDirAtom,
  isPrPollingEnabledAtom,
  prCreationPromptAtom,
  prDefaultTargetBranchAtom,
  prPollClosedMultiplierAtom,
  prPollIntervalAtom,
} from "../../../common/state/atoms/userConfig.ts";
import { GlobalDefaultsSection } from "./GlobalDefaultsSection.tsx";
import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";
import { TextAreaSettingRow } from "./TextAreaSettingRow.tsx";

const DEFAULT_PR_CREATION_PROMPT =
  "Push my changes to origin and create a pull request using the GitHub CLI (gh). Write a clear description summarizing the changes.";

const MIN_POLL_INTERVAL_SECONDS = 10;
const MAX_POLL_INTERVAL_SECONDS = 300;
const MIN_CLOSED_MULTIPLIER = 1;
const MAX_CLOSED_MULTIPLIER = 120;

type GitSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const GitSettingsSection = ({ onSettingChange }: GitSettingsSectionProps): ReactElement => {
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const isPrPollingEnabled = useAtomValue(isPrPollingEnabledAtom);
  const prPollInterval = useAtomValue(prPollIntervalAtom);
  const prPollClosedMultiplier = useAtomValue(prPollClosedMultiplierAtom);
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);
  const defaultCloneTargetDir = useAtomValue(defaultCloneTargetDirAtom);

  const [pollIntervalValue, setPollIntervalValue] = useState(String(prPollInterval));
  const [closedMultiplierValue, setClosedMultiplierValue] = useState(String(prPollClosedMultiplier));
  const [targetBranchValue, setTargetBranchValue] = useState(prDefaultTargetBranch);
  const [cloneTargetDirValue, setCloneTargetDirValue] = useState(defaultCloneTargetDir);

  useEffect(() => setPollIntervalValue(String(prPollInterval)), [prPollInterval]);
  useEffect(() => setClosedMultiplierValue(String(prPollClosedMultiplier)), [prPollClosedMultiplier]);
  useEffect(() => setTargetBranchValue(prDefaultTargetBranch), [prDefaultTargetBranch]);
  useEffect(() => setCloneTargetDirValue(defaultCloneTargetDir), [defaultCloneTargetDir]);

  const handlePollIntervalBlur = (): void => {
    const parsed = parseInt(pollIntervalValue, 10);
    if (isNaN(parsed) || parsed < MIN_POLL_INTERVAL_SECONDS || parsed > MAX_POLL_INTERVAL_SECONDS) {
      setPollIntervalValue(String(prPollInterval));
      return;
    }

    if (parsed !== prPollInterval) {
      void onSettingChange(UserConfigField.PR_POLL_INTERVAL_SECONDS, parsed);
    }
  };

  const handleClosedMultiplierBlur = (): void => {
    const parsed = parseInt(closedMultiplierValue, 10);
    if (isNaN(parsed) || parsed < MIN_CLOSED_MULTIPLIER || parsed > MAX_CLOSED_MULTIPLIER) {
      setClosedMultiplierValue(String(prPollClosedMultiplier));
      return;
    }

    if (parsed !== prPollClosedMultiplier) {
      void onSettingChange(UserConfigField.PR_POLL_CLOSED_MULTIPLIER, parsed);
    }
  };

  const handleTargetBranchBlur = (): void => {
    const trimmed = targetBranchValue.trim();
    if (!trimmed) {
      setTargetBranchValue(prDefaultTargetBranch);
      return;
    }

    if (trimmed !== prDefaultTargetBranch) {
      void onSettingChange(UserConfigField.PR_DEFAULT_TARGET_BRANCH, trimmed);
    }
  };

  const handleCloneTargetDirBlur = (): void => {
    const trimmed = cloneTargetDirValue.trim();
    if (trimmed !== defaultCloneTargetDir) {
      onSettingChange("defaultCloneTargetDir" as UserConfigField, trimmed);
    }
    setCloneTargetDirValue(trimmed);
  };

  return (
    <SettingsSectionLayout description="Configure how Sculptor interacts with Git.">
      <TextAreaSettingRow
        title="PR Creation Prompt"
        description="The prompt sent to the agent when you click Create PR."
        value={prCreationPrompt}
        defaultValue={DEFAULT_PR_CREATION_PROMPT}
        onSave={(value) => onSettingChange(UserConfigField.PR_CREATION_PROMPT, value)}
      />

      <SettingRow
        title="Enable PR Status Polling"
        description="When off, Sculptor stops calling gh to refresh PR status. The workspace banner keeps showing the last cached status."
      >
        <Switch
          checked={isPrPollingEnabled}
          onCheckedChange={(checked) => onSettingChange(UserConfigField.PR_POLLING_ENABLED, checked)}
          data-testid={ElementIds.SETTINGS_POLLING_ENABLED_TOGGLE}
        />
      </SettingRow>

      <SettingRow
        title="Status Poll Interval"
        description="How often to check for PR status updates on open workspaces. Lower values provide faster updates but use more API calls."
      >
        <TextField.Root
          type="number"
          min={MIN_POLL_INTERVAL_SECONDS}
          max={MAX_POLL_INTERVAL_SECONDS}
          value={pollIntervalValue}
          onChange={(e) => setPollIntervalValue(e.target.value)}
          onBlur={handlePollIntervalBlur}
          disabled={!isPrPollingEnabled}
          data-testid={ElementIds.SETTINGS_POLL_INTERVAL_INPUT}
          style={{ width: 140 }}
        >
          <TextField.Slot side="right">
            <Text size="1" color="gray">
              seconds
            </Text>
          </TextField.Slot>
        </TextField.Root>
      </SettingRow>

      <SettingRow
        title="Closed Workspace Multiplier"
        description="Closed workspaces poll less often than the interval above by this multiple. Default 6 means closed workspaces poll every 6× the open interval."
      >
        <TextField.Root
          type="number"
          min={MIN_CLOSED_MULTIPLIER}
          max={MAX_CLOSED_MULTIPLIER}
          value={closedMultiplierValue}
          onChange={(e) => setClosedMultiplierValue(e.target.value)}
          onBlur={handleClosedMultiplierBlur}
          disabled={!isPrPollingEnabled}
          data-testid={ElementIds.SETTINGS_POLL_CLOSED_MULTIPLIER_INPUT}
          style={{ width: 140 }}
        >
          <TextField.Slot side="right">
            <Text size="1" color="gray">
              ×
            </Text>
          </TextField.Slot>
        </TextField.Root>
      </SettingRow>

      <SettingRow
        title="Default Target Branch"
        description="The default target branch for new workspaces. Can be overridden per-workspace in the banner."
      >
        <TextField.Root
          value={targetBranchValue}
          onChange={(e) => setTargetBranchValue(e.target.value)}
          onBlur={handleTargetBranchBlur}
          data-testid={ElementIds.SETTINGS_DEFAULT_TARGET_BRANCH_INPUT}
          style={{ width: 200 }}
        />
      </SettingRow>

      <SettingRow
        title="Default Target Folder"
        description="Pre-fills the Target Folder field when cloning a repo from GitHub. Leave empty to default to ~/.sculptor/repos/github."
      >
        <TextField.Root
          placeholder="~/.sculptor/repos"
          value={cloneTargetDirValue}
          onChange={(e) => setCloneTargetDirValue(e.target.value)}
          onBlur={handleCloneTargetDirBlur}
          data-testid={ElementIds.SETTINGS_DEFAULT_CLONE_TARGET_DIR_INPUT}
          style={{ width: 240 }}
        />
      </SettingRow>

      <GlobalDefaultsSection onSettingChange={onSettingChange} />
    </SettingsSectionLayout>
  );
};
