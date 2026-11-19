import { AlertDialog } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { workspaceBranchDeletionPolicyAtom } from "~/common/state/atoms/userConfig.ts";
import { workspaceVcsAtomFamily } from "~/common/state/atoms/workspaceIdentity.ts";

import type { UserConfig } from "../api";
import { ElementIds } from "../api";
import { ConfirmationDialog } from "./ConfirmationDialog.tsx";

type EntityType = "workspace" | "agent" | "terminal";

type DeleteConfirmationDialogProps = {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  entityName: string;
  onConfirm: () => void;
} & (
  | {
      entityType: "workspace";
      /** The workspace to delete; undefined while no deletion is pending. */
      workspaceId: string | undefined;
    }
  | { entityType: "agent" | "terminal" }
);

const DESCRIPTION_BY_TYPE: Record<EntityType, (name: string) => string> = {
  workspace: (name) => `This will permanently delete the workspace "${name}" and all of its agents.`,
  agent: (name) => `This will permanently delete the agent "${name}".`,
  terminal: (name) => `This will close the terminal "${name}" and end its session.`,
};

// Confirm-button verb per entity. Terminals are "closed" (they hold no durable
// history), everything else is "deleted". Keyed on entityType so the label can't
// drift from the title/description a caller renders.
const CONFIRM_LABEL_BY_TYPE: Record<EntityType, string> = {
  workspace: "Delete",
  agent: "Delete",
  terminal: "Close",
};

// What the backend's deletion policy does with a deleted jj workspace's own
// bookmarks. It forgets them, which removes them locally and never from the remote.
const JJ_BOOKMARK_FATE_BY_POLICY: Record<NonNullable<UserConfig["workspaceBranchDeletionPolicy"]>, string> = {
  never: "Its jj bookmarks are kept.",
  delete_if_safe:
    "Its jj bookmarks are removed locally if they are merged into the target or already on the remote, and kept otherwise.",
  always: "Its jj bookmarks are removed locally, even if they are not merged or pushed.",
};

const JjBookmarkFate = ({ workspaceId }: { workspaceId: string }): ReactElement | null => {
  const vcs = useAtomValue(workspaceVcsAtomFamily(workspaceId));
  const policy = useAtomValue(workspaceBranchDeletionPolicyAtom);
  return vcs === "jj" ? <> {JJ_BOOKMARK_FATE_BY_POLICY[policy]}</> : null;
};

export const DeleteConfirmationDialog = (props: DeleteConfirmationDialogProps): ReactElement => {
  const { isOpen, onOpenChange, entityType, entityName, onConfirm } = props;
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
      <AlertDialog.Description>
        {description}
        {props.entityType === "workspace" && props.workspaceId !== undefined ? (
          <JjBookmarkFate workspaceId={props.workspaceId} />
        ) : null}
      </AlertDialog.Description>
    </ConfirmationDialog>
  );
};
