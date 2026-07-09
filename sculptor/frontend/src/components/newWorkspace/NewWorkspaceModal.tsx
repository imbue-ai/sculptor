import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { ElementIds } from "~/api";
import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { NewWorkspaceForm } from "~/components/newWorkspace/NewWorkspaceForm.tsx";
import { PaletteDialog } from "~/components/PaletteDialog/PaletteDialog.tsx";

/**
 * Global host for the new-workspace dialog. Opened/closed via
 * `newWorkspaceModalAtom`, set by the creation entry points — the Cmd+K command,
 * the Cmd/Meta+T shortcut, the sidebar's New Workspace button, and the home
 * page's first-run auto-open (with the onboarding prompt prefilled). A repo
 * group's "+" direct-creates instead, opening this dialog (with that repo
 * preset) only as its fallback when the create can't proceed. Mounted in
 * AppShell, the layout hosting every
 * page route, so it is reachable everywhere. Renders the PaletteDialog shell
 * around the form, remounting the form on each open (keyed on the preset repo)
 * so its local field state starts fresh from the MRU seed every time.
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
        initialPrompt={modalState.initialPrompt}
        onCreated={handleCreated}
      />
    </PaletteDialog>
  );
};
