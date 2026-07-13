import type { MouseEvent as ReactMouseEvent, TouchEvent as ReactTouchEvent } from "react";
import { useCallback, useRef } from "react";

const LONG_PRESS_MS = 450;
// Ignore tiny finger jitter; a real scroll (> this many px) cancels the press.
const MOVE_CANCEL_PX = 10;

type LongPressHandlers = {
  onTouchStart: (e: ReactTouchEvent) => void;
  onTouchMove: (e: ReactTouchEvent) => void;
  onTouchEnd: () => void;
  onTouchCancel: () => void;
  onContextMenu: (e: ReactMouseEvent) => void;
};

/**
 * Detect a long-press (touch hold) or right-click and invoke `onLongPress`.
 * Returns handlers to spread on the target, plus `consumeClick`: the target's
 * onClick must call it FIRST — it returns true (and resets) when the click is
 * the tail end of a long-press, so the caller skips its normal tap action.
 */
export const useLongPress = (onLongPress: () => void): { handlers: LongPressHandlers; consumeClick: () => boolean } => {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startPosRef = useRef<{ x: number; y: number } | null>(null);
  const firedRef = useRef(false);

  const cancel = useCallback((): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const onTouchStart = useCallback(
    (e: ReactTouchEvent): void => {
      firedRef.current = false;
      const touch = e.touches[0];
      startPosRef.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
      cancel();
      timerRef.current = setTimeout(() => {
        firedRef.current = true;
        onLongPress();
      }, LONG_PRESS_MS);
    },
    [cancel, onLongPress],
  );

  const onTouchMove = useCallback(
    (e: ReactTouchEvent): void => {
      const touch = e.touches[0];
      const start = startPosRef.current;
      if (touch && start && Math.hypot(touch.clientX - start.x, touch.clientY - start.y) > MOVE_CANCEL_PX) {
        cancel();
      }
    },
    [cancel],
  );

  const onContextMenu = useCallback(
    (e: ReactMouseEvent): void => {
      // Desktop right-click / any browser long-press that still fires contextmenu:
      // suppress the native menu and open ours instead.
      e.preventDefault();
      firedRef.current = true;
      onLongPress();
    },
    [onLongPress],
  );

  const consumeClick = useCallback((): boolean => {
    if (firedRef.current) {
      firedRef.current = false;
      return true;
    }
    return false;
  }, []);

  return {
    handlers: { onTouchStart, onTouchMove, onTouchEnd: cancel, onTouchCancel: cancel, onContextMenu },
    consumeClick,
  };
};
