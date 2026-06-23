import { Select, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { FocusEvent, ReactElement } from "react";
import { Fragment } from "react";

import { ElementIds, UserConfigField } from "~/api";
import {
  defaultWorkspaceBranchNamingPatternAtom,
  workspaceBranchDeletionPolicyAtom,
} from "~/common/state/atoms/userConfig.ts";

import { SettingRow } from "./SettingRow.tsx";

const DEFAULT_PATTERN_FALLBACK = "<user>/<slug>";

type GlobalDefaultsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const GlobalDefaultsSection = ({ onSettingChange }: GlobalDefaultsSectionProps): ReactElement => {
  const defaultPattern = useAtomValue(defaultWorkspaceBranchNamingPatternAtom);
  const deletionPolicy = useAtomValue(workspaceBranchDeletionPolicyAtom);

  const handlePatternBlur = (e: FocusEvent<HTMLInputElement>): void => {
    const trimmed = e.target.value.trim() || DEFAULT_PATTERN_FALLBACK;
    if (trimmed !== defaultPattern) {
      void onSettingChange(UserConfigField.DEFAULT_WORKSPACE_BRANCH_NAMING_PATTERN, trimmed);
    } else if (e.target.value !== trimmed) {
      // The trimmed value matches the saved value; just normalise the input to drop whitespace.
      e.target.value = trimmed;
    }
  };

  return (
    <Fragment>
      <SettingRow
        title="Default branch-naming pattern"
        description="Used by clone and worktree workspace creation. Supports <user> and <slug> placeholders. Per-repo overrides on Repositories."
      >
        {/* Uncontrolled: `key` re-mounts the input when the saved pattern changes,
            so we never copy the prop into local state. */}
        <TextField.Root
          key={defaultPattern}
          defaultValue={defaultPattern}
          onBlur={handlePatternBlur}
          placeholder={DEFAULT_PATTERN_FALLBACK}
          spellCheck={false}
          data-testid={ElementIds.SETTINGS_GLOBAL_NAMING_PATTERN_INPUT}
          style={{ width: 200 }}
        />
      </SettingRow>
      <SettingRow
        title="Branch deletion when worktree workspace is removed"
        description="“Delete if safe” refuses to delete unmerged branches. “Always” force-deletes regardless. Only applies to worktree-mode workspaces."
      >
        <Select.Root
          value={deletionPolicy}
          onValueChange={(value) => {
            void onSettingChange(UserConfigField.WORKSPACE_BRANCH_DELETION_POLICY, value);
          }}
        >
          <Select.Trigger data-testid={ElementIds.SETTINGS_BRANCH_DELETION_POLICY_SELECT} />
          <Select.Content>
            <Select.Item value="never">
              <Text>Never</Text>
            </Select.Item>
            <Select.Item value="delete_if_safe">
              <Text>Delete if safe (default)</Text>
            </Select.Item>
            <Select.Item value="always">
              <Text>Always</Text>
            </Select.Item>
          </Select.Content>
        </Select.Root>
      </SettingRow>
    </Fragment>
  );
};
