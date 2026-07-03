// Count-only lifecycle warning shown before an action that would terminate
// running background processes — quitting Sculptor, or deleting the current
// agent / workspace. Reuses the DeleteConfirmationDialog AlertDialog pattern:
// gray-soft Cancel, danger-colored confirm, focus landed on confirm so Enter
// accepts.
//
// Presentational only. The count sentence ("N running background process(es)
// will be terminated.") is shown ONLY when runningCount > 0 — at zero the
// dialog is the plain action confirmation.
import { AlertDialog, Button, Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef } from "react";

import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE } from "./popoverFriendlyModal.ts";

type BackgroundProcessWarningAction = "quit" | "delete-agent" | "delete-workspace";

type BackgroundProcessWarningDialogProps = {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  action: BackgroundProcessWarningAction;
  runningCount: number;
  entityName?: string;
  onConfirm: () => void;
};

// Per-action title + confirm label. The body is assembled below so it can fold
// in the optional entity name and the conditional count sentence.
const ACTION_COPY = {
  quit: {
    title: "Quit Sculptor?",
    confirmLabel: "Quit",
    body: "Quitting Sculptor will close this session.",
  },
  "delete-agent": {
    title: "Delete agent?",
    confirmLabel: "Delete",
    body: "This will permanently delete this agent.",
  },
  "delete-workspace": {
    title: "Delete workspace?",
    confirmLabel: "Delete",
    body: "This will permanently delete this workspace and all of its agents.",
  },
} as const satisfies Record<BackgroundProcessWarningAction, { title: string; confirmLabel: string; body: string }>;

export const BackgroundProcessWarningDialog = ({
  isOpen,
  onOpenChange,
  action,
  runningCount,
  entityName,
  onConfirm,
}: BackgroundProcessWarningDialogProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  const copy = ACTION_COPY[action];
  const isDelete = action !== "quit";
  // When the caller knows the entity name, name it in the body for the delete
  // actions ("...delete the agent \"fix-auth-bug\"."); otherwise fall back to
  // the generic body.
  const body =
    isDelete && entityName !== undefined
      ? `This will permanently delete the ${action === "delete-workspace" ? "workspace" : "agent"} "${entityName}"${
          action === "delete-workspace" ? " and all of its agents" : ""
        }.`
      : copy.body;

  const hasRunningProcesses = runningCount > 0;
  const countSentence = `${runningCount} running background process${
    runningCount === 1 ? "" : "es"
  } will be terminated.`;

  // Radix' AlertDialog defaults focus to the first focusable element (Cancel),
  // which makes Enter dismiss instead of confirming. Land focus on the confirm
  // button so Enter accepts; Esc / Cancel still close.
  const handleOpenAutoFocus = (event: Event): void => {
    event.preventDefault();
    confirmButtonRef.current?.focus();
  };

  return (
    <AlertDialog.Root open={isOpen} onOpenChange={onOpenChange}>
      <AlertDialog.Content
        maxWidth="400px"
        {...{ [POPOVER_FRIENDLY_MODAL_ATTRIBUTE]: "true" }}
        onOpenAutoFocus={handleOpenAutoFocus}
      >
        <AlertDialog.Title>{copy.title}</AlertDialog.Title>
        <AlertDialog.Description>
          {body}
          {hasRunningProcesses ? ` ${countSentence}` : ""}
        </AlertDialog.Description>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray">
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button ref={confirmButtonRef} variant="solid" color={dangerColor} onClick={onConfirm}>
              {copy.confirmLabel}
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
