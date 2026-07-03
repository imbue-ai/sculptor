import { atomFamily, atomWithStorage, createJSONStorage } from "jotai/utils";

export type AlphaScrollPosition = {
  firstVisibleMessageId: string;
  pixelOffset: number;
  /** Signed distance from the viewport bottom to the content bottom (the
   *  virtualizer's paddingEnd excluded); negative when the viewport sits past
   *  the content, inside the tail padding. */
  distanceFromBottom: number;
};

// sessionStorage, not memory or localStorage: a full page reload (mobile PWA
// relaunch, tab eviction, dev-server reconnect) must not lose the reading
// position — with a memory-only atom the restore falls back to the first-visit
// landing and leaves the reader a page above the live tail once measurements
// settle. Per-tab and gone on tab close, so positions never go stale across
// sessions. `getOnInit` makes the saved value available on the very first
// read, which the pre-paint mount restore depends on.
const alphaScrollStorage = createJSONStorage<AlphaScrollPosition | null>(() => sessionStorage);

export const alphaScrollPositionAtomFamily = atomFamily((taskId: string) =>
  atomWithStorage<AlphaScrollPosition | null>(`sculptor-alpha-scroll:${taskId}`, null, alphaScrollStorage, {
    getOnInit: true,
  }),
);
