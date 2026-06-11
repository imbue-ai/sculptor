import { useAtom, useSetAtom } from "jotai";
import { useCallback } from "react";

import { commandPaletteOpenAtom } from "../CommandPalette/atoms.ts";
import {
  type NewWorkspaceModalEntrySource,
  newWorkspaceModalEntrySourceAtom,
  newWorkspaceModalOpenAtom,
} from "./atoms.ts";

type UseNewWorkspaceModal = {
  isOpen: boolean;
  open: (source: NewWorkspaceModalEntrySource) => void;
  close: () => void;
  toggle: (source: NewWorkspaceModalEntrySource) => void;
  /**
   * Close the modal and re-open the command palette. Drives the "swap in
   * place" feel for the palette entry path (the back-arrow and Esc-once /
   * ArrowLeft-at-position-0 affordances) without rendering two overlapping
   * dimmed overlays.
   */
  returnToPalette: () => void;
};

/**
 * UI controls for the new-workspace modal. Opening also closes the
 * command palette so the two surfaces are mutually exclusive — when the
 * user reaches the modal via Cmd+K → "New workspace" the entry source
 * "palette" enables the back-arrow / Esc-pops-back behavior.
 */
export const useNewWorkspaceModal = (): UseNewWorkspaceModal => {
  const [isOpen, setIsOpen] = useAtom(newWorkspaceModalOpenAtom);
  const setEntrySource = useSetAtom(newWorkspaceModalEntrySourceAtom);
  const setCommandPaletteOpen = useSetAtom(commandPaletteOpenAtom);

  const open = useCallback(
    (source: NewWorkspaceModalEntrySource): void => {
      setEntrySource(source);
      // Always close the palette when the modal opens — only one of the
      // two surfaces is visible at a time. For the "palette" source,
      // the modal's back-arrow / Esc-once handlers re-open the palette,
      // creating the "swap in place" feel without rendering two
      // overlapping dimmed overlays.
      setCommandPaletteOpen(false);
      setIsOpen(true);
    },
    [setEntrySource, setCommandPaletteOpen, setIsOpen],
  );

  const close = useCallback((): void => {
    setIsOpen(false);
  }, [setIsOpen]);

  // Keep the state updater pure: branch on the current `isOpen` from render
  // scope and perform the entry-source / palette-close writes outside the
  // setter. `toggle` re-creates when `isOpen` flips, but callers register it
  // through `useEvent` so its identity churn doesn't re-bind the keybinding.
  const toggle = useCallback(
    (source: NewWorkspaceModalEntrySource): void => {
      if (isOpen) {
        setIsOpen(false);
        return;
      }
      setEntrySource(source);
      setCommandPaletteOpen(false);
      setIsOpen(true);
    },
    [isOpen, setIsOpen, setEntrySource, setCommandPaletteOpen],
  );

  const returnToPalette = useCallback((): void => {
    setIsOpen(false);
    setCommandPaletteOpen(true);
  }, [setIsOpen, setCommandPaletteOpen]);

  return { isOpen, open, close, toggle, returnToPalette };
};
