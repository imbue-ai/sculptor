import { useEffect, useState } from "react";

/** Returns `value` delayed by `delayMs`, resetting the timer on each change. */
export const useDebouncedValue = <TValue>(value: TValue, delayMs: number): TValue => {
  const [debounced, setDebounced] = useState<TValue>(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
};
