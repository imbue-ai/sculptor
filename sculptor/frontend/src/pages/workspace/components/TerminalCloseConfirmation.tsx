// Headless owner of the terminal close-confirmation dialog, driven by the
// shared terminalCloseTargetAtom (set from a terminal tab's close button via the
// panel's onRequestClose, wired in useWorkspaceDynamicPanels). Confirming kills the
// backend shell (closeWorkspaceTerminal), drops the tab from the persisted
// terminal-tab state, and unplaces the panel from the layout (closePanelAtom). Closing
// the last terminal leaves the bottom section empty (no auto-recreate), consistent with
// the agent flow. Mirrors the agent delete-confirmation wiring; rendered once by the
// workspace shell.

import { useAtom, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { closeWorkspaceTerminal } from "~/api";
import { terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { terminalCloseTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { closePanelAtom } from "~/components/sections/sectionActions.ts";

export const TerminalCloseConfirmation = (): ReactElement => {
  const [target, setTarget] = useAtom(terminalCloseTargetAtom);
  const setTerminalTabs = useSetAtom(terminalTabStateAtom);
  const closePanel = useSetAtom(closePanelAtom);

  const handleConfirm = useCallback((): void => {
    if (target === null) {
      return;
    }

    // Fire-and-forget: ask the backend to stop the pty + shell. A 404
    // (terminal never started, or already closed) is harmless; errors surface via
    // the API client's default handler.
    void closeWorkspaceTerminal({
      path: { workspace_id: target.workspaceId, index: target.index },
      throwOnError: false,
    });

    // Drop the closed terminal from the persisted tab state for this workspace.
    setTerminalTabs((prev) => {
      const workspaceTabs = prev[target.workspaceId];
      if (workspaceTabs === undefined) {
        return prev;
      }
      return { ...prev, [target.workspaceId]: workspaceTabs.filter((tab) => tab.id !== target.tabId) };
    });

    // Unplace the panel from the layout. The last terminal leaving the bottom
    // section empty is intentional (no auto-recreate).
    closePanel({ panelId: target.panelId });
    setTarget(null);
  }, [target, setTerminalTabs, closePanel, setTarget]);

  return (
    <DeleteConfirmationDialog
      isOpen={target !== null}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          setTarget(null);
        }
      }}
      entityType="terminal"
      entityName={target?.name ?? ""}
      onConfirm={handleConfirm}
    />
  );
};
