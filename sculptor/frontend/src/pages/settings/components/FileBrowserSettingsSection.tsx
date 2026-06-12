import { Flex, Select, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import type { UserConfigField } from "~/api";
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

type FileBrowserSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const FileBrowserSettingsSection = ({ onSettingChange }: FileBrowserSettingsSectionProps): ReactElement => {
  const splitRatio = useAtomValue(fileBrowserSplitRatioAtom);
  const tabCloseBehavior = useAtomValue(fileBrowserTabCloseBehaviorAtom);
  const lineWrapping = useAtomValue(fileBrowserLineWrappingAtom);
  const diffViewType = useAtomValue(fileBrowserDiffViewTypeAtom);
  const commitPrompt = useAtomValue(commitPromptAtom);

  const [splitRatioValue, setSplitRatioValue] = useState(String(splitRatio));

  useEffect(() => setSplitRatioValue(String(splitRatio)), [splitRatio]);

  const handleSplitRatioBlur = (): void => {
    const parsed = parseInt(splitRatioValue, 10);
    if (isNaN(parsed) || parsed < 20 || parsed > 80) {
      setSplitRatioValue(String(splitRatio));
      return;
    }

    if (parsed !== splitRatio) {
      onSettingChange("fileBrowserDefaultSplitRatio" as UserConfigField, parsed);
    }
  };

  return (
    <SettingsSectionLayout description="Customize how files and diffs are displayed.">
      <SettingRow title="Default split ratio" description="Controls the initial width ratio when the diff panel opens">
        <Flex align="center" gap="2">
          <TextField.Root
            type="number"
            min={20}
            max={80}
            step={5}
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
          onValueChange={(value) => onSettingChange("fileBrowserTabCloseBehavior" as UserConfigField, value)}
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
          onValueChange={(value) => onSettingChange("fileBrowserLineWrapping" as UserConfigField, value)}
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
          onValueChange={(value) => onSettingChange("fileBrowserDiffViewType" as UserConfigField, value)}
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
        onSave={(value) => onSettingChange("commitPrompt" as UserConfigField, value)}
      />
    </SettingsSectionLayout>
  );
};
