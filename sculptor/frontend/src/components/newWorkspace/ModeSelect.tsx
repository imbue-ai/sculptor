import { Flex, Select, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { BlocksIcon } from "lucide-react";
import type { ReactElement } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy as Strategy } from "~/api";
import { isCloneWorkspacesEnabledAtom, isInPlaceWorkspacesEnabledAtom } from "~/common/state/atoms/userConfig.ts";

type ModeSelectProps = {
  value: WorkspaceInitializationStrategy;
  onChange: (value: WorkspaceInitializationStrategy) => void;
  className?: string;
};

const MODE_LABELS: Record<WorkspaceInitializationStrategy, string> = {
  [Strategy.WORKTREE]: "Worktree",
  [Strategy.CLONE]: "Clone",
  [Strategy.IN_PLACE]: "In-place",
};

/**
 * The worktree/clone/in-place mode picker. Extracted from the add-workspace
 * page's inline JSX. Worktree is always the default; the selector only renders
 * when an opt-in mode (clone or in-place) has been enabled, so a user with no
 * extra modes never sees a single-option dropdown.
 */
export const ModeSelect = ({ value, onChange, className }: ModeSelectProps): ReactElement | undefined => {
  // State and hooks
  const isInPlaceWorkspacesEnabled = useAtomValue(isInPlaceWorkspacesEnabledAtom);
  const isCloneWorkspacesEnabled = useAtomValue(isCloneWorkspacesEnabledAtom);

  // JSX and rendering logic
  if (!isInPlaceWorkspacesEnabled && !isCloneWorkspacesEnabled) {
    return undefined;
  }

  return (
    <Select.Root size="1" value={value} onValueChange={(next) => onChange(next as WorkspaceInitializationStrategy)}>
      <Select.Trigger variant="ghost" className={className} data-testid={ElementIds.MODE_SELECTOR}>
        <Flex align="center" gap="1">
          <BlocksIcon size={12} />
          <Text>environment</Text>
          {MODE_LABELS[value]}
        </Flex>
      </Select.Trigger>
      <Select.Content position="popper" side="bottom" sideOffset={5}>
        <Select.Item value={Strategy.WORKTREE} data-testid={ElementIds.MODE_OPTION_WORKTREE}>
          {MODE_LABELS[Strategy.WORKTREE]}
        </Select.Item>
        {isCloneWorkspacesEnabled && (
          <Select.Item value={Strategy.CLONE} data-testid={ElementIds.MODE_OPTION_CLONE}>
            {MODE_LABELS[Strategy.CLONE]}
          </Select.Item>
        )}
        {isInPlaceWorkspacesEnabled && (
          <Select.Item value={Strategy.IN_PLACE} data-testid={ElementIds.MODE_OPTION_IN_PLACE}>
            {MODE_LABELS[Strategy.IN_PLACE]}
          </Select.Item>
        )}
      </Select.Content>
    </Select.Root>
  );
};
