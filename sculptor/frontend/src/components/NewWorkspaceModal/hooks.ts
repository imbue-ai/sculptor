import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useCallback } from "react";

import { useImbueLocation } from "../../common/NavigateUtils.ts";
import { isWorkspaceListEmptyAtom } from "../../common/state/atoms/workspaces.ts";
import { commandPaletteOpenAtom } from "../CommandPalette/atoms.ts";
import {
  homePromptFocusRequestAtom,
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
  const isWorkspaceListEmpty = useAtomValue(isWorkspaceListEmptyAtom);
  const { isHomeRoute } = useImbueLocation();
  const requestHomePromptFocus = useSetAtom(homePromptFocusRequestAtom);

  const open = useCallback(
    (source: NewWorkspaceModalEntrySource): void => {
      // Always close the palette first — only one create surface is visible
      // at a time. For the "palette" source, the modal's back-arrow / Esc-once
      // handlers re-open the palette, creating the "swap in place" feel
      // without rendering two overlapping dimmed overlays.
      setCommandPaletteOpen(false);
      // On an empty Home the inline form *is* the create surface (and the
      // topbar "+" is hidden there), so there's no modal to open — focus its
      // prompt instead. Anywhere else (off Home, or once workspaces exist) the
      // modal opens normally. `isWorkspaceListEmptyAtom` treats the not-yet-
      // loaded window as empty, matching the inline form (and the hidden "+").
      if (isHomeRoute && isWorkspaceListEmpty) {
        requestHomePromptFocus((nonce) => nonce + 1);
        return;
      }
      setEntrySource(source);
      setIsOpen(true);
    },
    [isHomeRoute, isWorkspaceListEmpty, setEntrySource, setCommandPaletteOpen, setIsOpen, requestHomePromptFocus],
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
