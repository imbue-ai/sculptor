import { useAtom, useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { ElementIds } from "../../api";
import { PaletteDialog } from "../PaletteDialog";
import { Toast } from "../Toast.tsx";
import {
  newWorkspaceModalEntrySourceAtom,
  newWorkspaceModalOpenAtom,
  newWorkspaceSubmittingAtom,
  newWorkspaceToastAtom,
} from "./atoms.ts";
import { useNewWorkspaceModal } from "./hooks.ts";
import { NewWorkspaceForm } from "./NewWorkspaceForm.tsx";
import styles from "./NewWorkspaceModal.module.scss";

/**
 * Always-mounted shell for the new-workspace modal. Owns the shared
 * `PaletteDialog` frame, the dialog-level close / Esc / autofocus glue, and the
 * modal's toast — but no form state and no fetching effects. The actual form
 * (`NewWorkspaceForm`) is passed as dialog children, which Radix mounts only
 * while the dialog is open, so the form's effects never run while closed.
 *
 * The toast is rendered here (driven by an atom the form writes) so a toast set
 * just before the form unmounts (close + navigate to the new agent) still
 * shows.
 */
export const NewWorkspaceModal = (): ReactElement => {
  const [isOpen, setIsOpen] = useAtom(newWorkspaceModalOpenAtom);
  const entrySource = useAtomValue(newWorkspaceModalEntrySourceAtom);
  const isSubmitting = useAtomValue(newWorkspaceSubmittingAtom);
  const [toast, setToast] = useAtom(newWorkspaceToastAtom);
  const { returnToPalette } = useNewWorkspaceModal();

  const handleOpenChange = useCallback(
    (next: boolean): void => {
      if (next) {
        setIsOpen(true);
        return;
      }
      // While a create is in flight, refuse to close so a stray Esc / overlay
      // click can't cancel the request mid-flight.
      if (isSubmitting) return;
      setIsOpen(false);
    },
    [setIsOpen, isSubmitting],
  );

  // Only the "entered via Cmd+K" path pops back to the command list on Esc;
  // every other entry source treats the modal as a destination, so the default
  // Radix Esc-closes behavior applies.
  const handleEscapeKeyDown = useCallback(
    (e: globalThis.KeyboardEvent): void => {
      if (entrySource === "palette") {
        e.preventDefault();
        returnToPalette();
      }
    },
    [entrySource, returnToPalette],
  );

  // Suppress Radix's default first-focusable autofocus so it doesn't land on
  // the close button / repo selector; the form focuses its title input on
  // mount instead.
  const handleOpenAutoFocus = useCallback((e: Event): void => {
    e.preventDefault();
  }, []);

  return (
    <>
      <PaletteDialog
        open={isOpen}
        onOpenChange={handleOpenChange}
        title="New workspace"
        contentClassName={styles.content}
        contentTestId={ElementIds.NEW_WORKSPACE_MODAL}
        onEscapeKeyDown={handleEscapeKeyDown}
        onOpenAutoFocus={handleOpenAutoFocus}
      >
        <NewWorkspaceForm />
      </PaletteDialog>
      <Toast
        open={!!toast}
        onOpenChange={(open) => !open && setToast(null)}
        description={toast?.description}
        duration={5000}
        title={toast?.title}
        type={toast?.type}
      />
    </>
  );
};
