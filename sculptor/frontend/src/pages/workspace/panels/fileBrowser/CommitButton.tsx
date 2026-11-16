import { Button, ContextMenu } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { CSSProperties, ReactElement } from "react";
import { useState } from "react";

import { ElementIds } from "~/api";
import { canCommitAtomFamily, commitActionAtomFamily } from "~/common/state/atoms/workspaceAgentActions.ts";

import { CommitPromptDialog } from "./CommitPromptDialog.tsx";

// Fills the footer row; the row's own padding (shared with the scope picker
// above the tree) sets the inset.
const COMMIT_BUTTON_STYLE: CSSProperties = { width: "100%" };

type CommitButtonProps = {
  workspaceId: string;
  changesCount: number;
  /** Called after the commit message is sent. */
  onCommit?: () => void;
};

export const CommitButton = ({ workspaceId, changesCount, onCommit }: CommitButtonProps): ReactElement => {
  // Committing sends the prompt through the workspace-scoped action rather
  // than the mounted chat's `chatActionsAtom` closures — the Changes panel is
  // usually the active center tab, which unmounts the chat. The action builds
  // the workspace's message itself.
  const canCommit = useAtomValue(canCommitAtomFamily(workspaceId));
  const commit = useSetAtom(commitActionAtomFamily(workspaceId));
  const [isPromptDialogOpen, setIsPromptDialogOpen] = useState(false);

  const isDisabled = changesCount === 0 || !canCommit;

  const handleClick = (): void => {
    void commit();
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
