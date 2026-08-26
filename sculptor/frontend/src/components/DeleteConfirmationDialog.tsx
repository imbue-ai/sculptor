import { AlertDialog } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "../api";
import { ConfirmationDialog } from "./ConfirmationDialog.tsx";

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
  // Terminals are "closed", not "deleted" — they hold no durable history.
  const title = entityType === "terminal" ? "Close terminal?" : `Delete ${entityType}?`;
  const description = DESCRIPTION_BY_TYPE[entityType](entityName);
  const confirmLabel = CONFIRM_LABEL_BY_TYPE[entityType];

  return (
    <ConfirmationDialog
      open={isOpen}
      onOpenChange={onOpenChange}
      title={title}
      confirmLabel={confirmLabel}
      onConfirm={onConfirm}
      isDanger
      dialogTestId={ElementIds.DELETE_CONFIRMATION_DIALOG}
      cancelTestId={ElementIds.DELETE_CONFIRMATION_CANCEL}
      confirmTestId={ElementIds.DELETE_CONFIRMATION_CONFIRM}
    >
      <AlertDialog.Description>{description}</AlertDialog.Description>
    </ConfirmationDialog>
  );
};
