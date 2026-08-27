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
  /** Identifies the dialog content for tests. */
  testId?: string;
  children: ReactNode;
};

/**
 * The Raycast-style modal shell: an opaque ~720px panel centered ~14% from the
 * top with `--shadow-xl`, over a dimmed overlay. The content is rendered inline
 * (no `Dialog.Portal`) so it inherits the Radix `.radix-themes` token scope
 * where the `.dark` / `.light` variable overrides live — the same pattern
 * `KeyboardShortcutsDialog` / `CommandPalette` use.
 */
export const PaletteDialog = ({ open, onOpenChange, title, testId, children }: PaletteDialogProps): ReactElement => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <VisuallyHidden>
        <Dialog.Title>{title}</Dialog.Title>
      </VisuallyHidden>
      <Dialog.Overlay className={styles.overlay} data-testid={ElementIds.PALETTE_DIALOG_OVERLAY} />
      {/* The visually-hidden title supplies the accessible name; opt out of
          Radix's Description requirement rather than adding an empty one. */}
      <Dialog.Content className={styles.content} data-testid={testId} aria-describedby={undefined}>
        {children}
      </Dialog.Content>
    </Dialog.Root>
  );
};
