import { useAtomValue } from "jotai";
import { useState } from "react";

import { useInterval } from "~/common/hooks/useInterval.ts";
import { getNightModeSuppressionReason } from "~/common/nightMode.ts";

import { nightModeAtom } from "../atoms/userConfig.ts";

const NIGHT_MODE_TICK_INTERVAL_MS = 60_000;

/**
 * Why fast mode is unavailable right now, or null when it is available.
 *
 * An "until" override lapses with the clock rather than with a server event, so
 * the reference instant is refreshed on a timer; without it the toggle would
 * stay greyed out past the expiry until something unrelated re-rendered. The
 * tick only advances the instant when doing so changes the answer, so the
 * overwhelming majority of ticks are dropped by React's bail-out rather than
 * re-rendering the chat input every minute.
 */
export const useNightModeSuppressionReason = (): string | null => {
  const nightMode = useAtomValue(nightModeAtom);
  const [now, setNow] = useState(() => new Date());

  useInterval(() => {
    setNow((current) => {
      const next = new Date();
      const hasReasonChanged =
        getNightModeSuppressionReason(nightMode, current) !== getNightModeSuppressionReason(nightMode, next);
      return hasReasonChanged ? next : current;
    });
  }, NIGHT_MODE_TICK_INTERVAL_MS);

  return getNightModeSuppressionReason(nightMode, now);
};
