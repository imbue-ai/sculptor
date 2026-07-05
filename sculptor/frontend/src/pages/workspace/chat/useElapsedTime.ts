import { useEffect, useRef, useState } from "react";

/**
 * Module-level store that preserves timer origins across component remounts.
 * Keyed by a caller-supplied string (typically the agent ID). This allows the
 * timer to resume from where it left off when the component unmounts and
 * remounts — e.g. when switching workspace tabs.
 *
 * Entries are created when a timer first becomes visible and removed when it
 * becomes invisible (agent goes idle). They are intentionally NOT removed on
 * unmount so remounting mid-session preserves the elapsed time.
 */
const persistedOrigins = new Map<string, number>();

const MILLISECONDS_PER_SECOND = 1000;
const TICK_INTERVAL_MS = 100;

/** Format a duration in milliseconds as a one-decimal seconds string, e.g. "1.5s". */
const formatElapsedSeconds = (elapsedMs: number): string => `${(elapsedMs / MILLISECONDS_PER_SECOND).toFixed(1)}s`;

/**
 * Tracks elapsed time with separate visibility and ticking controls.
 * - `isVisible`: when true the timer is shown; when it transitions from false→true the timer resets.
 *   When it goes false the display resets to "0.0s".
 * - `isTicking`: when true the counter advances; when false the counter freezes at its current value.
 * - `persistKey`: key (e.g. agent ID or tool use ID) to preserve the timer origin across
 *   remounts. The timer resumes from the stored origin instead of resetting to 0.
 *
 * Uses a 100ms interval instead of requestAnimationFrame to avoid unnecessary
 * re-renders — the display only changes once per 100ms (one decimal place).
 */
export const useElapsedTime = (isVisible: boolean, isTicking: boolean, persistKey: string): { elapsed: string } => {
  const startRef = useRef<number | null>(null);
  const frozenOffsetRef = useRef<number>(0);
  const lastDisplayedRef = useRef<string>("0.0s");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [elapsed, setElapsed] = useState<string>("0.0s");

  // Reset when visibility changes
  useEffect(() => {
    if (isVisible) {
      let initialOffset = 0;
      const storedOrigin = persistedOrigins.get(persistKey);
      if (storedOrigin !== undefined) {
        // Resuming after remount: compute elapsed since the original start
        initialOffset = performance.now() - storedOrigin;
      } else {
        // First time visible for this key: record the origin
        persistedOrigins.set(persistKey, performance.now());
      }
      startRef.current = performance.now();
      frozenOffsetRef.current = initialOffset;
      const formatted = formatElapsedSeconds(initialOffset);
      lastDisplayedRef.current = formatted;
      // Syncs from external systems (the persisted-origins store and performance.now())
      // on the visibility transition; the value reflects the clock at this moment and
      // is not derivable during render without an impure time read.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setElapsed(formatted);
    } else {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }

      // Going invisible: clear the stored origin so the next session starts fresh
      persistedOrigins.delete(persistKey);
      startRef.current = null;
      frozenOffsetRef.current = 0;
      lastDisplayedRef.current = "0.0s";
      setElapsed("0.0s");
    }

    return (): void => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isVisible, persistKey]);

  // Start/stop ticking
  useEffect(() => {
    if (!isVisible) return;

    if (isTicking) {
      // Resume: set a new start time, accounting for previously frozen offset
      startRef.current = performance.now();

      const tick = (): void => {
        if (startRef.current === null) return;

        const elapsedMs = performance.now() - startRef.current + frozenOffsetRef.current;
        const formatted = formatElapsedSeconds(elapsedMs);

        if (formatted !== lastDisplayedRef.current) {
          lastDisplayedRef.current = formatted;
          setElapsed(formatted);
        }
      };

      intervalRef.current = setInterval(tick, TICK_INTERVAL_MS);
    } else {
      // Freeze: capture current elapsed into offset
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }

      if (startRef.current !== null) {
        frozenOffsetRef.current += performance.now() - startRef.current;
        startRef.current = null;
      }

      // Ensure the displayed value reflects the frozen offset.
      // The last interval tick may not have fired before the cleanup.
      if (frozenOffsetRef.current > 0) {
        const formatted = formatElapsedSeconds(frozenOffsetRef.current);
        if (formatted !== lastDisplayedRef.current) {
          lastDisplayedRef.current = formatted;
          setElapsed(formatted);
        }
      }
    }

    return (): void => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isVisible, isTicking, persistKey]);

  return { elapsed };
};
