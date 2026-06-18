import { usePluginSetting } from "@sculptor/plugin-sdk";
import { useCallback, useMemo } from "react";

export type PinnedIds = {
  pinnedIds: ReadonlyArray<string>;
  pin: (identifier: string) => void;
  unpin: (identifier: string) => void;
};

/**
 * The user's pinned ticket identifiers for a workspace, persisted via the
 * plugin-settings SDK as a JSON array under a per-workspace key. `workspaceId`
 * may be null in contexts without a workspace, where pinning is a no-op.
 */
export const usePinnedIds = (workspaceId: string | null): PinnedIds => {
  const [raw, setRaw] = usePluginSetting(`pinned:${workspaceId ?? "none"}`);

  const pinnedIds = useMemo<ReadonlyArray<string>>(() => {
    if (!raw) return [];
    try {
      const parsed: unknown = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
    } catch {
      return [];
    }
  }, [raw]);

  const pin = useCallback(
    (identifier: string): void => {
      if (!workspaceId || pinnedIds.includes(identifier)) return;
      setRaw(JSON.stringify([...pinnedIds, identifier]));
    },
    [workspaceId, pinnedIds, setRaw],
  );

  const unpin = useCallback(
    (identifier: string): void => {
      if (!workspaceId) return;
      setRaw(JSON.stringify(pinnedIds.filter((id) => id !== identifier)));
    },
    [workspaceId, pinnedIds, setRaw],
  );

  return { pinnedIds, pin, unpin };
};
