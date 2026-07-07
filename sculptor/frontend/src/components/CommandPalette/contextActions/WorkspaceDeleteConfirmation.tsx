// Headless owner of the workspace delete-confirmation dialog driven by
// `workspaceDeleteTargetAtom` — the target that the palette's workspace Delete
// action and the `delete_workspace` keybinding both set. The sidebar's trash icon
// renders its own local dialog; this one serves the surfaces that have no natural
// host component. Mounted once alongside the palette (see CommandRegistrations) so
// it is available on every route.

import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { ConfirmationDialog } from "~/components/ConfirmationDialog.tsx";
import { buildDeleteConfirmationContent } from "~/components/confirmationDialogContent.ts";
import { useWorkspaceTabActions } from "~/components/useWorkspaceTabActions.ts";

import { workspaceDeleteTargetAtom } from "./atoms.ts";

export const WorkspaceDeleteConfirmation = (): ReactElement => {
  const [target, setTarget] = useAtom(workspaceDeleteTargetAtom);
  const { workspaceId: activeWorkspaceId } = useImbueLocation();
  const { navigateToNextTab } = useWorkspaceTabActions();
  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    // Navigate away only when the deleted workspace is the one being viewed —
    // the same rule as the sidebar's delete flow.
    onNavigateAfterDelete: (workspaceId): void => {
      if (workspaceId === activeWorkspaceId) {
        navigateToNextTab(workspaceId);
      }
    },
  });

  const handleConfirm = useCallback((): void => {
    if (target === null) {
      return;
    }
    executeDelete(target.id, target.name);
    setTarget(null);
  }, [target, executeDelete, setTarget]);

  const handleOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) {
        setTarget(null);
      }
    },
    [setTarget],
  );

  return (
    <ConfirmationDialog
      isOpen={target !== null}
      onOpenChange={handleOpenChange}
      {...buildDeleteConfirmationContent({ entityType: "workspace", entityName: target?.name ?? "" })}
      onConfirm={handleConfirm}
    />
  );
};
