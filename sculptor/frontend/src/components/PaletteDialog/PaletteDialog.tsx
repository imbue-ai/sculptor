import * as Dialog from "@radix-ui/react-dialog";
import { VisuallyHidden } from "@radix-ui/themes";
import type { KeyboardEvent, ReactElement, ReactNode } from "react";
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import styles from "./PaletteDialog.module.scss";

type PaletteDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Accessible title (rendered visually-hidden); required by Radix Dialog. */
  title: string;
  children: ReactNode;
  /** Optional capture-phase keydown handler on the content node. */
  onKeyDownCapture?: (e: KeyboardEvent<HTMLDivElement>) => void;
  /** Optional Radix Escape interceptor — preventDefault() to swallow Esc. */
  onEscapeKeyDown?: (e: globalThis.KeyboardEvent) => void;
  /** Optional Radix open-autofocus interceptor — preventDefault() and
   *  focus your own element to override Radix's default first-focusable
   *  behavior. */
  onOpenAutoFocus?: (e: Event) => void;
  /** Adds a class to the overlay (e.g. to flag a "pending" cursor). */
  overlayClassName?: string;
  /** Adds a class to the content. Use to widen the modal beyond palette default. */
  contentClassName?: string;
  /** Test id forwarded to Dialog.Content. */
  contentTestId?: string;
};

/**
 * Shared dialog frame for palette-style overlays (CommandPalette,
 * NewWorkspaceModal). Owns the Radix Dialog root, the dimmed overlay, the
 * centered content panel with Raycast-style chrome, and the accessibility
 * title. Consumers compose their own header/body inside.
 *
 * No Dialog.Portal: portaled content mounts at <body>, OUTSIDE the
 * Radix `.radix-themes` wrapper, and `.dark` / `.light` token overrides
 * are scoped to that class. Rendering inline keeps the dialog inside the
 * Theme tree so dark-mode tokens apply correctly.
 */
export const PaletteDialog = ({
  open,
  onOpenChange,
  title,
  children,
  onKeyDownCapture,
  onEscapeKeyDown,
  onOpenAutoFocus,
  overlayClassName,
  contentClassName,
  contentTestId,
}: PaletteDialogProps): ReactElement => {
  const overlayClass = overlayClassName ? `${styles.overlay} ${overlayClassName}` : styles.overlay;
  const contentClass = contentClassName ? `${styles.content} ${contentClassName}` : styles.content;

  // Close palette-style overlays whenever the pathname changes. Both
  // consumers (CommandPalette, NewWorkspaceModal) survive intra-layout
  // route changes — the overlay would otherwise stay on top of the
  // destination page and intercept clicks. handleSubmit / explicit
  // close paths cover the create-then-navigate flow; this catches
  // URL-bar nav, browser back/forward, and test cleanup re-routing.
  // Some entry sources (e.g. NewWorkspaceModal opened via Cmd+K) close
  // by re-opening a sibling palette overlay, so the URL listener has
  // to live here, not in the consumer — otherwise the sibling stays
  // open across the navigation.
  const { pathname } = useLocation();
  const lastPathnameRef = useRef(pathname);
  useEffect(() => {
    if (pathname === lastPathnameRef.current) return;
    lastPathnameRef.current = pathname;
    if (open) onOpenChange(false);
  }, [pathname, open, onOpenChange]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Overlay className={overlayClass} />
      <Dialog.Content
        className={contentClass}
        aria-describedby={undefined}
        data-testid={contentTestId}
        onKeyDownCapture={onKeyDownCapture}
        onEscapeKeyDown={onEscapeKeyDown}
        onOpenAutoFocus={onOpenAutoFocus}
      >
        <VisuallyHidden>
          <Dialog.Title>{title}</Dialog.Title>
        </VisuallyHidden>
        {children}
      </Dialog.Content>
    </Dialog.Root>
  );
};
