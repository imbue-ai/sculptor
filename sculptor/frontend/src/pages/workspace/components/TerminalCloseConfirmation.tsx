import { useAtom, useSetAtom } from "jotai";
import { type ReactElement, useCallback } from "react";

import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { useRemovePanelFromSection } from "~/components/panels/sectionHooks.ts";
import { removeTerminalAtom, terminalCloseTargetAtom } from "~/pages/workspace/panels/terminals.ts";

/**
 * Headless owner of the terminal close-confirmation dialog, driven by the shared
 * `terminalCloseTargetAtom` (set from a terminal tab's close button / "Close
 * terminal" menu item). Confirming kills the terminal session and unplaces its
 * panel, collapsing the section if it was the last tab. Mirrors the agent delete
 * flow in `AgentWorkspaceCommands`. Rendered once per workspace.
 */
export const TerminalCloseConfirmation = (): ReactElement => {
  const [target, setTarget] = useAtom(terminalCloseTargetAtom);
  const removeTerminal = useSetAtom(removeTerminalAtom);
  const removePanel = useRemovePanelFromSection();

  const handleConfirm = useCallback((): void => {
    if (!target) return;
    removeTerminal(target.id);
    removePanel(target.id);
    setTarget(null);
  }, [target, removeTerminal, removePanel, setTarget]);

  return (
    <DeleteConfirmationDialog
      isOpen={target !== null}
      onOpenChange={(open) => {
        if (!open) setTarget(null);
      }}
      entityType="terminal"
      entityName={target?.name ?? ""}
      confirmLabel="Close"
      onConfirm={handleConfirm}
    />
  );
};
