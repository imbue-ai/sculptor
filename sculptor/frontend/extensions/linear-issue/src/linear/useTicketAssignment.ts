import { useExtensionSetting } from "@sculptor/extension-sdk";
import { useCallback } from "react";

/**
 * The per-workspace extension-setting key under which a workspace's assigned ticket
 * is stored. Exported so the board can read the same keys the panel writes (via
 * `useExtensionSettings`) — the two must agree on the format.
 */
export const ticketAssignmentKey = (workspaceId: string | null): string => `assignment:${workspaceId ?? "none"}`;

export type TicketAssignment = {
  /**
   * The ticket the workspace is explicitly assigned to, or `null` when it has no
   * explicit assignment and falls back to the branch (primary) ticket.
   */
  assignedTicketId: string | null;
  /** Assign a ticket to this workspace. */
  assign: (identifier: string) => void;
  /** Drop the assignment, reverting to the branch ticket. */
  clear: () => void;
};

/**
 * A workspace's explicit ticket assignment — the user's own assertion of which
 * Linear ticket the workspace is for — persisted via the extension-settings SDK
 * under a per-workspace key. This is the single piece of state the panel and the
 * banner widget share: the panel writes it (assign / clear) and both read it, so
 * the ticket stays consistent across the two surfaces. The board reads it too
 * (via `useExtensionSettings`), so a workspace shows under its assigned ticket even
 * when the branch name carries no identifier. `workspaceId` may be null in
 * contexts without a workspace, where the hook is inert.
 */
export const useTicketAssignment = (workspaceId: string | null): TicketAssignment => {
  const [raw, setRaw] = useExtensionSetting(ticketAssignmentKey(workspaceId));

  const assign = useCallback(
    (identifier: string): void => {
      if (!workspaceId) return;
      setRaw(identifier);
    },
    [workspaceId, setRaw],
  );

  const clear = useCallback((): void => {
    if (!workspaceId) return;
    setRaw("");
  }, [workspaceId, setRaw]);

  return { assignedTicketId: raw || null, assign, clear };
};
