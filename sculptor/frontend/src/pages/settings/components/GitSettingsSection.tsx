import { Switch, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { ElementIds, type UserConfigField } from "../../../api";
import {
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
  "Push my changes to origin and create a pull request. Check whether the repo uses GitHub (gh) or GitLab (glab) and use the appropriate tool. Write a clear description summarizing the changes.";

type GitSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const GitSettingsSection = ({ onSettingChange }: GitSettingsSectionProps): ReactElement => {
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const isPrPollingEnabled = useAtomValue(isPrPollingEnabledAtom);
  const prPollInterval = useAtomValue(prPollIntervalAtom);
  const prPollClosedMultiplier = useAtomValue(prPollClosedMultiplierAtom);
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);

  const [pollIntervalValue, setPollIntervalValue] = useState(String(prPollInterval));
  const [closedMultiplierValue, setClosedMultiplierValue] = useState(String(prPollClosedMultiplier));
  const [targetBranchValue, setTargetBranchValue] = useState(prDefaultTargetBranch);

  useEffect(() => setPollIntervalValue(String(prPollInterval)), [prPollInterval]);
  useEffect(() => setClosedMultiplierValue(String(prPollClosedMultiplier)), [prPollClosedMultiplier]);
  useEffect(() => setTargetBranchValue(prDefaultTargetBranch), [prDefaultTargetBranch]);

  const handlePollIntervalBlur = (): void => {
    const parsed = parseInt(pollIntervalValue, 10);
    if (isNaN(parsed) || parsed < 10 || parsed > 300) {
      setPollIntervalValue(String(prPollInterval));
      return;
    }

    if (parsed !== prPollInterval) {
      onSettingChange("prPollIntervalSeconds" as UserConfigField, parsed);
    }
  };

  const handleClosedMultiplierBlur = (): void => {
    const parsed = parseInt(closedMultiplierValue, 10);
    if (isNaN(parsed) || parsed < 1 || parsed > 120) {
      setClosedMultiplierValue(String(prPollClosedMultiplier));
      return;
    }

    if (parsed !== prPollClosedMultiplier) {
      onSettingChange("prPollClosedMultiplier" as UserConfigField, parsed);
    }
  };

  const handleTargetBranchBlur = (): void => {
    const trimmed = targetBranchValue.trim();
    if (!trimmed) {
      setTargetBranchValue(prDefaultTargetBranch);
      return;
    }

    if (trimmed !== prDefaultTargetBranch) {
      onSettingChange("prDefaultTargetBranch" as UserConfigField, trimmed);
    }
  };

  return (
    <SettingsSectionLayout description="Configure how Sculptor interacts with Git.">
      <TextAreaSettingRow
        title="PR Creation Prompt"
        description="The prompt sent to the agent when you click Create PR."
        value={prCreationPrompt}
        defaultValue={DEFAULT_PR_CREATION_PROMPT}
        onSave={(value) => onSettingChange("prCreationPrompt" as UserConfigField, value)}
      />

      <SettingRow
        title="Enable PR/MR Status Polling"
        description="When off, Sculptor stops calling gh/glab to refresh PR status. The workspace banner keeps showing the last cached status."
      >
        <Switch
          checked={isPrPollingEnabled}
          onCheckedChange={(checked) => onSettingChange("prPollingEnabled" as UserConfigField, checked)}
          data-testid={ElementIds.SETTINGS_POLLING_ENABLED_TOGGLE}
        />
      </SettingRow>

      <SettingRow
        title="Status Poll Interval"
        description="How often to check for PR status updates on open workspaces. Lower values provide faster updates but use more API calls."
      >
        <TextField.Root
          type="number"
          min={10}
          max={300}
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
          min={1}
          max={120}
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

      <GlobalDefaultsSection onSettingChange={onSettingChange} />
    </SettingsSectionLayout>
  );
};
