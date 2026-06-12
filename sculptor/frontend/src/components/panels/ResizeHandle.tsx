import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import styles from "./DockingLayout.module.scss";

// Native Electron <webview> elements run in a separate render process, so
// pointer events that occur over them are delivered to the embedded
// WebContents — not the host window. While a resize drag is active that
// would freeze the drag the moment the cursor crossed into a webview.
// We mark <body> with this class for the lifetime of the drag so global
// CSS can disable pointer events on webviews until the drag ends.
const BODY_RESIZING_CLASS = "sculptor-resizing";

// Counter so concurrent drags (e.g. nested ResizeHandles) don't clear
// the class until the last one finishes.
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

type ResizeHandleProps = {
  axis: "x" | "y";
  /** Called at pointer-down; returns the current size (in px) so drag deltas
   *  are applied relative to the starting value rather than the latest state. */
  getSize: () => number;
  /** Called with the new size (startSize + direction * pointerDelta). */
  onResize: (nextSizePx: number) => void;
  /** 1 = moving pointer positive on axis grows the panel; -1 = shrinks it. */
  direction?: 1 | -1;
  className?: string;
  ariaLabel?: string;
  "data-testid"?: string;
};

// Keyboard resize steps by 10% of the parent container on each arrow press —
// matches the default feel of react-resizable-panels' keyboard handling.
const KEYBOARD_STEP_FRACTION = 0.1;

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
  // Holds the teardown for the active drag (if any) so the unmount effect can
  // remove stray window listeners if the handle disappears mid-drag — e.g. if
  // a panel's visibility flips while the user is dragging.
  const activeDragCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return (): void => {
      activeDragCleanupRef.current?.();
    };
  }, []);

  const handlePointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      if (e.button !== 0) return;
      e.preventDefault();
      const startCoord = axis === "x" ? e.clientX : e.clientY;
      const startSize = getSize();
      setIsDragging(true);
      beginGlobalDrag();

      const handlePointerMove = (ev: PointerEvent): void => {
        const now = axis === "x" ? ev.clientX : ev.clientY;
        onResize(startSize + direction * (now - startCoord));
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
    (e: ReactKeyboardEvent<HTMLDivElement>): void => {
      const negKey = axis === "x" ? "ArrowLeft" : "ArrowUp";
      const posKey = axis === "x" ? "ArrowRight" : "ArrowDown";
      const sign = e.key === negKey ? -1 : e.key === posKey ? 1 : 0;
      if (sign === 0) return;
      e.preventDefault();
      const parent = e.currentTarget.parentElement;
      const parentSize = parent
        ? axis === "x"
          ? parent.getBoundingClientRect().width
          : parent.getBoundingClientRect().height
        : 0;
      const step = parentSize > 0 ? parentSize * KEYBOARD_STEP_FRACTION : 0;
      if (step === 0) return;
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
