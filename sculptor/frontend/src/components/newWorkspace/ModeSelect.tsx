import { Button, Flex, Select, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { BlocksIcon } from "lucide-react";
import type { ReactElement } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy as Strategy } from "~/api";
import { isCloneWorkspacesEnabledAtom, isInPlaceWorkspacesEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { type IsolatedCreationMode, offeredCreationModes } from "~/common/utils/workspaceModeRules.ts";

type ModeSelectProps = {
  value: WorkspaceInitializationStrategy;
  /** The repository's own isolated mode: a worktree, or a jj workspace when the repository uses jj. */
  isolatedMode: IsolatedCreationMode;
  onChange: (value: WorkspaceInitializationStrategy) => void;
  /** Opens the repository's settings, where its jj setting lives. */
  onOpenRepositorySettings: () => void;
  className?: string;
};

const MODE_LABELS: Record<WorkspaceInitializationStrategy, string> = {
  [Strategy.WORKTREE]: "Worktree",
  [Strategy.CLONE]: "Clone",
  [Strategy.IN_PLACE]: "In-place",
  [Strategy.JJ_WORKSPACE]: "jj workspace",
};

const MODE_OPTION_TEST_IDS: Record<WorkspaceInitializationStrategy, string> = {
  [Strategy.WORKTREE]: ElementIds.MODE_OPTION_WORKTREE,
  [Strategy.CLONE]: ElementIds.MODE_OPTION_CLONE,
  [Strategy.IN_PLACE]: ElementIds.MODE_OPTION_IN_PLACE,
  [Strategy.JJ_WORKSPACE]: ElementIds.MODE_OPTION_JJ_WORKSPACE,
};

const ModeTriggerContent = ({ value }: { value: WorkspaceInitializationStrategy }): ReactElement => (
  <Flex align="center" gap="1">
    <BlocksIcon size={12} />
    <Text size="1" color="gray">
      environment
    </Text>
    <Text size="1" weight="medium" color="gray" highContrast>
      {MODE_LABELS[value]}
    </Text>
  </Flex>
);

/**
 * The mode picker. The repository's isolated mode is always available: a
 * worktree, or a jj workspace in a repository that uses jj for new workspaces.
 * Clone and in-place are opt-in.
 *
 * When the isolated mode is the only reachable one, a worktree shows nothing,
 * so a user with no extra modes never sees a single-option dropdown; a jj
 * workspace shows a chip that says so and links to the repository's settings,
 * because the choice of jj is made there. An opt-in mode whose flag is now off
 * stays offered while it is the value (e.g. seeded from a persisted choice), so
 * the user is never trapped in it (in-place in particular mutates the user's
 * real repo).
 */
export const ModeSelect = ({
  value,
  isolatedMode,
  onChange,
  onOpenRepositorySettings,
  className,
}: ModeSelectProps): ReactElement | undefined => {
  // State and hooks
  const isInPlaceEnabled = useAtomValue(isInPlaceWorkspacesEnabledAtom);
  const isCloneEnabled = useAtomValue(isCloneWorkspacesEnabledAtom);

  // JSX and rendering logic
  const modes = offeredCreationModes({ isolatedMode, value, isCloneEnabled, isInPlaceEnabled });

  if (modes.length === 1) {
    if (isolatedMode === Strategy.WORKTREE) {
      return undefined;
    }
    return (
      <Tooltip content="This repository creates jj workspaces. Change that in its settings.">
        <Button
          variant="ghost"
          size="1"
          className={className}
          onClick={onOpenRepositorySettings}
          data-testid={ElementIds.MODE_SELECTOR}
        >
          <ModeTriggerContent value={value} />
        </Button>
      </Tooltip>
    );
  }

  return (
    <Select.Root size="1" value={value} onValueChange={(next) => onChange(next as WorkspaceInitializationStrategy)}>
      <Select.Trigger variant="ghost" className={className} data-testid={ElementIds.MODE_SELECTOR}>
        <ModeTriggerContent value={value} />
      </Select.Trigger>
      <Select.Content position="popper" side="bottom" sideOffset={5}>
        {modes.map((mode) => (
          <Select.Item key={mode} value={mode} data-testid={MODE_OPTION_TEST_IDS[mode]}>
            {MODE_LABELS[mode]}
          </Select.Item>
        ))}
      </Select.Content>
    </Select.Root>
  );
};
