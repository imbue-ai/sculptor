import { Button, ContextMenu } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { CSSProperties, ReactElement } from "react";
import { useState } from "react";

import { ElementIds } from "~/api";
import { chatActionsAtom } from "~/common/state/atoms/chatActions.ts";
import { commitPromptAtom } from "~/common/state/atoms/userConfig.ts";

import { CommitPromptDialog } from "./CommitPromptDialog.tsx";

const COMMIT_BUTTON_STYLE: CSSProperties = { minWidth: 180 };

type CommitButtonProps = {
  changesCount: number;
  /** Called after the commit message is sent. */
  onCommit?: () => void;
};

export const CommitButton = ({ changesCount, onCommit }: CommitButtonProps): ReactElement => {
  const chatActions = useAtomValue(chatActionsAtom);
  const commitPrompt = useAtomValue(commitPromptAtom);
  const [isPromptDialogOpen, setIsPromptDialogOpen] = useState(false);

  const isDisabled = changesCount === 0 || chatActions.isDisabled;

  const handleClick = (): void => {
    chatActions.sendMessage?.(commitPrompt);
    onCommit?.();
  };

  return (
    <>
      <ContextMenu.Root>
        <ContextMenu.Trigger>
          <Button
            variant="soft"
            size="1"
            color="gray"
            disabled={isDisabled}
            onClick={handleClick}
            style={COMMIT_BUTTON_STYLE}
            data-testid={ElementIds.CHANGES_COMMIT_BUTTON}
          >
            Commit {changesCount} {changesCount === 1 ? "change" : "changes"}
          </Button>
        </ContextMenu.Trigger>
        <ContextMenu.Content size="1">
          <ContextMenu.Item onSelect={() => setIsPromptDialogOpen(true)}>Edit prompt...</ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Root>
      <CommitPromptDialog open={isPromptDialogOpen} onOpenChange={setIsPromptDialogOpen} />
    </>
  );
};
