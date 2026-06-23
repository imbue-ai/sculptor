import type { Virtualizer } from "@tanstack/react-virtual";
import type { MutableRefObject, RefObject } from "react";
import { useCallback } from "react";

type UseViewportStabilityReturn = {
  onHeightChange: (messageIndex: number) => void;
};

export const useViewportStability = (
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  isProgrammaticScrollRef: MutableRefObject<boolean>,
): UseViewportStabilityReturn => {
  const onHeightChange = useCallback(
    (messageIndex: number): void => {
      const el = scrollContainerRef.current;
      if (!el) return;

      const virtualItems = virtualizer.getVirtualItems();
      if (virtualItems.length === 0) return;

      // Find the first visible item (first item whose end extends past scrollTop)
      const scrollTop = el.scrollTop;
      const firstVisibleItem = virtualItems.find((item) => item.start + item.size > scrollTop);
      if (!firstVisibleItem) return;

      // Only compensate if the changed item is above the first visible item
      if (messageIndex >= firstVisibleItem.index) return;

      // Snapshot scrollHeight before DOM update
      const scrollHeightBefore = el.scrollHeight;

      // Wait for DOM update and re-measurement
      requestAnimationFrame(() => {
        const scrollHeightAfter = el.scrollHeight;
        const delta = scrollHeightAfter - scrollHeightBefore;
        if (delta !== 0) {
          isProgrammaticScrollRef.current = true;
          el.scrollTop += delta;
        }
      });
    },
    [scrollContainerRef, virtualizer, isProgrammaticScrollRef],
  );

  return { onHeightChange };
};
