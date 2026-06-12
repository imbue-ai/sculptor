import type { RefObject } from "react";
import { useEffect, useRef, useState } from "react";

type UseProgressiveCollapseResult = {
  hiddenPriorities: Set<number>;
};

const EMPTY_SET: Set<number> = new Set();

/** Estimated width of the overflow "..." button in pixels. */
const OVERFLOW_BUTTON_WIDTH_ESTIMATE = 30;

function setsAreEqual(a: Set<number>, b: Set<number>): boolean {
  if (a.size !== b.size) {
    return false;
  }

  for (const item of a) {
    if (!b.has(item)) {
      return false;
    }
  }
  return true;
}

/**
 * Progressively hides lower-priority items when the container is too narrow.
 *
 * Items opt in via `data-collapse-priority="N"` on direct children of the
 * container. Lower N = lower priority = hidden first. Elements with
 * `data-spacer` or `data-overflow` are excluded from content width
 * measurements but `data-spacer` elements still count towards the gap total.
 *
 * Natural widths are cached so that hidden (unmounted) items still contribute
 * to the "everything visible" calculation, preventing hide/show oscillation.
 */
export function useProgressiveCollapse(containerRef: RefObject<HTMLElement | null>): UseProgressiveCollapseResult {
  const [hiddenPriorities, setHiddenPriorities] = useState<Set<number>>(EMPTY_SET);
  const rafIdRef = useRef<number>(0);
  const widthCacheRef = useRef<Map<number, number>>(new Map());

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const computeCollapse = (): void => {
      const containerWidth = container.clientWidth;
      if (containerWidth === 0) {
        return;
      }

      const style = getComputedStyle(container);
      const gap = parseFloat(style.gap) || 0;
      const paddingLeft = parseFloat(style.paddingLeft) || 0;
      const paddingRight = parseFloat(style.paddingRight) || 0;
      const availableWidth = containerWidth - paddingLeft - paddingRight;

      const widthCache = widthCacheRef.current;
      let fixedWidth = 0;
      let fixedCount = 0;
      // Non-content children (spacer) have no intrinsic width but still
      // occupy a gap slot between their neighbours.
      let nonContentChildCount = 0;

      for (const child of Array.from(container.children) as Array<HTMLElement>) {
        if (child.dataset.spacer !== undefined) {
          nonContentChildCount++;
          continue;
        }

        // The overflow button is only present when items are already hidden.
        // Skip it so it doesn't inflate the "everything visible" calculation.
        if (child.dataset.overflow !== undefined) {
          continue;
        }

        const priorityAttr = child.dataset.collapsePriority;
        if (priorityAttr !== undefined) {
          const priority = parseInt(priorityAttr, 10);
          const width = child.getBoundingClientRect().width;
          widthCache.set(priority, width);
        } else {
          fixedWidth += child.getBoundingClientRect().width;
          fixedCount++;
        }
      }

      // Build the full list of collapsible items from the cache (includes
      // items that are currently hidden and therefore not in the DOM).
      const collapsibleItems = Array.from(widthCache.entries())
        .map(([priority, width]) => ({ priority, width }))
        .sort((a, b) => a.priority - b.priority);

      // Compute total needed if everything were visible. Include
      // nonContentChildCount so the spacer's gap contributions are counted.
      const totalCollapsibleWidth = collapsibleItems.reduce((sum, item) => sum + item.width, 0);
      const totalItemCount = fixedCount + collapsibleItems.length + nonContentChildCount;
      const totalGaps = totalItemCount > 1 ? (totalItemCount - 1) * gap : 0;
      let totalNeeded = fixedWidth + totalCollapsibleWidth + totalGaps;

      // Progressively hide lowest-priority items until content fits.
      const newHidden = new Set<number>();

      for (const item of collapsibleItems) {
        if (totalNeeded <= availableWidth) {
          break;
        }

        newHidden.add(item.priority);
        totalNeeded -= item.width + gap;

        // When the first item is hidden, the overflow button will appear.
        if (newHidden.size === 1) {
          totalNeeded += OVERFLOW_BUTTON_WIDTH_ESTIMATE + gap;
        }
      }

      setHiddenPriorities((prev) => {
        if (setsAreEqual(prev, newHidden)) {
          return prev;
        }
        return newHidden;
      });
    };

    const scheduleCompute = (): void => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
      }
      rafIdRef.current = requestAnimationFrame(computeCollapse);
    };

    const resizeObserver = new ResizeObserver(scheduleCompute);
    resizeObserver.observe(container);

    // Also watch for child additions/removals so we re-compute when React
    // mounts or unmounts collapsible items.
    const mutationObserver = new MutationObserver(scheduleCompute);
    mutationObserver.observe(container, { childList: true, subtree: true });

    return (): void => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
      }
    };
  }, [containerRef]);

  return { hiddenPriorities };
}
