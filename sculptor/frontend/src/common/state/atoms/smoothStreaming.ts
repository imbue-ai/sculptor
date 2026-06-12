import { atom } from "jotai";

import { isSmoothStreamingUserPreferenceAtom } from "~/common/state/atoms/userConfig.ts";

/**
 * Writable atom set by the IntersectionObserver in useSmoothStreamingViewportObserver.
 * `true` when the message tail is in-view, `false` when off-screen.
 */
export const isSmoothStreamingViewportVisibleAtom = atom<boolean>(true);

/**
 * Derived atom: smooth streaming is active only when BOTH the user preference
 * is enabled AND the message tail is visible in the viewport.
 */
export const isSmoothStreamingEnabledAtom = atom<boolean>((get) => {
  const isUserPreferenceEnabled = get(isSmoothStreamingUserPreferenceAtom);
  const isViewportVisible = get(isSmoothStreamingViewportVisibleAtom);
  return isUserPreferenceEnabled && isViewportVisible;
});
