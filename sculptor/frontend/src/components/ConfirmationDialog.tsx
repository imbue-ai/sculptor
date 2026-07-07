import { AlertDialog, Button, Flex } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";
import { useRef } from "react";

import { useThemeAccentColor, useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import { ElementIds } from "../api";
import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE } from "./popoverFriendlyModal.ts";

// Confirm-button emphasis. "danger" (destructive actions — delete, close) paints
// the button in the theme danger color; "neutral" (reversible-but-discarding
// actions, e.g. reset layout) uses the accent color so it doesn't read as
// permanent data loss.
export type ConfirmationTone = "danger" | "neutral";

type ConfirmationDialogProps = {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  tone: ConfirmationTone;
  onConfirm: () => void;
};

// A generic confirm/cancel dialog: the caller supplies the copy (title,
// description, confirm label) and tone, so a single component serves every
// confirmation. Per-flow copy is produced by the builders in
// `confirmationDialogContent.ts` rather than baked in here.
export const ConfirmationDialog = ({
  isOpen,
  onOpenChange,
  title,
  description,
  confirmLabel,
  tone,
  onConfirm,
}: ConfirmationDialogProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const accentColor = useThemeAccentColor();
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const confirmColor = tone === "danger" ? dangerColor : accentColor;

  // Radix' AlertDialog defaults focus to the first focusable element
  // (Cancel) for safety, which makes Enter dismiss the dialog instead of
  // confirming. Override `onOpenAutoFocus` to land focus on the confirm
  // button so Enter accepts. Esc / Cancel still close as expected.
  const handleOpenAutoFocus = (event: Event): void => {
    event.preventDefault();
    confirmButtonRef.current?.focus();
  };

  return (
    <AlertDialog.Root open={isOpen} onOpenChange={onOpenChange}>
      <AlertDialog.Content
        maxWidth="400px"
        data-testid={ElementIds.CONFIRMATION_DIALOG}
        {...{ [POPOVER_FRIENDLY_MODAL_ATTRIBUTE]: "true" }}
        onOpenAutoFocus={handleOpenAutoFocus}
      >
        <AlertDialog.Title>{title}</AlertDialog.Title>
        <AlertDialog.Description>{description}</AlertDialog.Description>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray" data-testid={ElementIds.CONFIRMATION_DIALOG_CANCEL}>
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button
              ref={confirmButtonRef}
              variant="solid"
              color={confirmColor}
              onClick={onConfirm}
              data-testid={ElementIds.CONFIRMATION_DIALOG_CONFIRM}
            >
              {confirmLabel}
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
