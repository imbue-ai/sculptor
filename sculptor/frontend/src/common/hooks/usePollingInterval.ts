import { useCallback, useEffect, useRef } from "react";

const DEFAULT_INTERVAL_MS = 3000;
const DEFAULT_TIMEOUT_MS = 600_000;

type UsePollingIntervalReturn = {
  startPolling: (pollFn: () => Promise<void>) => void;
  stopPolling: () => void;
};

/**
 * On-demand polling with a safety timeout.
 *
 * Call `startPolling(fn)` to begin invoking `fn` every `intervalMs`.
 * Polling automatically stops after `timeoutMs` or when `stopPolling` is called.
 * Cleans up on unmount.
 */
export const usePollingInterval = (options?: { intervalMs?: number; timeoutMs?: number }): UsePollingIntervalReturn => {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isFetchingRef = useRef(false);

  const stopPolling = useCallback((): void => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    isFetchingRef.current = false;
  }, []);

  const startPolling = useCallback(
    (pollFn: () => Promise<void>): void => {
      // Clear any existing timers before starting fresh
      stopPolling();

      intervalRef.current = setInterval(() => {
        if (isFetchingRef.current) return;
        isFetchingRef.current = true;
        pollFn()
          .catch(() => {
            // Callers handle their own errors inside pollFn.
            // Swallow here to prevent unhandled promise rejections.
          })
          .finally(() => {
            isFetchingRef.current = false;
          });
      }, intervalMs);

      timeoutRef.current = setTimeout(() => {
        stopPolling();
      }, timeoutMs);
    },
    [intervalMs, timeoutMs, stopPolling],
  );

  useEffect(() => {
    return (): void => {
      stopPolling();
    };
  }, [stopPolling]);

  return { startPolling, stopPolling };
};
