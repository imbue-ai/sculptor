import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect } from "react";

import { ElementIds } from "~/api";
import { newWorkspaceDialogAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { NewWorkspaceForm } from "~/components/newWorkspace/NewWorkspaceForm.tsx";
import { PaletteDialog } from "~/components/newWorkspace/PaletteDialog.tsx";

/**
 * Global host for the new-workspace dialog. Opened/closed via
 * `newWorkspaceDialogAtom`, set by the creation entry points — the Cmd+K command,
 * the Cmd/Meta+T shortcut, and the sidebar's New Workspace button (the per-repo
 * "+" direct-creates and only falls back to opening this). Mounted in AppShell, the
 * layout hosting every page route, so it is reachable everywhere except the
 * empty first-run page (which replaces AppShell and renders the form inline
 * instead). Renders the PaletteDialog shell around the
 * form, remounting the form on each open (keyed on the preset repo) so
 * its local field state starts fresh from the MRU seed every time.
 */
export const NewWorkspaceDialog = (): ReactElement | undefined => {
  // State and hooks
  const [modalState, setModalState] = useAtom(newWorkspaceDialogAtom);

  // An open request must not outlive this host. AppShell unmounts when the
  // workspace list becomes (or turns out to be) empty and the first-run page
  // takes over; `newWorkspaceDialogAtom` lives in the store, so without this
  // cleanup a request set just before that swap would survive it invisibly and
  // pop the dialog — overlay and all — over the first workspace created from
  // the inline form. Close it on unmount so a stale request dies with its host.
  useEffect(() => {
    return (): void => {
      setModalState({ open: false });
    };
  }, [setModalState]);

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
