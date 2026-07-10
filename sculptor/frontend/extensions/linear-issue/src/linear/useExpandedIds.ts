import { useExtensionSetting } from "@sculptor/extension-sdk";
import { useCallback, useMemo } from "react";

export type ExpandedState = {
  /**
   * Explicit open/closed choices the user has made, keyed by ticket
   * identifier. Tickets absent here fall back to the panel's derived default —
   * this stores only deviations from it, so the default can evolve without
   * being frozen into persisted state.
   */
  overrides: Readonly<Record<string, boolean>>;
  /**
   * Record the user's open/closed choice. `defaultOpen` is the panel's derived
   * default for this id: when the choice matches it, the override is *deleted*
   * rather than written, so only true deviations persist and a later change to
   * the default rule isn't frozen out by a stored value that merely echoed the
   * old default.
   */
  setExpanded: (identifier: string, open: boolean, defaultOpen: boolean) => void;
};

/**
 * Per-workspace open/closed overrides, persisted via the extension-settings SDK as
 * a JSON object under a per-workspace key. Persisting (rather than React state)
 * is what lets a manually-toggled section survive the panel remounting.
 * `namespace` separates independent collapsible groups (e.g. the ticket
 * sections vs. each ticket's sub-issue disclosure) so their keys can't collide
 * — both are keyed by a Linear identifier, but they live in different maps.
 * `workspaceId` may be null in contexts without a workspace, where overrides
 * share a single fallback bucket.
 */
export const useExpandedIds = (workspaceId: string | null, namespace = "expanded"): ExpandedState => {
  const [raw, setRaw] = useExtensionSetting(`${namespace}:${workspaceId ?? "none"}`);

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
    (identifier: string, open: boolean, defaultOpen: boolean): void => {
      const next = { ...overrides };
      if (open === defaultOpen) {
        delete next[identifier];
      } else {
        next[identifier] = open;
      }
      setRaw(JSON.stringify(next));
    },
    [overrides, setRaw],
  );

  return { overrides, setExpanded };
};
