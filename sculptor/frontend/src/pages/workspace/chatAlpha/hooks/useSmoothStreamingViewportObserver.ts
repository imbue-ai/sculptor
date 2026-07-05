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
  const setIsViewportVisible = useSetAtom(isSmoothStreamingViewportVisibleAtom);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) {
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      setIsViewportVisible(entry.isIntersecting);
    });

    observer.observe(node);

    return (): void => {
      observer.disconnect();
      setIsViewportVisible(true);
    };
  }, [setIsViewportVisible]);

  return sentinelRef;
};

/**
 * Hook that synchronizes smooth streaming state when switching agents.
 * This complements useSmoothStreamingViewportObserver by handling the case where
 * switching agents lands you on a page where the sentinel is already in view
 * (no intersection event fires in that case).
 *
 * @param agentId - The current agent ID to react to changes
 * @param sentinelRef - Ref to the bottom sentinel element
 */
export const useSmoothStreamingOnAgentSwitch = (
  agentId: string,
  sentinelRef: RefObject<HTMLDivElement | null>,
): void => {
  const setIsViewportVisible = useSetAtom(isSmoothStreamingViewportVisibleAtom);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) {
      return;
    }

    // Check if the sentinel is currently in the viewport and set visibility accordingly
    const isInView = isElementInViewport(node);
    setIsViewportVisible(isInView);
  }, [agentId, sentinelRef, setIsViewportVisible]);
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
