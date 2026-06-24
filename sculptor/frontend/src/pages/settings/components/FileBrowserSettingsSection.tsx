import { Flex, Select, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useState } from "react";

import { UserConfigField } from "~/api";
import {
  commitPromptAtom,
  DEFAULT_COMMIT_PROMPT,
  fileBrowserDiffViewTypeAtom,
  fileBrowserLineWrappingAtom,
  fileBrowserSplitRatioAtom,
  fileBrowserTabCloseBehaviorAtom,
} from "~/common/state/atoms/userConfig.ts";

import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";
import { TextAreaSettingRow } from "./TextAreaSettingRow.tsx";

const MIN_SPLIT_RATIO = 20;
const MAX_SPLIT_RATIO = 80;
const SPLIT_RATIO_STEP = 5;

type FileBrowserSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const FileBrowserSettingsSection = ({ onSettingChange }: FileBrowserSettingsSectionProps): ReactElement => {
  const splitRatio = useAtomValue(fileBrowserSplitRatioAtom);
  const tabCloseBehavior = useAtomValue(fileBrowserTabCloseBehaviorAtom);
  const lineWrapping = useAtomValue(fileBrowserLineWrappingAtom);
  const diffViewType = useAtomValue(fileBrowserDiffViewTypeAtom);
  const commitPrompt = useAtomValue(commitPromptAtom);

  // Local draft of the split-ratio input, resynced during render whenever the
  // committed atom value changes (e.g. another tab edits it or a blur rejects).
  const [splitRatioValue, setSplitRatioValue] = useState(String(splitRatio));
  const [lastSplitRatio, setLastSplitRatio] = useState(splitRatio);
  if (splitRatio !== lastSplitRatio) {
    setLastSplitRatio(splitRatio);
    setSplitRatioValue(String(splitRatio));
  }

  const handleSplitRatioBlur = (): void => {
    const parsed = parseInt(splitRatioValue, 10);
    if (isNaN(parsed) || parsed < MIN_SPLIT_RATIO || parsed > MAX_SPLIT_RATIO) {
      setSplitRatioValue(String(splitRatio));
      return;
    }

    if (parsed !== splitRatio) {
      onSettingChange(UserConfigField.FILE_BROWSER_DEFAULT_SPLIT_RATIO, parsed);
    }
  };

  return (
    <SettingsSectionLayout description="Customize how files and diffs are displayed.">
      <SettingRow title="Default split ratio" description="Controls the initial width ratio when the diff panel opens">
        <Flex align="center" gap="2">
          <TextField.Root
            type="number"
            min={MIN_SPLIT_RATIO}
            max={MAX_SPLIT_RATIO}
            step={SPLIT_RATIO_STEP}
            value={splitRatioValue}
            onChange={(e) => setSplitRatioValue(e.target.value)}
            onBlur={handleSplitRatioBlur}
            style={{ width: 80 }}
          />
          <Text size="2">%</Text>
        </Flex>
      </SettingRow>

      <SettingRow title="Tab close behavior" description="Which tab becomes active after closing the current tab">
        <Select.Root
          value={tabCloseBehavior}
          onValueChange={(value) => onSettingChange(UserConfigField.FILE_BROWSER_TAB_CLOSE_BEHAVIOR, value)}
        >
          <Select.Trigger variant="soft" />
          <Select.Content>
            <Select.Item value="mru">Most recently used</Select.Item>
            <Select.Item value="adjacent">Adjacent (right, then left)</Select.Item>
          </Select.Content>
        </Select.Root>
      </SettingRow>

      <SettingRow title="Line wrapping" description="How long lines are displayed in the diff view">
        <Select.Root
          value={lineWrapping}
          onValueChange={(value) => onSettingChange(UserConfigField.FILE_BROWSER_LINE_WRAPPING, value)}
        >
          <Select.Trigger variant="soft" />
          <Select.Content>
            <Select.Item value="wrap">Soft wrap</Select.Item>
            <Select.Item value="scroll">Horizontal scroll</Select.Item>
          </Select.Content>
        </Select.Root>
      </SettingRow>

      <SettingRow title="Default diff view" description="Default layout for viewing diffs">
        <Select.Root
          value={diffViewType}
          onValueChange={(value) => onSettingChange(UserConfigField.FILE_BROWSER_DIFF_VIEW_TYPE, value)}
        >
          <Select.Trigger variant="soft" />
          <Select.Content>
            <Select.Item value="unified">Unified</Select.Item>
            <Select.Item value="split">Split (side-by-side)</Select.Item>
          </Select.Content>
        </Select.Root>
      </SettingRow>

      <TextAreaSettingRow
        title="Commit prompt"
        description="The prompt sent to the agent when you click Commit Changes."
        value={commitPrompt}
        defaultValue={DEFAULT_COMMIT_PROMPT}
        onSave={(value) => onSettingChange(UserConfigField.COMMIT_PROMPT, value)}
      />
    </SettingsSectionLayout>
  );
};
