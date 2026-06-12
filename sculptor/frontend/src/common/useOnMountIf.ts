import { useEffect } from "react";

/**
 * Runs `fn` once on mount, but only if `condition` is true at mount time.
 *
 * Use this for one-shot signals captured from props (or other inputs) at the
 * moment of the component's first render — e.g. focusing an element when a
 * deep-link URL param tells us to. Subsequent changes to `condition` do NOT
 * re-run `fn`; the value is read once and never observed again.
 *
 * Why this helper exists: the same shape inlined as
 *
 *   useEffect(() => { if (condition) fn(); }, []);
 *
 * trips `react-hooks/exhaustive-deps` because `condition` and `fn` are read
 * inside an effect with empty deps. The lint rule is conservative — it
 * cannot tell "I forgot to react to changes" (a real bug) from "I
 * deliberately don't want to react to changes" (this case). This helper
 * centralizes the suppression in one audited place so callsites stay
 * readable and the intent is in the API name.
 *
 * Don't use this when `fn` should re-run as `condition` flips — that's
 * `useEffect(() => { if (condition) fn(); }, [condition])`. Reach for this
 * only when re-firing would be wrong (e.g. would steal focus from the user
 * after they've moved on).
 */
export const useOnMountIf = (condition: boolean, fn: () => void): void => {
  useEffect(() => {
    if (condition) {
      fn();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
