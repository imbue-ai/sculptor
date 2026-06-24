import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { ElementIds } from "~/api";
import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { NewWorkspaceForm } from "~/components/newWorkspace/NewWorkspaceForm.tsx";
import { PaletteDialog } from "~/components/PaletteDialog/PaletteDialog.tsx";

/**
 * Global host for the new-workspace dialog. Opened/closed via
 * `newWorkspaceModalAtom` (the entry points that set it are wired in a later
 * task). Renders the PaletteDialog shell around the WSC-05 form, remounting the
 * form on each open (keyed on the preset repo) so its local field state starts
 * fresh from the MRU seed every time.
 */
export const NewWorkspaceModal = (): ReactElement | undefined => {
  // State and hooks
  const [modalState, setModalState] = useAtom(newWorkspaceModalAtom);

  // Functions and callbacks
  const handleOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) {
        setModalState({ open: false });
      }
    },
    [setModalState],
  );

  const handleCreated = useCallback((): void => {
    setModalState({ open: false });
  }, [setModalState]);

  // JSX and rendering logic
  if (!modalState.open) {
    return undefined;
  }

  return (
    <PaletteDialog
      open={modalState.open}
      onOpenChange={handleOpenChange}
      title="New workspace"
      testId={ElementIds.NEW_WORKSPACE_DIALOG}
    >
      <NewWorkspaceForm
        key={modalState.presetProjectId ?? "default"}
        presetProjectId={modalState.presetProjectId}
        onCreated={handleCreated}
      />
    </PaletteDialog>
  );
};
