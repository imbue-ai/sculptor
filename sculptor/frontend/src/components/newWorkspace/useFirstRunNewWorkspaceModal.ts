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
 * Mounted by the home page only, so the dialog never pops over Settings (or
 * any other route) and re-offers itself on each return to Home while the list
 * is still empty. The user can dismiss it freely; the sidebar's New Workspace
 * button and the Cmd/Meta+T shortcut stay live as the explicit reopen paths.
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
      setNewWorkspaceModal({ open: true, initialPrompt: HOME_PROMPT_PREFILL });
    }
  }, [isWorkspaceListEmpty, setNewWorkspaceModal]);
};
