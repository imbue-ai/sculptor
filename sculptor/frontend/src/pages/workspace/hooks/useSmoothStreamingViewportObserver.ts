import { useSetAtom } from "jotai";
import type { MutableRefObject, RefObject } from "react";
import { useEffect, useRef } from "react";

import { isSmoothStreamingViewportVisibleAtom } from "~/common/state/atoms/smoothStreaming.ts";

/**
 * Hook that observes the message viewport visibility.
 * When the bottom sentinel goes off-screen, it disables smooth streaming so new snapshots render instantly.
 * When the sentinel re-enters the viewport, smooth streaming is re-enabled.
 *
 * @returns Ref to attach to the bottom sentinel element
 */
export const useSmoothStreamingViewportObserver = (): MutableRefObject<HTMLDivElement | null> => {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const setSmoothStreamingEnabled = useSetAtom(isSmoothStreamingViewportVisibleAtom);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) {
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      setSmoothStreamingEnabled(entry.isIntersecting);
    });

    observer.observe(node);

    return (): void => {
      observer.disconnect();
      setSmoothStreamingEnabled(true);
    };
  }, [setSmoothStreamingEnabled]);

  return sentinelRef;
};

/**
 * Hook that synchronizes smooth streaming state when switching tasks.
 * This complements useSmoothStreamingViewportObserver by handling the case where
 * switching tasks lands you on a page where the sentinel is already in view
 * (no intersection event fires in that case).
 *
 * @param taskID - The current task ID to react to changes
 * @param sentinelRef - Ref to the bottom sentinel element
 */
export const useSmoothStreamingOnTaskSwitch = (taskID: string, sentinelRef: RefObject<HTMLDivElement | null>): void => {
  const setSmoothStreamingEnabled = useSetAtom(isSmoothStreamingViewportVisibleAtom);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) {
      return;
    }

    // Check if the sentinel is currently in the viewport and set smooth streaming accordingly
    const isInView = isElementInViewport(node);
    setSmoothStreamingEnabled(isInView);
  }, [taskID, sentinelRef, setSmoothStreamingEnabled]);
};

const isElementInViewport = (element: HTMLElement): boolean => {
  const rect = element.getBoundingClientRect();
  return (
    rect.top >= 0 &&
    rect.left >= 0 &&
    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
  );
};
