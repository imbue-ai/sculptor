import { useAtomValue, useSetAtom } from "jotai";
import { useEffect } from "react";

import { HOME_PROMPT_PREFILL } from "~/components/newWorkspace/homePromptPrefill.ts";
import { isWorkspaceListEmptyAtom, newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";

/**
 * First-run create affordance: while the workspace list is empty, landing on
 * the home page auto-opens the new-workspace dialog with the `/sculptor:help`
 * onboarding prompt prefilled — creating a workspace IS the home experience
 * when there is nothing to show yet.
 *
 * The auto-open is marked `firstRun`, which renders the dialog NON-modally:
 * it is an offer, not a gate, so the sidebar and every other affordance stay
 * clickable and an open request the user never made can't steal their next
 * click. The user can dismiss it freely; the sidebar's New Workspace button
 * and the Cmd/Meta+T shortcut stay live as the explicit (modal) reopen paths.
 *
 * Mounted by the home page only, so the dialog never pops over Settings (or
 * any other route) and re-offers itself on each return to Home while the list
 * is still empty. Leaving Home retires a still-`firstRun` open with it —
 * the dialog is Home's empty-state content, not a global popup — while an
 * explicitly opened dialog is left alone.
 *
 * `isWorkspaceListEmptyAtom` is false while the list is still loading, so the
 * dialog only opens once the first snapshot confirms there are no workspaces —
 * a boot with existing workspaces never flashes it.
 */
export const useFirstRunNewWorkspaceModal = (): void => {
  const isWorkspaceListEmpty = useAtomValue(isWorkspaceListEmptyAtom);
  const setNewWorkspaceModal = useSetAtom(newWorkspaceModalAtom);

  useEffect(() => {
    if (isWorkspaceListEmpty) {
      setNewWorkspaceModal({ open: true, initialPrompt: HOME_PROMPT_PREFILL, firstRun: true });
    }
  }, [isWorkspaceListEmpty, setNewWorkspaceModal]);

  // Unmount-only cleanup (not on the empty-flag flipping false): the first
  // workspace arriving while the user is mid-form must not close the dialog
  // under them (e.g. a keep-open multi-create, or a workspace created by the
  // CLI). The functional update re-checks `firstRun` so an explicit open that
  // replaced the auto-open survives navigation the way it always has.
  useEffect(() => {
    return (): void => {
      setNewWorkspaceModal((prev) => (prev.firstRun ? { open: false } : prev));
    };
  }, [setNewWorkspaceModal]);
};
