import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import { isSmoothStreamingUserPreferenceAtom } from "~/common/state/atoms/userConfig.ts";

/**
 * Per-task viewport-visibility atom, set by the IntersectionObserver in
 * useSmoothStreamingViewportObserver. `true` when that task's message tail is
 * in-view, `false` when off-screen.
 *
 * Keyed by task id because several chat panels can be mounted and streaming at
 * once (one per placed agent section). A single shared atom would let an
 * off-screen or differently-laid-out panel flip the gate for the panel the
 * user is actually watching, forcing it to abandon smooth animation and dump
 * text — which reads as choppiness. Scoping per task keeps each panel's gate
 * independent.
 */
export const isSmoothStreamingViewportVisibleAtomFamily = atomFamily((_taskID: string) => atom<boolean>(true));

/**
 * Derived per-task atom: smooth streaming is active for a task only when BOTH
 * the user preference is enabled AND that task's message tail is visible in the
 * viewport.
 */
export const isSmoothStreamingEnabledAtomFamily = atomFamily((taskID: string) =>
  atom<boolean>((get) => {
    const isUserPreferenceEnabled = get(isSmoothStreamingUserPreferenceAtom);
    const isViewportVisible = get(isSmoothStreamingViewportVisibleAtomFamily(taskID));
    return isUserPreferenceEnabled && isViewportVisible;
  }),
);
