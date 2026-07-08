import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { type CapturedRun, capturedRunBetween, clearLinePaint, paintRowRun, shadowRootOf } from "./spotlightPaint.ts";
import { spotlightHighlightColor } from "./spotlightPalette.ts";

/**
 * Result the hook hands back when a selection completes: the per-version line
 * ranges (a cross-side red→green drag yields both) plus the literal snippet.
 */
export type SpotlightCaptureResult = CapturedRun;

type UseSpotlightCaptureOptions = {
  /**
   * The visible pane — it both hosts the mouse listeners and (recursively)
   * contains the Pierre `<diffs-container>` whose shadow root holds the lines.
   * Passed as an element (from a callback ref) so the listener-attach effect
   * updates exactly when the pane mounts.
   */
  paneElement: HTMLElement | null;
  /** Spotlight capture is inert unless the host passes a file to anchor to. */
  enabled: boolean;
  /** Fired when the user completes a click (single line) or drag (range). */
  onCapture: (result: SpotlightCaptureResult) => void;
};

type UseSpotlightCaptureResult = {
  /** Absolute style for the floating capture control, or null when hidden. */
  buttonStyle: CSSProperties | null;
  /** True while a line selection is in progress (mousedown → mouseup). */
  isSelecting: boolean;
  /** Wire onto the capture control's `onMouseDown` to begin a click/drag selection. */
  onButtonMouseDown: (e: ReactMouseEvent) => void;
};

/** The Pierre line row nearest to an event's composed path, or null. */
const lineElementFromEvent = (e: MouseEvent): HTMLElement | null => {
  const el = e
    .composedPath()
    .find((node): node is HTMLElement => node instanceof HTMLElement && node.matches("[data-line]"));
  return el ?? null;
};

export const useSpotlightCapture = ({
  paneElement,
  enabled,
  onCapture,
}: UseSpotlightCaptureOptions): UseSpotlightCaptureResult => {
  const [buttonStyle, setButtonStyle] = useState<CSSProperties | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);

  // The row the control currently anchors to. Held as elements (not numbers) so
  // a cross-side drag is captured by DOM position, and the document-level drag
  // handlers always read the live value.
  const activeRowRef = useRef<HTMLElement | null>(null);
  const selectStartRef = useRef<HTMLElement | null>(null);
  const selectCurrentRef = useRef<HTMLElement | null>(null);
  const onCaptureRef = useRef(onCapture);
  useEffect(() => {
    onCaptureRef.current = onCapture;
  }, [onCapture]);

  const positionButtonAt = useCallback(
    (lineEl: HTMLElement): void => {
      const lineRect = lineEl.getBoundingClientRect();
      const bounds = paneElement?.getBoundingClientRect();
      // Right-align to the visible pane's right edge; vertically centre on the
      // line. (Commit 5 pivots this to a left-gutter `+`.)
      const rightInset = bounds ? Math.max(window.innerWidth - bounds.right + 8, 8) : 8;
      setButtonStyle({
        position: "fixed",
        top: `${lineRect.top + lineRect.height / 2}px`,
        right: `${rightInset}px`,
        transform: "translateY(-50%)",
      });
    },
    [paneElement],
  );

  // The drag preview uses the base palette color; the final chip and its
  // hover-highlight resolve their own rotating color from the anchor.
  const previewRun = useCallback(
    (fromEl: HTMLElement, toEl: HTMLElement): void => {
      const shadowRoot = shadowRootOf(paneElement);
      if (shadowRoot) paintRowRun(shadowRoot, fromEl, toEl, spotlightHighlightColor(0));
    },
    [paneElement],
  );

  const clearPaint = useCallback((): void => {
    const shadowRoot = shadowRootOf(paneElement);
    if (shadowRoot) clearLinePaint(shadowRoot);
  }, [paneElement]);

  // Hover tracking: anchor the control to whatever row the pointer is over. We
  // do NOT hide it when the pointer moves onto the gutter or the control
  // itself — only when it leaves the whole pane — so the user can travel from
  // the line to the control without it vanishing.
  useEffect(() => {
    if (!paneElement || !enabled) return;

    const handleMove = (e: MouseEvent): void => {
      if (isSelecting) return;
      const lineEl = lineElementFromEvent(e);
      if (lineEl !== null) {
        activeRowRef.current = lineEl;
        positionButtonAt(lineEl);
      }
    };

    const handleLeave = (): void => {
      if (isSelecting) return;
      activeRowRef.current = null;
      setButtonStyle(null);
    };

    paneElement.addEventListener("mousemove", handleMove, { passive: true });
    paneElement.addEventListener("mouseleave", handleLeave);
    return (): void => {
      paneElement.removeEventListener("mousemove", handleMove);
      paneElement.removeEventListener("mouseleave", handleLeave);
    };
  }, [paneElement, enabled, isSelecting, positionButtonAt]);

  // Selection choreography: attach document-level listeners while a drag is in
  // progress so the release can land anywhere.
  useEffect(() => {
    if (!isSelecting) return;

    const handleMove = (e: MouseEvent): void => {
      const el = lineElementFromEvent(e);
      if (el === null) return;
      selectCurrentRef.current = el;
      const start = selectStartRef.current;
      if (start !== null) previewRun(start, el);
    };

    const handleUp = (): void => {
      const start = selectStartRef.current;
      const end = selectCurrentRef.current ?? start;
      clearPaint();
      setIsSelecting(false);
      if (start === null || end === null) return;
      const shadowRoot = shadowRootOf(paneElement);
      const run = shadowRoot ? capturedRunBetween(shadowRoot, start, end) : null;
      if (run !== null) onCaptureRef.current(run);
    };

    document.addEventListener("mousemove", handleMove, { passive: true });
    document.addEventListener("mouseup", handleUp);
    return (): void => {
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
    };
  }, [isSelecting, previewRun, clearPaint, paneElement]);

  const onButtonMouseDown = useCallback(
    (e: ReactMouseEvent): void => {
      e.preventDefault();
      e.stopPropagation();
      const start = activeRowRef.current;
      if (start === null) return;
      selectStartRef.current = start;
      selectCurrentRef.current = start;
      setIsSelecting(true);
      previewRun(start, start);
    },
    [previewRun],
  );

  return { buttonStyle, isSelecting, onButtonMouseDown };
};
