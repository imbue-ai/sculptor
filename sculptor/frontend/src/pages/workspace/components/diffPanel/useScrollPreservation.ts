import type { RefObject } from "react";
import { useLayoutEffect, useRef } from "react";

/**
 * Find the first descendant element with `overflow-y: auto|scroll`.
 * Pierre renders a scrollable wrapper inside the diff content container
 * (which itself has `overflow: hidden`).
 */
export const findScrollableChild = (el: HTMLElement): HTMLElement | null => {
  for (const child of Array.from(el.children)) {
    if (!(child instanceof HTMLElement)) continue;
    const { overflowY } = getComputedStyle(child);
    if (overflowY === "auto" || overflowY === "scroll") return child;
    const nested = findScrollableChild(child);
    if (nested) return nested;
  }
  return null;
};

type UseScrollPreservationParams = {
  containerRef: RefObject<HTMLElement | null>;
  diffString: string | null;
  filePath: string | null;
};

/**
 * Preserves the scroll position of the Pierre diff view when the diff string
 * changes for the same file (e.g. hunk expansion). Saves scrollTop before each
 * layout commit and restores it when the diff content re-renders.
 */
export const useScrollPreservation = ({ containerRef, diffString, filePath }: UseScrollPreservationParams): void => {
  const savedScrollTopRef = useRef(0);
  const prevDiffStringRef = useRef(diffString);
  const prevFilePathRef = useRef(filePath);

  // Save scroll position before every layout commit
  useLayoutEffect(() => {
    const wrapper = containerRef.current;
    if (!wrapper) return;
    const scrollable = findScrollableChild(wrapper);
    if (scrollable) {
      savedScrollTopRef.current = scrollable.scrollTop;
    }
  });

  // Restore scroll position when diff changes for the same file
  useLayoutEffect(() => {
    const isSameFile = filePath === prevFilePathRef.current;
    const hasDiffChanged = diffString !== prevDiffStringRef.current;

    if (hasDiffChanged && isSameFile) {
      const wrapper = containerRef.current;
      if (wrapper && savedScrollTopRef.current > 0) {
        requestAnimationFrame(() => {
          const scrollable = findScrollableChild(wrapper);
          if (scrollable) {
            scrollable.scrollTop = savedScrollTopRef.current;
          }
        });
      }
    }

    prevDiffStringRef.current = diffString;
    prevFilePathRef.current = filePath;
  }, [diffString, filePath, containerRef]);
};
