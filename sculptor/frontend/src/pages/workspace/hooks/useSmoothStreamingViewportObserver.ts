import { useSetAtom } from "jotai";
import type { MutableRefObject, RefObject } from "react";
import { useEffect, useRef } from "react";

import { isSmoothStreamingViewportVisibleAtomFamily } from "~/common/state/atoms/smoothStreaming.ts";

/**
 * Walk up from `element` to the nearest scrollable ancestor, so the
 * IntersectionObserver measures visibility relative to the chat panel's own
 * scroll container rather than the whole browser viewport. In a multi-panel
 * layout a panel is not full-window, so a viewport-relative observer would
 * report the sentinel as off-screen even when it is visible within its panel.
 * Returns `null` (viewport root) if no scrollable ancestor is found.
 */
const findScrollableAncestor = (element: HTMLElement): HTMLElement | null => {
  let node: HTMLElement | null = element.parentElement;
  while (node) {
    const style = window.getComputedStyle(node);
    const overflowY = style.overflowY;
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
};

/**
 * Hook that observes the message viewport visibility for a single task.
 * When the bottom sentinel goes off-screen, it disables smooth streaming for
 * that task so new snapshots render instantly. When the sentinel re-enters the
 * viewport, smooth streaming is re-enabled.
 *
 * @param taskID - The task whose visibility this sentinel represents.
 * @returns Ref to attach to the bottom sentinel element
 */
export const useSmoothStreamingViewportObserver = (taskID: string): MutableRefObject<HTMLDivElement | null> => {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const setIsViewportVisible = useSetAtom(isSmoothStreamingViewportVisibleAtomFamily(taskID));

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsViewportVisible(entry.isIntersecting);
      },
      { root: findScrollableAncestor(node) },
    );

    observer.observe(node);

    return (): void => {
      observer.disconnect();
      setIsViewportVisible(true);
    };
  }, [setIsViewportVisible]);

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
  const setIsViewportVisible = useSetAtom(isSmoothStreamingViewportVisibleAtomFamily(taskID));

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) {
      return;
    }

    // Check if the sentinel is currently visible within its scroll container
    // (or the viewport, if it isn't in one) and set visibility accordingly.
    setIsViewportVisible(isElementVisibleInScrollParent(node));
  }, [taskID, sentinelRef, setIsViewportVisible]);
};

/**
 * Whether `element` is currently visible within its nearest scrollable
 * ancestor (falling back to the browser viewport). Uses the scroll container's
 * bounds rather than the whole window so a non-full-window chat panel reports
 * correctly.
 */
const isElementVisibleInScrollParent = (element: HTMLElement): boolean => {
  const rect = element.getBoundingClientRect();
  const scrollParent = findScrollableAncestor(element);
  if (scrollParent) {
    const parentRect = scrollParent.getBoundingClientRect();
    return rect.bottom > parentRect.top && rect.top < parentRect.bottom;
  }
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
  return rect.bottom > 0 && rect.top < viewportHeight;
};
