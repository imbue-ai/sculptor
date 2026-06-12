import { AlertDialog, Button, Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef } from "react";

import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import { ElementIds } from "../api";
import styles from "./DeleteConfirmationDialog.module.scss";
import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE } from "./popoverFriendlyModal.ts";

type DeleteConfirmationDialogProps = {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  entityType: "workspace" | "agent";
  entityName: string;
  onConfirm: () => void;
};

export const DeleteConfirmationDialog = ({
  isOpen,
  onOpenChange,
  entityType,
  entityName,
  onConfirm,
}: DeleteConfirmationDialogProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const title = `Delete ${entityType}?`;
  const description =
    entityType === "workspace"
      ? `This will permanently delete the workspace "${entityName}" and all of its agents.`
      : `This will permanently delete the agent "${entityName}".`;

  // Radix' AlertDialog defaults focus to the first focusable element
  // (Cancel) for safety, which makes Enter dismiss the dialog instead of
  // confirming. Override `onOpenAutoFocus` to land focus on the Delete
  // button so Enter accepts. Esc / Cancel still close as expected.
  const handleOpenAutoFocus = (event: Event): void => {
    event.preventDefault();
    confirmButtonRef.current?.focus();
  };

  return (
    <AlertDialog.Root open={isOpen} onOpenChange={onOpenChange}>
      <AlertDialog.Content
        maxWidth="400px"
        className={styles.dialogContent}
        data-testid={ElementIds.DELETE_CONFIRMATION_DIALOG}
        {...{ [POPOVER_FRIENDLY_MODAL_ATTRIBUTE]: "true" }}
        onOpenAutoFocus={handleOpenAutoFocus}
      >
        <AlertDialog.Title>{title}</AlertDialog.Title>
        <AlertDialog.Description>{description}</AlertDialog.Description>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray" data-testid={ElementIds.DELETE_CONFIRMATION_CANCEL}>
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button
              ref={confirmButtonRef}
              variant="solid"
              color={dangerColor}
              onClick={onConfirm}
              data-testid={ElementIds.DELETE_CONFIRMATION_CONFIRM}
            >
              Delete
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
