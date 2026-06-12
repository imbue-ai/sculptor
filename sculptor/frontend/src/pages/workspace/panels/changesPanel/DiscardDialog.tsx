import { AlertDialog, Button, Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

type DiscardDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filePath: string;
  onConfirm: () => void;
};

export const DiscardDialog = ({ open, onOpenChange, filePath, onConfirm }: DiscardDialogProps): ReactElement => {
  const fileName = filePath.split("/").pop() ?? filePath;

  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Content maxWidth="400px" data-testid={ElementIds.DISCARD_DIALOG}>
        <AlertDialog.Title>Discard changes</AlertDialog.Title>
        <AlertDialog.Description>
          <Text size="2">
            Discard changes to <Text weight="bold">{fileName}</Text>? This cannot be undone.
          </Text>
        </AlertDialog.Description>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray" data-testid={ElementIds.DISCARD_DIALOG_CANCEL}>
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button variant="solid" color="red" onClick={onConfirm} data-testid={ElementIds.DISCARD_DIALOG_CONFIRM}>
              Discard
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
