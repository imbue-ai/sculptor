// A <ConfirmationDialog> driven by a Jotai atom: a non-null atom value opens the
// dialog with that payload; confirming runs the payload's onConfirm and clears the
// atom, while dismissing (Cancel / Esc / outside click) just clears it. AppShell
// mounts one per app-level confirmation atom, mirroring AtomToast — so any surface
// can raise a one-off confirmation by setting the atom, with no bespoke owner.

import type { WritableAtom } from "jotai";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { memo, useCallback } from "react";

import type { ConfirmationDialogData } from "~/common/state/atoms/confirmationDialog.ts";

import { ConfirmationDialog } from "./ConfirmationDialog.tsx";

// Writable so the dialog can clear itself on confirm or dismiss. Only null is ever
// written back, which keeps atoms with narrower payloads assignable.
export type ConfirmationDialogAtom = WritableAtom<ConfirmationDialogData | null, [null], void>;

type AtomConfirmationDialogProps = {
  dialogAtom: ConfirmationDialogAtom;
};

const AtomConfirmationDialogComponent = ({ dialogAtom }: AtomConfirmationDialogProps): ReactElement => {
  const data = useAtomValue(dialogAtom);
  const setData = useSetAtom(dialogAtom);

  // Stable callback so the memoized dialog bails out instead of re-rendering on
  // every unrelated commit while it sits closed.
  const handleOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) setData(null);
    },
    [setData],
  );

  const handleConfirm = useCallback((): void => {
    data?.onConfirm();
    setData(null);
  }, [data, setData]);

  // While closed (data === null) the dialog is unmounted by Radix, so the empty
  // fallbacks below are never shown; they only satisfy the required string props.
  return (
    <ConfirmationDialog
      isOpen={data !== null}
      onOpenChange={handleOpenChange}
      title={data?.title ?? ""}
      description={data?.description ?? ""}
      confirmLabel={data?.confirmLabel ?? ""}
      tone={data?.tone ?? "danger"}
      onConfirm={handleConfirm}
    />
  );
};

// Memoized because instances sit always-mounted (and usually closed) in the shell;
// with a stable module-level atom prop, only a payload change re-renders one.
export const AtomConfirmationDialog = memo(AtomConfirmationDialogComponent);
