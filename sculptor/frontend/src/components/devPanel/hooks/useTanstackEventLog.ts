import type { MutationCacheNotifyEvent, QueryCacheNotifyEvent } from "@tanstack/react-query";
import { useAtom } from "jotai";
import { useCallback, useEffect } from "react";

import { tanstackEventLogEnabledAtom } from "~/common/state/atoms/devPanel.ts";
import { queryClient } from "~/common/state/queryClient.ts";

type UseTanstackEventLogResult = {
  isEnabled: boolean;
  handleCheckedChange: (enabled: boolean) => void;
};

type DedupMaps = {
  // Per-query signature of the last observerResultsUpdated we logged. Used
  // to skip refires where nothing meaningful about the query state changed.
  queryResults: WeakMap<object, string>;
  // Per-query / per-mutation set of options signatures already logged.
  // Multiple observers for the same subject (one per useQuery call site,
  // plus duplicates across re-renders) typically all call setOptions with
  // identical content on every render — log each *distinct* signature once
  // per subject, not once per observer.
  subjectOptions: WeakMap<object, Set<string>>;
};

/**
 * `observerResultsUpdated` and `observerOptionsUpdated` fire on every
 * render/subscribe cycle even when nothing meaningful changed. Suppress
 * the no-ops by comparing against the last logged signature. Meaningful
 * changes (fetch transitions, new data, real option changes) still log.
 */
const isNoopUpdate = (maps: DedupMaps, event: QueryCacheNotifyEvent | MutationCacheNotifyEvent): boolean => {
  if (event.type === "observerResultsUpdated") {
    const s = event.query.state;
    const sig = `${s.status}|${s.fetchStatus}|${s.dataUpdatedAt}|${s.errorUpdatedAt}|${s.fetchFailureCount ?? 0}`;
    if (maps.queryResults.get(event.query) === sig) return true;
    maps.queryResults.set(event.query, sig);
    return false;
  }

  if (event.type === "observerOptionsUpdated" && event.observer) {
    const subject = "query" in event ? event.query : event.mutation;
    if (!subject) return false;
    const opts = (event.observer as unknown as { options: Record<string, unknown> }).options;
    const sig = JSON.stringify({
      queryHash: opts.queryHash,
      enabled: opts.enabled,
      staleTime: opts.staleTime,
      refetchInterval: opts.refetchInterval,
      gcTime: opts.gcTime,
      refetchOnMount: opts.refetchOnMount,
      refetchOnWindowFocus: opts.refetchOnWindowFocus,
      refetchOnReconnect: opts.refetchOnReconnect,
    });
    let seen = maps.subjectOptions.get(subject);
    if (seen?.has(sig)) return true;
    if (!seen) {
      seen = new Set();
      maps.subjectOptions.set(subject, seen);
    }
    seen.add(sig);
    return false;
  }
  return false;
};

const createLogEvent =
  (kind: "query" | "mutation", maps: DedupMaps) =>
  (event: QueryCacheNotifyEvent | MutationCacheNotifyEvent): void => {
    if (isNoopUpdate(maps, event)) return;

    // Capture the synchronous stack from the caller that triggered the
    // change (invalidateQueries, setQueryData, observer mount, etc.).
    // Promise-resolved events (e.g. a fetch settling) will show the
    // microtask resolution path instead, which is expected.
    const stack = new Error().stack ?? "";
    const key = "query" in event ? event.query.queryKey : (event.mutation?.options.mutationKey ?? "(no mutationKey)");
    const action = "action" in event && event.action ? ` (${event.action.type})` : "";
    console.groupCollapsed(`%c[TSQ:${kind}] ${event.type}${action}`, "color:#0a7", key);
    console.log("event:", event);
    console.log("stack:\n" + stack);
    console.groupEnd();
  };

/**
 * Subscribe to QueryCache + MutationCache events while the toggle is on
 * and log each one (with a synchronous call-site stack) to the console.
 * Useful for tracing the source of subscriptions and chains of
 * invalidations during debugging.
 *
 * The dedup maps live inside the effect so each on/off cycle starts with
 * a fresh history — re-enabling after a pause shouldn't suppress events
 * that match a stale signature from a previous session.
 */
export const useTanstackEventLog = (): UseTanstackEventLogResult => {
  const [isEnabled, setIsEnabled] = useAtom(tanstackEventLogEnabledAtom);

  useEffect(() => {
    if (!isEnabled) {
      return;
    }
    const maps: DedupMaps = {
      queryResults: new WeakMap(),
      subjectOptions: new WeakMap(),
    };
    const unsubQuery = queryClient.getQueryCache().subscribe(createLogEvent("query", maps));
    const unsubMutation = queryClient.getMutationCache().subscribe(createLogEvent("mutation", maps));
    return (): void => {
      unsubQuery();
      unsubMutation();
      // `maps` falls out of scope here — the WeakMaps become unreachable
      // and get GC'd along with anything they were keyed on.
    };
  }, [isEnabled]);

  const handleCheckedChange = useCallback(
    (enabled: boolean): void => {
      setIsEnabled(enabled);
    },
    [setIsEnabled],
  );

  return { isEnabled, handleCheckedChange };
};
