// A single-axis resize divider. Drags are applied relative to the size captured at
// pointer-down, and a global body class suppresses webview pointer events for the
// drag's lifetime (Electron <webview> runs in a separate process, so a cursor
// crossing one would otherwise freeze the drag). Keyboard arrows step by 10% of the
// parent.

import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import styles from "./ResizeHandle.module.scss";

const BODY_RESIZING_CLASS = "sculptor-resizing";

// Counter so concurrent drags (e.g. nested handles) don't clear the class early.
let activeDragCount = 0;

const beginGlobalDrag = (): void => {
  activeDragCount += 1;
  document.body.classList.add(BODY_RESIZING_CLASS);
};

const endGlobalDrag = (): void => {
  activeDragCount = Math.max(0, activeDragCount - 1);
  if (activeDragCount === 0) {
    document.body.classList.remove(BODY_RESIZING_CLASS);
  }
};

const KEYBOARD_STEP_FRACTION = 0.1;

type ResizeHandleProps = {
  axis: "x" | "y";
  /** Current size (px) at pointer-down, so deltas apply relative to the start. */
  getSize: () => number;
  /** New size = startSize + direction * pointerDelta. */
  onResize: (nextSizePx: number) => void;
  /** 1 = moving the pointer positively on the axis grows the section; -1 = shrinks. */
  direction?: 1 | -1;
  /**
   * "edge-overlay" floats the handle over one edge of its nearest positioned
   * ancestor instead of occupying flow space between two siblings (e.g. the
   * workspace sidebar's right border). The overlaid edge is the one the
   * controlled region grows toward, derived from axis + direction.
   */
  variant?: "default" | "edge-overlay";
  /**
   * Reported as aria-valuenow/-valuemin/-valuemax on the separator, in whatever
   * unit the caller resizes with (a percentage or a pixel width) — assistive
   * tech only needs now/min/max to be consistent with each other.
   */
  ariaValueNow?: number;
  ariaValueMin?: number;
  ariaValueMax?: number;
  className?: string;
  ariaLabel?: string;
  "data-testid"?: string;
};

export const ResizeHandle = ({
  axis,
  getSize,
  onResize,
  direction = 1,
  variant = "default",
  ariaValueNow,
  ariaValueMin,
  ariaValueMax,
  className,
  ariaLabel,
  "data-testid": dataTestId,
}: ResizeHandleProps): ReactElement => {
  const [isDragging, setIsDragging] = useState(false);
  const activeDragCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return (): void => {
      activeDragCleanupRef.current?.();
    };
  }, []);

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>): void => {
      if (event.button !== 0) {
        return;
      }
      event.preventDefault();
      const startCoord = axis === "x" ? event.clientX : event.clientY;
      const startSize = getSize();
      setIsDragging(true);
      beginGlobalDrag();

      const handlePointerMove = (moveEvent: PointerEvent): void => {
        const current = axis === "x" ? moveEvent.clientX : moveEvent.clientY;
        onResize(startSize + direction * (current - startCoord));
      };

      // A drag ends on pointerup OR pointercancel — the latter fires when a browser/OS
      // gesture (e.g. touch panning) hijacks the pointer. Without it the listeners stay
      // attached, the body class keeps webview pointer events suppressed, and any pointer
      // movement keeps resizing with no button held.
      const endDrag = (): void => {
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", endDrag);
        window.removeEventListener("pointercancel", endDrag);
        activeDragCleanupRef.current = null;
        setIsDragging(false);
        endGlobalDrag();
      };
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", endDrag);
      window.addEventListener("pointercancel", endDrag);
      activeDragCleanupRef.current = endDrag;
    },
    [axis, direction, getSize, onResize],
  );

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>): void => {
      const negativeKey = axis === "x" ? "ArrowLeft" : "ArrowUp";
      const positiveKey = axis === "x" ? "ArrowRight" : "ArrowDown";
      const sign = event.key === negativeKey ? -1 : event.key === positiveKey ? 1 : 0;
      if (sign === 0) {
        return;
      }
      event.preventDefault();
      const parent = event.currentTarget.parentElement;
      const parentSize = parent
        ? axis === "x"
          ? parent.getBoundingClientRect().width
          : parent.getBoundingClientRect().height
        : 0;
      const step = parentSize > 0 ? parentSize * KEYBOARD_STEP_FRACTION : 0;
      if (step === 0) {
        return;
      }
      onResize(getSize() + direction * sign * step);
    },
    [axis, direction, getSize, onResize],
  );

  const baseClass = axis === "x" ? styles.horizontalResizeHandle : styles.verticalResizeHandle;
  // The overlaid edge is the one the controlled region grows toward: with axis "x",
  // direction 1 means dragging right grows the region, so the handle sits on its
  // right edge (and mirrored for the other three combinations).
  const edgeOverlayClass =
    axis === "x"
      ? direction === 1
        ? styles.edgeOverlayRight
        : styles.edgeOverlayLeft
      : direction === 1
        ? styles.edgeOverlayBottom
        : styles.edgeOverlayTop;
  const combinedClassName = [baseClass, variant === "edge-overlay" ? edgeOverlayClass : undefined, className]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      role="separator"
      aria-orientation={axis === "x" ? "vertical" : "horizontal"}
      aria-label={ariaLabel}
      aria-valuenow={ariaValueNow}
      aria-valuemin={ariaValueMin}
      aria-valuemax={ariaValueMax}
      tabIndex={0}
      className={combinedClassName}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
      data-resize-handle-active={isDragging ? "" : undefined}
      data-testid={dataTestId}
    />
  );
};
