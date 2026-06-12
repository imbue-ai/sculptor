import { useEffect, useRef } from "react";

/**
 * Runs a callback on a fixed interval, cleaning up on unmount.
 * The callback can change between renders without resetting the interval.
 */
export const useInterval = (callback: () => void, intervalMs: number): void => {
  const callbackRef = useRef(callback);

  // Keep the ref in sync so the interval always calls the latest callback
  // without restarting the timer.
  callbackRef.current = callback;

  useEffect(() => {
    const id = setInterval(() => {
      callbackRef.current();
    }, intervalMs);

    return (): void => {
      clearInterval(id);
    };
  }, [intervalMs]);
};
