import * as Dialog from "@radix-ui/react-dialog";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import type { ReactElement, ReactNode } from "react";

import { ElementIds } from "~/api";

import styles from "./PaletteDialog.module.scss";

type PaletteDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Accessible title; rendered visually hidden (the form supplies its own heading). */
  title: string;
  /**
   * Modal by default: dimmed overlay, focus trap, background inert. Pass
   * `false` for opens the user didn't ask for (e.g. the home page's first-run
   * auto-open): the panel floats over the page without an overlay, so nothing
   * underneath is blocked and a click aimed at the page beneath is never
   * stolen by a dialog that appeared asynchronously.
   */
  modal?: boolean;
  /** Identifies the dialog content for tests. */
  testId?: string;
  children: ReactNode;
};

/**
 * The Raycast-style dialog shell: an opaque ~720px panel centered ~14% from the
 * top with `--shadow-xl`, over a dimmed overlay in modal mode. The content is
 * rendered inline (no `Dialog.Portal`) so it inherits the Radix `.radix-themes`
 * token scope where the `.dark` / `.light` variable overrides live — the same
 * pattern `KeyboardShortcutsDialog` / `CommandPalette` use.
 */
export const PaletteDialog = ({
  open,
  onOpenChange,
  title,
  modal = true,
  testId,
  children,
}: PaletteDialogProps): ReactElement => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={modal}>
      <VisuallyHidden>
        <Dialog.Title>{title}</Dialog.Title>
      </VisuallyHidden>
      {/* Gated explicitly rather than relying on Radix to skip it in non-modal
          mode, so "no overlay, nothing blocked" is guaranteed by this file. */}
      {modal && <Dialog.Overlay className={styles.overlay} data-testid={ElementIds.PALETTE_DIALOG_OVERLAY} />}
      {/* The visually-hidden title supplies the accessible name; opt out of
          Radix's Description requirement rather than adding an empty one. */}
      <Dialog.Content className={styles.content} data-testid={testId} aria-describedby={undefined}>
        {children}
      </Dialog.Content>
    </Dialog.Root>
  );
};
