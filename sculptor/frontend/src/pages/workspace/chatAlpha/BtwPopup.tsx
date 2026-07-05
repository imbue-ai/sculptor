import { IconButton } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { X } from "lucide-react";
import type { CSSProperties, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "../../../api";
import { CHAT_INPUT_ELEMENT_ID } from "../../../common/Constants.ts";
import { btwPopupAtom, closeBtwPopupAtom, setBtwPopupPositionAtom } from "../../../common/state/atoms/btwPopup";
import styles from "./BtwPopup.module.scss";

const POPUP_WIDTH = 360;
const POPUP_HEIGHT = 280;
const DEFAULT_RIGHT_INSET = 16;
const DEFAULT_BOTTOM_INSET = 16;

type Position = { x: number; y: number };

export const BtwPopup = (): ReactElement | null => {
  const popupState = useAtomValue(btwPopupAtom);
  const closePopup = useSetAtom(closeBtwPopupAtom);
  const setPopupPosition = useSetAtom(setBtwPopupPositionAtom);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [dragOffset, setDragOffset] = useState<Position | null>(null);
  const [localPosition, setLocalPosition] = useState<Position | null>(null);

  const handleDragMouseDown = useCallback((event: React.MouseEvent<HTMLDivElement>): void => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const rect = container.getBoundingClientRect();
    setDragOffset({ x: event.clientX - rect.left, y: event.clientY - rect.top });
    event.preventDefault();
  }, []);

  // Move focus into the popup when it mounts so Esc and Tab work without
  // requiring the user to click into the popup first.
  useEffect(() => {
    containerRef.current?.focus();
  }, []);

  // Hand focus back to the chat input synchronously, then close the atom.
  // Doing this in the click/key handler (rather than in an unmount cleanup)
  // avoids racing with React's DOM tear-down: the chat input is fully
  // mounted at this point, focus() lands cleanly, and the popup unmount
  // afterwards has nothing left to fight with.
  const closeAndRestoreFocus = useCallback((): void => {
    const chatInputContainer = document.getElementById(CHAT_INPUT_ELEMENT_ID);
    const editable = chatInputContainer?.querySelector("[contenteditable]") as HTMLElement | null;
    editable?.focus();
    closePopup();
  }, [closePopup]);

  // Esc dismisses the popup. We listen on the document so the shortcut
  // works regardless of which element inside the popup currently has focus.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeAndRestoreFocus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return (): void => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [closeAndRestoreFocus]);

  // Wires `mousemove`/`mouseup` listeners to the document while a drag is
  // in flight, clamps the live position to the viewport, and commits the
  // final position to the popup atom on release. The component fully
  // unmounts on close (parent-gated render), so there is no close-reset
  // effect needed — drag state dies with the component.
  useEffect(() => {
    if (!dragOffset) {
      return;
    }

    const onMove = (event: MouseEvent): void => {
      // Popup is `position: fixed`, so left/top are viewport-relative;
      // clamp to the viewport rather than to any containing element.
      const x = Math.max(0, Math.min(window.innerWidth - POPUP_WIDTH, event.clientX - dragOffset.x));
      const y = Math.max(0, Math.min(window.innerHeight - POPUP_HEIGHT, event.clientY - dragOffset.y));
      setLocalPosition({ x, y });
    };

    const onUp = (): void => {
      setDragOffset(null);
      // Commit the final drag position to the atom and drop the local copy
      // so the atom becomes the single source of truth for the resting
      // position (no shadowing on subsequent renders).
      setLocalPosition((committed) => {
        if (committed) {
          setPopupPosition(committed);
        }
        return null;
      });
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return (): void => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [dragOffset, setPopupPosition]);

  if (popupState.kind === "closed") {
    return null;
  }

  const effectivePosition = localPosition ?? popupState.position ?? null;
  const positionStyle: CSSProperties = effectivePosition
    ? { left: effectivePosition.x, top: effectivePosition.y, right: "auto", bottom: "auto" }
    : { right: DEFAULT_RIGHT_INSET, bottom: DEFAULT_BOTTOM_INSET };

  return (
    <div
      ref={containerRef}
      data-testid={ElementIds.BTW_POPUP}
      role="region"
      aria-label="Side chat answer"
      tabIndex={-1}
      className={styles.popup}
      style={positionStyle}
    >
      <div
        data-testid={ElementIds.BTW_POPUP_DRAG_HANDLE}
        className={styles.dragHandle}
        onMouseDown={handleDragMouseDown}
      >
        <span className={styles.dragLabel}>/btw</span>
        <IconButton
          data-testid={ElementIds.BTW_POPUP_CLOSE_BUTTON}
          aria-label="Close side chat"
          size="1"
          variant="ghost"
          color="gray"
          onClick={closeAndRestoreFocus}
        >
          <X size={14} />
        </IconButton>
      </div>
      <div className={styles.body}>
        <div className={styles.questionRow}>
          <div data-testid={ElementIds.BTW_POPUP_QUESTION} className={styles.questionBubble}>
            {popupState.question}
          </div>
        </div>
        <div className={styles.answerRow}>
          <div className={styles.avatarDot} aria-hidden="true" />
          <div
            data-testid={ElementIds.BTW_POPUP_ANSWER}
            className={`${styles.answerBubble} ${popupState.error ? styles.errorBubble : ""}`}
            aria-live="polite"
          >
            {popupState.error ?? popupState.answer}
            {popupState.streaming && !popupState.error && (
              <span
                data-testid={ElementIds.BTW_POPUP_STREAMING_INDICATOR}
                className={styles.streamingCursor}
                aria-hidden="true"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
