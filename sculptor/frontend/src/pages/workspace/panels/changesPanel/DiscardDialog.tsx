import { AlertDialog, Button, Callout, Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import type { WorkspaceVcs } from "~/common/utils/workspaceVcs.ts";

// jj restores the file from the working copy's parents, and the content it
// replaces stays in the operation log, where `jj op log` finds it.
const CONSEQUENCE_BY_VCS: Readonly<Record<WorkspaceVcs, string>> = {
  git: "This cannot be undone.",
  jj: "The discarded content stays recoverable from the jj operation log.",
};

type DiscardDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filePath: string;
  vcs: WorkspaceVcs;
  isDiscarding: boolean;
  /** Why the last discard failed; the dialog stays open so the user can retry or cancel. */
  errorMessage: string | null;
  /** Start the discard. The dialog stays open; the caller closes it once the discard lands. */
  onConfirm: () => void;
};

export const DiscardDialog = ({
  open,
  onOpenChange,
  filePath,
  vcs,
  isDiscarding,
  errorMessage,
  onConfirm,
}: DiscardDialogProps): ReactElement => {
  const fileName = filePath.split("/").pop() ?? filePath;

  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Content maxWidth="400px" data-testid={ElementIds.DISCARD_DIALOG}>
        <AlertDialog.Title>Discard changes</AlertDialog.Title>
        <AlertDialog.Description>
          <Text size="2">
            Discard changes to <Text weight="bold">{fileName}</Text>? {CONSEQUENCE_BY_VCS[vcs]}
          </Text>
        </AlertDialog.Description>
        {errorMessage !== null && (
          <Callout.Root color="red" size="1" mt="3" data-testid={ElementIds.DISCARD_DIALOG_ERROR}>
            <Callout.Text>Could not discard the changes: {errorMessage}</Callout.Text>
          </Callout.Root>
        )}
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray" data-testid={ElementIds.DISCARD_DIALOG_CANCEL}>
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <Button
            variant="solid"
            color="red"
            onClick={onConfirm}
            loading={isDiscarding}
            disabled={isDiscarding}
            data-testid={ElementIds.DISCARD_DIALOG_CONFIRM}
          >
            Discard
          </Button>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
