import { useEffect, useRef, useState } from "react";

/**
 * A timed latch over a boolean signal. Mirrors `active`, except that once
 * `active` goes true the output stays true for at least `minHoldMs` after
 * the last time `active` was observed true.
 *
 * Useful for short-lived signals like `isFetching`: a fetch that completes in
 * 50ms would otherwise produce a single-frame flash of the loading indicator.
 * Wrapping it with this hook guarantees the indicator is shown long enough to
 * be perceptible.
 *
 * `startDelayMs` adds an optional leading debounce: the latch only turns on
 * after `active` has stayed true continuously for that long, so fetches faster
 * than the delay never show the indicator at all. It defaults to 0, which
 * preserves the show-immediately behavior.
 */
export const useTimedLatch = (active: boolean, minHoldMs: number, startDelayMs: number = 0): boolean => {
  // Don't show on mount unless already active and there's no leading delay to wait out.
  const [isLatched, setIsLatched] = useState(active && startDelayMs <= 0);
  const lastActivatedAtRef = useRef<number | null>(null);

  useEffect(() => {
    // Phase 1 — `active` is true: bring the latch on, then keep refreshing the
    // activation timestamp. While `active` stays true the effect re-runs each
    // time `isLatched` flips (a single tick on the rising edge), so consecutive
    // activations extend the latch with trailing-debounce semantics.
    if (active) {
      // Already on (or just turned on): refresh the timestamp so the trailing
      // min-hold measures from the most recent activity.
      if (isLatched) {
        lastActivatedAtRef.current = Date.now();
        return;
      }

      // No leading delay: latch on synchronously.
      if (startDelayMs <= 0) {
        lastActivatedAtRef.current = Date.now();
        setIsLatched(true);
        return;
      }
      // Leading debounce: wait `startDelayMs` before turning the latch on. If
      // `active` flips false within the delay (a fast fetch), the cleanup
      // cancels this timer and the indicator never appears.
      const timer = setTimeout(() => {
        lastActivatedAtRef.current = Date.now();
        setIsLatched(true);
      }, startDelayMs);
      return (): void => clearTimeout(timer);
    }
    // Phase 2 — `active` is false: schedule the unlatch for the time
    // remaining until min-hold elapses. The cleanup cancels the timer if
    // `active` flips back true or the component unmounts.
    if (!isLatched) return;
    // Invariant: `isLatched` only goes true via the branch above, which
    // always sets the ref first. Asserting non-null surfaces any future
    // breakage rather than silently treating "now" as the activation start.
    const lastAt = lastActivatedAtRef.current!;
    const remaining = Math.max(0, minHoldMs - (Date.now() - lastAt));
    const timer = setTimeout(() => setIsLatched(false), remaining);
    return (): void => clearTimeout(timer);
  }, [active, isLatched, minHoldMs, startDelayMs]);

  return isLatched;
};
