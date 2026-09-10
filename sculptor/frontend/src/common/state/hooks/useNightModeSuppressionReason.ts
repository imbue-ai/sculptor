import { useAtomValue } from "jotai";
import { useState } from "react";

import { useInterval } from "~/common/hooks/useInterval.ts";
import { getNightModeSuppressionReason } from "~/common/nightMode.ts";

import { nightModeAtom } from "../atoms/userConfig.ts";

const NIGHT_MODE_TICK_INTERVAL_MS = 60_000;

/**
 * An "until" override lapses with the clock rather than with a server event, so
 * the reference instant is refreshed on a timer; without it the toggle would
 * stay greyed out past the expiry until something unrelated re-rendered.
 *
 * A tick advances the instant only when doing so changes the answer, comparing
 * against the reason this render already computed, so a quiet minute costs one
 * comparison and no re-render. The comparison is on the answer rather than on
 * which way it moved, so a state that becomes active with the clock would be
 * picked up the same way one that lapses is.
 */
export const useNightModeSuppressionReason = (): string | null => {
  const nightMode = useAtomValue(nightModeAtom);
  const [now, setNow] = useState(() => new Date());
  const reason = getNightModeSuppressionReason(nightMode, now);

  useInterval(() => {
    const next = new Date();
    if (getNightModeSuppressionReason(nightMode, next) !== reason) {
      setNow(next);
    }
  }, NIGHT_MODE_TICK_INTERVAL_MS);

  return reason;
};
