import { Select } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { UserConfigField } from "~/api";
import {
  commitPromptAtom,
  DEFAULT_COMMIT_PROMPT,
  fileBrowserDiffViewTypeAtom,
  fileBrowserLineWrappingAtom,
} from "~/common/state/atoms/userConfig.ts";

import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";
import { TextAreaSettingRow } from "./TextAreaSettingRow.tsx";

type FileBrowserSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const FileBrowserSettingsSection = ({ onSettingChange }: FileBrowserSettingsSectionProps): ReactElement => {
  const lineWrapping = useAtomValue(fileBrowserLineWrappingAtom);
  const diffViewType = useAtomValue(fileBrowserDiffViewTypeAtom);
  const commitPrompt = useAtomValue(commitPromptAtom);

  return (
    <SettingsSectionLayout description="Customize how files and diffs are displayed.">
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
