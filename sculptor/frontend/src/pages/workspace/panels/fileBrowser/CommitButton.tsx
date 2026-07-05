import { Button, ContextMenu } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { CSSProperties, ReactElement } from "react";
import { useState } from "react";

import { ElementIds } from "~/api";
import { commitPromptAtom } from "~/common/state/atoms/userConfig.ts";
import { activeWorkspaceIdAtom } from "~/pages/workspace/layout/atoms/section.ts";

import { canCommitAtomFamily, commitActionAtomFamily } from "../workspaceAgentActions.ts";
import { CommitPromptDialog } from "./CommitPromptDialog.tsx";

// Fills the footer row; the row's own padding (shared with the scope picker
// above the tree) sets the inset.
const COMMIT_BUTTON_STYLE: CSSProperties = { width: "100%" };

type CommitButtonProps = {
  changesCount: number;
  /** Called after the commit message is sent. */
  onCommit?: () => void;
};

export const CommitButton = ({ changesCount, onCommit }: CommitButtonProps): ReactElement => {
  // Committing sends the prompt through the workspace-scoped action rather
  // than the mounted chat's `chatActionsAtom` closures — the Changes panel is
  // usually the active center tab, which unmounts the chat.
  const workspaceId = useAtomValue(activeWorkspaceIdAtom) ?? "";
  const canCommit = useAtomValue(canCommitAtomFamily(workspaceId));
  const sendCommitMessage = useSetAtom(commitActionAtomFamily(workspaceId));
  const commitPrompt = useAtomValue(commitPromptAtom);
  const [isPromptDialogOpen, setIsPromptDialogOpen] = useState(false);

  const isDisabled = changesCount === 0 || !canCommit;

  const handleClick = (): void => {
    void sendCommitMessage(commitPrompt);
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
