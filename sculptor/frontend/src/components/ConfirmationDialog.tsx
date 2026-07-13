import { AlertDialog, Button, Flex } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";
import { useRef } from "react";

import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE } from "./popoverFriendlyModal.ts";

type ConfirmationDialogProps = {
  // Controlled open state, mirroring Radix' AlertDialog.Root.
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Heading and body. `children` is an arbitrary slot — a description line, a
  // list of affected items, a reassurance note — so callers own their copy.
  title: ReactNode;
  children: ReactNode;
  // Confirm button contents and handler. `isDanger` tints it with the theme
  // danger color for destructive confirmations; otherwise it uses the accent.
  confirmLabel: ReactNode;
  onConfirm: () => void;
  onCancel?: () => void;
  isDanger?: boolean;
  maxWidth?: string;
  dialogTestId?: string;
  cancelTestId?: string;
  confirmTestId?: string;
};

// Shared chrome for AlertDialog-based confirmations: a popover-friendly modal
// whose confirm button takes initial focus, with a Cancel/Confirm footer.
// Callers compose the body and supply their own copy; this owns the frame so
// every confirmation looks and behaves the same.
export const ConfirmationDialog = ({
  open,
  onOpenChange,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  isDanger = false,
  maxWidth = "400px",
  dialogTestId,
  cancelTestId,
  confirmTestId,
}: ConfirmationDialogProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  // Radix' AlertDialog defaults focus to the first focusable element
  // (Cancel) for safety, which makes Enter dismiss the dialog instead of
  // confirming. Override `onOpenAutoFocus` to land focus on the confirm
  // button so Enter accepts. Esc / Cancel still close as expected.
  const handleOpenAutoFocus = (event: Event): void => {
    event.preventDefault();
    confirmButtonRef.current?.focus();
  };

  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Content
        maxWidth={maxWidth}
        data-testid={dialogTestId}
        {...{ [POPOVER_FRIENDLY_MODAL_ATTRIBUTE]: "true" }}
        onOpenAutoFocus={handleOpenAutoFocus}
      >
        <AlertDialog.Title>{title}</AlertDialog.Title>
        {children}
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray" onClick={onCancel} data-testid={cancelTestId}>
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button
              ref={confirmButtonRef}
              variant="solid"
              color={isDanger ? dangerColor : undefined}
              onClick={onConfirm}
              data-testid={confirmTestId}
            >
              {confirmLabel}
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
