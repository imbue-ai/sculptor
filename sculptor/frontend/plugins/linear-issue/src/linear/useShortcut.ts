import { usePluginSetting } from "@sculptor/plugin-sdk";
import { useCallback } from "react";

export type Shortcut = {
  /**
   * The explicitly-assigned shortcut identifier, or `null` when the workspace
   * has none and the shortcut defaults to the branch (primary) ticket.
   */
  shortcutId: string | null;
  /** Assign a ticket as this workspace's shortcut. */
  setShortcut: (identifier: string) => void;
  /** Drop the override, reverting the shortcut to the branch ticket. */
  clearShortcut: () => void;
};

/**
 * The workspace's assigned Linear shortcut, persisted via the plugin-settings
 * SDK under a per-workspace key. This is the single piece of state the panel
 * and the banner widget share: the panel writes it (assign / clear) and both
 * read it, so the ticket reference stays consistent across the two surfaces.
 * `workspaceId` may be null in contexts without a workspace, where it is inert.
 */
export const useShortcut = (workspaceId: string | null): Shortcut => {
  const [raw, setRaw] = usePluginSetting(`shortcut:${workspaceId ?? "none"}`);

  const setShortcut = useCallback(
    (identifier: string): void => {
      if (!workspaceId) return;
      setRaw(identifier);
    },
    [workspaceId, setRaw],
  );

  const clearShortcut = useCallback((): void => {
    if (!workspaceId) return;
    setRaw("");
  }, [workspaceId, setRaw]);

  return { shortcutId: raw || null, setShortcut, clearShortcut };
};
