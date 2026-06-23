import { usePluginSetting } from "@sculptor/plugin-sdk";
import { useCallback, useMemo } from "react";

export type ExpandedState = {
  /**
   * Explicit open/closed choices the user has made, keyed by ticket
   * identifier. Tickets absent here fall back to the panel's derived default —
   * this stores only deviations from it, so the default can evolve without
   * being frozen into persisted state.
   */
  overrides: Readonly<Record<string, boolean>>;
  setExpanded: (identifier: string, open: boolean) => void;
};

/**
 * Per-workspace ticket open/closed overrides, persisted via the plugin-settings
 * SDK as a JSON object under a per-workspace key. Persisting (rather than React
 * state) is what lets a manually-toggled section survive the panel remounting.
 * `workspaceId` may be null in contexts without a workspace, where overrides
 * share a single fallback bucket.
 */
export const useExpandedIds = (workspaceId: string | null): ExpandedState => {
  const [raw, setRaw] = usePluginSetting(`expanded:${workspaceId ?? "none"}`);

  const overrides = useMemo<Readonly<Record<string, boolean>>>(() => {
    if (!raw) return {};
    try {
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
      const result: Record<string, boolean> = {};
      for (const [key, value] of Object.entries(parsed)) {
        if (typeof value === "boolean") result[key] = value;
      }
      return result;
    } catch {
      return {};
    }
  }, [raw]);

  const setExpanded = useCallback(
    (identifier: string, open: boolean): void => {
      setRaw(JSON.stringify({ ...overrides, [identifier]: open }));
    },
    [overrides, setRaw],
  );

  return { overrides, setExpanded };
};
