import type { WritableAtom } from "jotai";
import { atom } from "jotai";

type PendingWrite = {
  timeout: ReturnType<typeof setTimeout>;
  value: unknown;
};

const pendingWrites = new Map<string, PendingWrite>();

const flushPendingWrites = (): void => {
  for (const [key, { timeout, value }] of pendingWrites) {
    clearTimeout(timeout);
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Quota exceeded or storage unavailable — best-effort during unload
    }
  }
  pendingWrites.clear();
};

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", flushPendingWrites);
}

const debouncedStorageWrite = (key: string, value: unknown, delayMs: number): void => {
  const existing = pendingWrites.get(key);
  if (existing !== undefined) {
    clearTimeout(existing.timeout);
  }
  pendingWrites.set(key, {
    value,
    timeout: setTimeout(() => {
      try {
        // Storage can be gone by the time the debounce fires (jsdom test
        // teardown); a missed best-effort write must not become an
        // unhandled exception.
        if (typeof localStorage !== "undefined") {
          localStorage.setItem(key, JSON.stringify(value));
        }
      } catch {
        // Quota exceeded or storage unavailable — best-effort, same as flush.
      } finally {
        pendingWrites.delete(key);
      }
    }, delayMs),
  });
};

const readStoredValue = <T>(key: string, initialValue: T): T => {
  if (typeof window === "undefined") {
    return initialValue;
  }

  try {
    const stored = localStorage.getItem(key);
    return stored !== null ? (JSON.parse(stored) as T) : initialValue;
  } catch {
    return initialValue;
  }
};

/**
 * Creates an atom that reads from and writes to localStorage, but debounces
 * the actual storage write by `delayMs` milliseconds. In-memory state updates
 * are immediate, preventing UI lag during rapid updates (e.g., typing).
 *
 * Supports both direct value assignment and functional updates (prev => next).
 * Reads the initial value from localStorage synchronously, equivalent to
 * `atomWithStorage` with `{ getOnInit: true }`.
 *
 * Pending writes are flushed synchronously on `beforeunload` to prevent data
 * loss when the page is closed mid-debounce.
 */
export const atomWithDebouncedStorage = <T>(
  key: string,
  initialValue: T,
  delayMs = 300,
): WritableAtom<T, [T | ((prev: T) => T)], void> => {
  // Wrapping in an object distinguishes "value has been set in this store"
  // (non-null) from "no write yet" (null). When null, the getter re-reads
  // from localStorage so each new Jotai store picks up the latest persisted
  // value — matching the behaviour of atomWithStorage({ getOnInit: true }).
  const storeValueAtom = atom<{ value: T } | null>(null);

  return atom(
    (get) => {
      const entry = get(storeValueAtom);
      return entry !== null ? entry.value : readStoredValue(key, initialValue);
    },
    (get, set, update: T | ((prev: T) => T)) => {
      const entry = get(storeValueAtom);
      const prev = entry !== null ? entry.value : readStoredValue(key, initialValue);
      const newValue = typeof update === "function" ? (update as (prev: T) => T)(prev) : update;
      set(storeValueAtom, { value: newValue });
      debouncedStorageWrite(key, newValue, delayMs);
    },
  );
};
