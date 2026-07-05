import { AlertDialog, Button, Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef } from "react";

import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import { ElementIds } from "../api";
import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE } from "./popoverFriendlyModal.ts";

type DeleteConfirmationDialogProps = {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  entityType: "workspace" | "agent" | "terminal";
  entityName: string;
  onConfirm: () => void;
};

const DESCRIPTION_BY_TYPE: Record<DeleteConfirmationDialogProps["entityType"], (name: string) => string> = {
  workspace: (name) => `This will permanently delete the workspace "${name}" and all of its agents.`,
  agent: (name) => `This will permanently delete the agent "${name}".`,
  terminal: (name) => `This will close the terminal "${name}" and end its session.`,
};

// Confirm-button verb per entity. Terminals are "closed" (they hold no durable
// history), everything else is "deleted". Keyed on entityType so the label can't
// drift from the title/description a caller renders.
const CONFIRM_LABEL_BY_TYPE: Record<DeleteConfirmationDialogProps["entityType"], string> = {
  workspace: "Delete",
  agent: "Delete",
  terminal: "Close",
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
  // Terminals are "closed", not "deleted" — they hold no durable history.
  const title = entityType === "terminal" ? "Close terminal?" : `Delete ${entityType}?`;
  const description = DESCRIPTION_BY_TYPE[entityType](entityName);
  const confirmLabel = CONFIRM_LABEL_BY_TYPE[entityType];

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
              {confirmLabel}
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
