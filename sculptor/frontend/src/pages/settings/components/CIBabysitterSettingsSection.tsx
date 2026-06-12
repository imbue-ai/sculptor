import { Switch, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { type CiBabysitterConfig, ElementIds, UserConfigField } from "../../../api";
import {
  ciBabysitterMergeConflictPromptAtom,
  ciBabysitterPipelineFailedPromptAtom,
  ciBabysitterRetryCapAtom,
  isCiBabysitterEnabledAtom,
} from "../../../common/state/atoms/userConfig.ts";
import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";
import { TextAreaSettingRow } from "./TextAreaSettingRow.tsx";

const DEFAULT_PIPELINE_FAILED_PROMPT =
  "Investigate the failing pipeline for this MR, identify the root cause, fix the code, commit, and push.";
const DEFAULT_MERGE_CONFLICT_PROMPT =
  "This MR has a merge conflict with its base branch. Fetch the latest, then rebase against the base branch, resolve all conflicts, and force-push the result.";

type CIBabysitterSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const CIBabysitterSettingsSection = ({ onSettingChange }: CIBabysitterSettingsSectionProps): ReactElement => {
  const isEnabled = useAtomValue(isCiBabysitterEnabledAtom);
  const retryCap = useAtomValue(ciBabysitterRetryCapAtom);
  const pipelineFailedPrompt = useAtomValue(ciBabysitterPipelineFailedPromptAtom);
  const mergeConflictPrompt = useAtomValue(ciBabysitterMergeConflictPromptAtom);

  const [retryCapValue, setRetryCapValue] = useState(String(retryCap));

  useEffect(() => setRetryCapValue(String(retryCap)), [retryCap]);

  // Backend stores all babysitter settings in a single nested `ciBabysitter`
  // object. Each edit on this page builds a new full config from the current
  // atom values, overlays the changed field, and PUTs the whole thing.
  const commit = (overrides: Partial<CiBabysitterConfig>): Promise<void> => {
    const next: CiBabysitterConfig = {
      enabled: isEnabled,
      retryCap,
      pipelineFailedPrompt,
      mergeConflictPrompt,
      ...overrides,
    };
    return onSettingChange(UserConfigField.CI_BABYSITTER, next);
  };

  const handleRetryCapBlur = (): void => {
    const parsed = parseInt(retryCapValue, 10);
    if (isNaN(parsed) || parsed < 1 || parsed > 10) {
      setRetryCapValue(String(retryCap));
      return;
    }

    if (parsed !== retryCap) {
      void commit({ retryCap: parsed });
    }
  };

  return (
    <SettingsSectionLayout description="When enabled, Sculptor watches open MRs and asks an AI agent to fix CI failures and merge conflicts automatically. Currently only available for GitLab MRs. Coming soon for GitHub PRs.">
      <SettingRow
        title="Enable CI Babysitter"
        description="Spawn a per-workspace babysitter agent when an MR's pipeline fails or develops a merge conflict."
      >
        <Switch
          checked={isEnabled}
          onCheckedChange={(checked) => void commit({ enabled: checked })}
          data-testid={ElementIds.SETTINGS_CI_BABYSITTER_ENABLED_TOGGLE}
        />
      </SettingRow>

      <SettingRow
        title="Retry Cap"
        description="After this many babysitter prompts for an MR without a passing pipeline, no further prompts are sent until the pipeline next passes."
      >
        <TextField.Root
          type="number"
          min={1}
          max={10}
          value={retryCapValue}
          onChange={(e) => setRetryCapValue(e.target.value)}
          onBlur={handleRetryCapBlur}
          disabled={!isEnabled}
          data-testid={ElementIds.SETTINGS_CI_BABYSITTER_RETRY_CAP_INPUT}
          style={{ width: 140 }}
        >
          <TextField.Slot side="right">
            <Text size="1" color="gray">
              prompts
            </Text>
          </TextField.Slot>
        </TextField.Root>
      </SettingRow>

      <TextAreaSettingRow
        title="Pipeline Failed Prompt"
        description="Sent to the CI Babysitter when an MR's pipeline transitions to failed."
        value={pipelineFailedPrompt}
        defaultValue={DEFAULT_PIPELINE_FAILED_PROMPT}
        onSave={(value) => void commit({ pipelineFailedPrompt: value })}
        textAreaTestId={ElementIds.SETTINGS_CI_BABYSITTER_PIPELINE_PROMPT_TEXTAREA}
        disabled={!isEnabled}
      />

      <TextAreaSettingRow
        title="Merge Conflict Prompt"
        description="Sent to the CI Babysitter when an MR develops a merge conflict with its base branch."
        value={mergeConflictPrompt}
        defaultValue={DEFAULT_MERGE_CONFLICT_PROMPT}
        onSave={(value) => void commit({ mergeConflictPrompt: value })}
        textAreaTestId={ElementIds.SETTINGS_CI_BABYSITTER_MERGE_CONFLICT_PROMPT_TEXTAREA}
        disabled={!isEnabled}
      />
    </SettingsSectionLayout>
  );
};
