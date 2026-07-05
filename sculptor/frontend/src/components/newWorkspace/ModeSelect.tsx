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
 * The worktree/clone/in-place mode picker. Extracted from the addWorkspace
 * page's inline JSX. Worktree is always available; clone and in-place are opt-in.
 *
 * The selector hides itself when worktree is the only reachable mode, so a user
 * with no extra modes never sees a single-option dropdown. But if the current
 * value is an opt-in mode whose flag is now off (e.g. seeded from a persisted
 * choice), the selector still renders and still offers that mode's item, so the
 * user is never trapped in a hidden non-worktree mode with no way back to
 * worktree (in-place in particular mutates the user's real repo).
 */
export const ModeSelect = ({ value, onChange, className }: ModeSelectProps): ReactElement | undefined => {
  // State and hooks
  const isInPlaceWorkspacesEnabled = useAtomValue(isInPlaceWorkspacesEnabledAtom);
  const isCloneWorkspacesEnabled = useAtomValue(isCloneWorkspacesEnabledAtom);

  // JSX and rendering logic
  const shouldShowClone = isCloneWorkspacesEnabled || value === Strategy.CLONE;
  const shouldShowInPlace = isInPlaceWorkspacesEnabled || value === Strategy.IN_PLACE;

  if (!shouldShowClone && !shouldShowInPlace) {
    return undefined;
  }

  return (
    <Select.Root size="1" value={value} onValueChange={(next) => onChange(next as WorkspaceInitializationStrategy)}>
      <Select.Trigger variant="ghost" className={className} data-testid={ElementIds.MODE_SELECTOR}>
        <Flex align="center" gap="1">
          <BlocksIcon size={12} />
          <Text size="1" color="gray">
            environment
          </Text>
          <Text size="1" weight="medium" color="gray" highContrast>
            {MODE_LABELS[value]}
          </Text>
        </Flex>
      </Select.Trigger>
      <Select.Content position="popper" side="bottom" sideOffset={5}>
        <Select.Item value={Strategy.WORKTREE} data-testid={ElementIds.MODE_OPTION_WORKTREE}>
          {MODE_LABELS[Strategy.WORKTREE]}
        </Select.Item>
        {shouldShowClone && (
          <Select.Item value={Strategy.CLONE} data-testid={ElementIds.MODE_OPTION_CLONE}>
            {MODE_LABELS[Strategy.CLONE]}
          </Select.Item>
        )}
        {shouldShowInPlace && (
          <Select.Item value={Strategy.IN_PLACE} data-testid={ElementIds.MODE_OPTION_IN_PLACE}>
            {MODE_LABELS[Strategy.IN_PLACE]}
          </Select.Item>
        )}
      </Select.Content>
    </Select.Root>
  );
};
