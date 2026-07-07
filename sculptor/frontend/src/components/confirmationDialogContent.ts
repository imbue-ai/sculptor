import type { ReactNode } from "react";

import type { ConfirmationTone } from "./ConfirmationDialog.tsx";

// The variant part of a confirmation dialog: everything the generic
// `ConfirmationDialog` renders except the open state and the confirm handler.
// A builder returns one of these so callers keep a single call site for a flow's
// copy, and so the copy can't drift from the tone it should carry.
export type ConfirmationDialogContent = {
  title: string;
  description: ReactNode;
  confirmLabel: string;
  tone: ConfirmationTone;
};

// Entities whose removal is confirmed. Terminals are "closed" (they hold no
// durable history); workspaces and agents are "deleted".
export type DeletableEntityType = "workspace" | "agent" | "terminal";

const DELETE_DESCRIPTION_BY_TYPE: Record<DeletableEntityType, (name: string) => string> = {
  workspace: (name) => `This will permanently delete the workspace "${name}" and all of its agents.`,
  agent: (name) => `This will permanently delete the agent "${name}".`,
  terminal: (name) => `This will close the terminal "${name}" and end its session.`,
};

const DELETE_CONFIRM_LABEL_BY_TYPE: Record<DeletableEntityType, string> = {
  workspace: "Delete",
  agent: "Delete",
  terminal: "Close",
};

// Copy for the delete/close confirmation of a named entity. Keyed on
// entityType so the title, description, and confirm verb stay in lockstep.
export const buildDeleteConfirmationContent = ({
  entityType,
  entityName,
}: {
  entityType: DeletableEntityType;
  entityName: string;
}): ConfirmationDialogContent => ({
  title: entityType === "terminal" ? "Close terminal?" : `Delete ${entityType}?`,
  description: DELETE_DESCRIPTION_BY_TYPE[entityType](entityName),
  confirmLabel: DELETE_CONFIRM_LABEL_BY_TYPE[entityType],
  tone: "danger",
});

// Copy for resetting a workspace's panel layout back to the default arrangement.
// Reversible-but-discarding (the user only loses their custom arrangement, no
// data), so it carries the neutral tone rather than danger.
export const buildResetLayoutConfirmationContent = (): ConfirmationDialogContent => ({
  title: "Reset to default layout?",
  description: "This discards your current panel arrangement for this workspace and restores the default layout.",
  confirmLabel: "Reset layout",
  tone: "neutral",
});
