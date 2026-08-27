import { atomFamily, atomWithStorage, createJSONStorage } from "jotai/utils";

export type AlphaScrollPosition = {
  firstVisibleMessageId: string;
  pixelOffset: number;
  /** Signed distance from the viewport bottom to the content bottom (the
   *  virtualizer's paddingEnd excluded); negative when the viewport sits past
   *  the content, inside the tail padding. */
  distanceFromBottom: number;
  /** When this position was saved (epoch ms). Only orders the LRU eviction of
   *  persisted positions; entries missing it are treated as oldest. */
  savedAtMs?: number;
};

const STORAGE_KEY_PREFIX = "sculptor-alpha-scroll:";

/**
 * Cap on how many tasks keep a persisted scroll position. Positions are ~100
 * bytes each, so the cap is about hygiene, not quota: without it every task
 * ever visited would leave a localStorage key behind forever. Oldest-saved
 * entries are evicted first.
 */
export const MAX_PERSISTED_SCROLL_POSITIONS = 50;

/** Evict the oldest persisted positions (by savedAtMs) until the count fits
 *  the cap. The just-written key is never a candidate, so a write is always
 *  retained even if its payload carries no timestamp. */
const prunePersistedPositions = (justWrittenKey: string): void => {
  const candidates: Array<{ key: string; savedAtMs: number }> = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key === null || !key.startsWith(STORAGE_KEY_PREFIX) || key === justWrittenKey) continue;
    let savedAtMs = 0;
    try {
      savedAtMs = (JSON.parse(localStorage.getItem(key) ?? "null") as AlphaScrollPosition | null)?.savedAtMs ?? 0;
    } catch {
      // Unparseable entry: leave savedAtMs at 0 so it is evicted first.
    }
    candidates.push({ key, savedAtMs });
  }
  const excess = candidates.length + 1 - MAX_PERSISTED_SCROLL_POSITIONS;
  if (excess <= 0) return;
  candidates.sort((a, b) => a.savedAtMs - b.savedAtMs);
  for (const { key } of candidates.slice(0, excess)) {
    localStorage.removeItem(key);
  }
};

// localStorage, not memory or sessionStorage: restoring where the reader left
// off must survive not just an in-tab reload (mobile PWA relaunch, tab
// eviction) but a full app restart — on desktop, quitting the Electron app
// ends the session, so sessionStorage would forget every position on quit.
// The concerns that usually argue for a narrower scope are covered here:
// cross-session staleness by the restore semantics themselves (an at-bottom
// reader re-lands at the *live* tail via the signed distance, a scrolled-up
// reader re-anchors to a stable message id with a distance fallback),
// concurrent tabs by last-writer-wins — the same policy as the other
// task-keyed localStorage state (prompt drafts, draft agent settings) — and
// unbounded key growth by the LRU prune above. `getOnInit` makes the saved
// value available on the very first read, which the pre-paint mount restore
// depends on.
const alphaScrollStorage = createJSONStorage<AlphaScrollPosition | null>(() => ({
  getItem: (key: string): string | null => localStorage.getItem(key),
  setItem: (key: string, value: string): void => {
    localStorage.setItem(key, value);
    prunePersistedPositions(key);
  },
  removeItem: (key: string): void => localStorage.removeItem(key),
}));

export const alphaScrollPositionAtomFamily = atomFamily((taskId: string) =>
  atomWithStorage<AlphaScrollPosition | null>(`${STORAGE_KEY_PREFIX}${taskId}`, null, alphaScrollStorage, {
    getOnInit: true,
  }),
);
