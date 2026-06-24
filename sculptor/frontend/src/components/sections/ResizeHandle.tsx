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

function beginGlobalDrag(): void {
  activeDragCount += 1;
  document.body.classList.add(BODY_RESIZING_CLASS);
}

function endGlobalDrag(): void {
  activeDragCount = Math.max(0, activeDragCount - 1);
  if (activeDragCount === 0) {
    document.body.classList.remove(BODY_RESIZING_CLASS);
  }
}

const KEYBOARD_STEP_FRACTION = 0.1;

type ResizeHandleProps = {
  axis: "x" | "y";
  /** Current size (px) at pointer-down, so deltas apply relative to the start. */
  getSize: () => number;
  /** New size = startSize + direction * pointerDelta. */
  onResize: (nextSizePx: number) => void;
  /** 1 = moving the pointer positively on the axis grows the section; -1 = shrinks. */
  direction?: 1 | -1;
  className?: string;
  ariaLabel?: string;
  "data-testid"?: string;
};

export const ResizeHandle = ({
  axis,
  getSize,
  onResize,
  direction = 1,
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

      const endDrag = (): void => {
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", endDrag);
        activeDragCleanupRef.current = null;
        setIsDragging(false);
        endGlobalDrag();
      };
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", endDrag);
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
  const combinedClassName = className ? `${baseClass} ${className}` : baseClass;

  return (
    <div
      role="separator"
      aria-orientation={axis === "x" ? "vertical" : "horizontal"}
      aria-label={ariaLabel}
      tabIndex={0}
      className={combinedClassName}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
      data-resize-handle-active={isDragging ? "" : undefined}
      data-testid={dataTestId}
    />
  );
};
