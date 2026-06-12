import { Box, Button, Dialog, Flex, Spinner, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import { ElementIds } from "../../../api";
import styles from "./RemoveRepoDialog.module.scss";

type RemoveRepoDialogProps = {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  projectName: string;
  agentCount: number;
  isDeleting: boolean;
};

export const RemoveRepoDialog = ({
  isOpen,
  onClose,
  onConfirm,
  projectName,
  agentCount,
  isDeleting,
}: RemoveRepoDialogProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  return (
    <Dialog.Root open={isOpen} onOpenChange={onClose}>
      <Dialog.Content className={styles.dialogContent}>
        <Dialog.Title>Remove Repository</Dialog.Title>

        <Flex direction="column" gap="4">
          <Text size="2">
            Are you sure you want to remove <strong>{projectName}</strong> and all of the associated agents from
            Sculptor? This action cannot be undone.
          </Text>

          <Box className={styles.agentCountsBox}>
            <Text size="2">
              {agentCount} agent{agentCount !== 1 ? "s" : ""}
            </Text>
          </Box>

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
              style={{ minWidth: "185px" }}
              data-testid={ElementIds.SETTINGS_REMOVE_REPO_CONFIRM}
            >
              {isDeleting ? <Spinner /> : "Remove repo & agents"}
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};
