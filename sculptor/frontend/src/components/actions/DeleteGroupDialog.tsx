import { Button, Dialog, Flex, Spinner, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import styles from "./DeleteActionDialog.module.scss";

type DeleteGroupDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupName: string;
  actionNames: ReadonlyArray<string>;
  onConfirm: () => void;
  isDeleting?: boolean;
};

export const DeleteGroupDialog = ({
  open,
  onOpenChange,
  groupName,
  actionNames,
  onConfirm,
  isDeleting = false,
}: DeleteGroupDialogProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className={styles.dialogContent}>
        <Flex direction="column" gap="4">
          <Dialog.Title>Delete &apos;{groupName}&apos;</Dialog.Title>

          {actionNames.length > 0 ? (
            <Flex direction="column" gap="2">
              <Text size="2">
                This will permanently delete the group and{" "}
                {actionNames.length === 1 ? "its action" : `all ${actionNames.length} actions`}:
              </Text>
              <Flex direction="column" gap="1" pl="3">
                {actionNames.map((name) => (
                  <Text key={name} size="2" style={{ color: "var(--gray-11)" }}>
                    &bull; {name}
                  </Text>
                ))}
              </Flex>
            </Flex>
          ) : (
            <Text size="2">This group will be permanently deleted. This cannot be undone.</Text>
          )}

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
              data-testid={ElementIds.DELETE_GROUP_CONFIRM_BUTTON}
            >
              {isDeleting ? <Spinner /> : "Delete Group"}
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};
