import { Button, Dialog, Flex, Spinner } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import styles from "./DeleteActionDialog.module.scss";

type DeleteActionDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actionName: string;
  onConfirm: () => void;
  isDeleting?: boolean;
};

export const DeleteActionDialog = ({
  open,
  onOpenChange,
  actionName,
  onConfirm,
  isDeleting = false,
}: DeleteActionDialogProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className={styles.dialogContent} data-testid={ElementIds.DELETE_ACTION_DIALOG}>
        <Flex direction="column" gap="4">
          <Dialog.Title>Delete &apos;{actionName}&apos;</Dialog.Title>

          <Dialog.Description size="2">
            This action will be permanently deleted. This cannot be undone.
          </Dialog.Description>

          <Flex gap="3" className={styles.actions} justify="end">
            <Dialog.Close>
              <Button variant="soft" color="gray" disabled={isDeleting}>
                Cancel
              </Button>
            </Dialog.Close>
            <Button
              variant="solid"
              color={dangerColor}
              onClick={onConfirm}
              disabled={isDeleting}
              style={{ minWidth: "120px" }}
              data-testid={ElementIds.DELETE_ACTION_CONFIRM_BUTTON}
            >
              {isDeleting ? <Spinner /> : "Delete Action"}
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};
