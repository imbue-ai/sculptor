import { useAtom } from "jotai";
import type { MouseEvent as ReactMouseEvent, ReactElement, RefObject } from "react";
import { useCallback, useEffect, useRef } from "react";

import { ElementIds } from "~/api";

import { splitDiffColumnRatioAtom } from "./atoms/diffPanel.ts";
import styles from "./SplitDiffHandle.module.scss";

const MIN_SPLIT_RATIO = 20;
const MAX_SPLIT_RATIO = 80;
const CENTER_SPLIT_RATIO = 50;

type SplitDiffHandleProps = {
  /**
   * Ref to the container element whose bounds define the handle's coordinate
   * space.  The handle will be positioned absolutely within this container.
   * The container must also include (at any depth) at least one Pierre
   * `diffs-container` shadow DOM so the handle can read actual grid column
   * widths for pixel-accurate positioning.
   */
  containerRef: RefObject<HTMLElement | null>;
};

/**
 * Draggable vertical handle that controls the left/right column ratio in
 * side-by-side diffs.  Render this as a sibling of the scrollable diff
 * content inside a `position: relative` wrapper.
 */
export const SplitDiffHandle = ({ containerRef }: SplitDiffHandleProps): ReactElement => {
  const [splitRatio, setSplitRatio] = useAtom(splitDiffColumnRatioAtom);
  const handleRef = useRef<HTMLDivElement>(null);

  /**
   * Position the drag handle at the actual grid boundary inside Pierre's
   * shadow DOM.  We read resolved `gridTemplateColumns` from the first
   * visible `[data-diffs][data-type='split']` element to get exact pixel
   * widths, accounting for fixed-width line-number columns in wrap mode.
   */
  const syncHandlePosition = useCallback((): void => {
    const container = containerRef.current;
    const handleEl = handleRef.current;
    if (!container || !handleEl) return;

    const shadowRoot = container.querySelector("diffs-container")?.shadowRoot;
    if (!shadowRoot) return;

    const diffsEl = shadowRoot.querySelector<HTMLElement>("[data-diffs][data-type='split']");
    if (!diffsEl) return;

    const cols = getComputedStyle(diffsEl).gridTemplateColumns;
    const colWidths = cols
      .split(/\s+/)
      .map(parseFloat)
      .filter((n) => !Number.isNaN(n));

    // In wrap mode (4 columns), the boundary is after column 2.
    // In scroll mode (2 columns), the boundary is after column 1.
    const leftColumnsCount = colWidths.length >= 4 ? 2 : 1;
    let leftWidth = 0;
    for (let i = 0; i < leftColumnsCount && i < colWidths.length; i++) {
      leftWidth += colWidths[i];
    }

    const gap = parseFloat(getComputedStyle(diffsEl).gap) || 0;
    const splitPx = leftWidth + gap / 2;

    const containerRect = container.getBoundingClientRect();
    const diffsRect = diffsEl.getBoundingClientRect();
    handleEl.style.left = `${diffsRect.left - containerRect.left + splitPx}px`;
  }, [containerRef]);

  // Keep the handle pixel-aligned with the grid boundary as layout changes.
  // Observers are stable — they are not torn down when splitRatio changes.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver(syncHandlePosition);
    resizeObserver.observe(container);

    // Watch for Pierre's `diffs-container` elements appearing in the DOM.
    // In the combined "Review all" view these render asynchronously after
    // the handle mounts, so the initial sync may not find them yet.
    const mutationObserver = new MutationObserver(() => requestAnimationFrame(syncHandlePosition));
    mutationObserver.observe(container, { childList: true, subtree: true });

    return (): void => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
    };
  }, [syncHandlePosition, containerRef]);

  // Re-sync pixel position after the atom-driven percentage changes.
  useEffect(() => {
    syncHandlePosition();
  }, [splitRatio, syncHandlePosition]);

  const handleMouseDown = useCallback(
    (e: ReactMouseEvent): void => {
      e.preventDefault();

      const onMouseMove = (moveEvent: MouseEvent): void => {
        const container = containerRef.current;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        const x = moveEvent.clientX - rect.left;
        const pct = Math.min(MAX_SPLIT_RATIO, Math.max(MIN_SPLIT_RATIO, (x / rect.width) * 100));
        setSplitRatio(Math.round(pct));
      };

      const onMouseUp = (): void => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [containerRef, setSplitRatio],
  );

  const handleDoubleClick = useCallback((): void => {
    setSplitRatio(CENTER_SPLIT_RATIO);
  }, [setSplitRatio]);

  return (
    <div
      ref={handleRef}
      className={styles.splitHandle}
      style={{ left: `${splitRatio}%` }}
      data-testid={ElementIds.DIFF_SPLIT_COLUMN_HANDLE}
      onMouseDown={handleMouseDown}
      onDoubleClick={handleDoubleClick}
    />
  );
};
