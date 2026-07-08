import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { clearLinePaint, paintLineRange, shadowRootOf, snippetForRange } from "./spotlightPaint.ts";

/** Result the hook hands back to the caller when a selection completes. */
export type SpotlightCaptureResult = {
  lineStart: number;
  lineEnd: number;
  snippet: string;
  side: "old" | "new" | null;
};

type UseSpotlightCaptureOptions = {
  /**
   * The visible pane — it both hosts the mouse listeners and (recursively)
   * contains the Pierre `<diffs-container>` whose shadow root holds the lines.
   * Passed as an element (from a callback ref, so it updates exactly when the
   * pane mounts) rather than a RefObject, so the listener-attach effect can't
   * miss the mount the way a one-shot readiness-gated effect did.
   */
  paneElement: HTMLElement | null;
  /** Spotlight capture is inert unless the host passes a file to anchor to. */
  enabled: boolean;
  /** Fired when the user completes a click (single line) or drag (range). */
  onCapture: (result: SpotlightCaptureResult) => void;
};

type UseSpotlightCaptureResult = {
  /** Absolute style for the floating pill, or null when it should be hidden. */
  buttonStyle: CSSProperties | null;
  /** True while a line selection is in progress (mousedown → mouseup). */
  isSelecting: boolean;
  /** Wire onto the pill's `onMouseDown` to begin a click/drag selection. */
  onButtonMouseDown: (e: ReactMouseEvent) => void;
};

/** The Pierre line row nearest to an event's composed path, or null. */
const lineElementFromEvent = (e: MouseEvent): HTMLElement | null => {
  const el = e
    .composedPath()
    .find((node): node is HTMLElement => node instanceof HTMLElement && node.matches("[data-line]"));
  return el ?? null;
};

const lineNumberOf = (el: HTMLElement | null): number | null => {
  if (!el) return null;
  const raw = el.getAttribute("data-line");
  if (!raw) return null;
  const n = parseInt(raw, 10);
  return Number.isNaN(n) ? null : n;
};

/** Pierre tags each row `addition` / `deletion` / `context`; map to diff side. */
const sideOf = (el: HTMLElement | null): "old" | "new" | null => {
  const type = el?.getAttribute("data-line-type");
  if (type === "addition") return "new";
  if (type === "deletion") return "old";
  return null;
};

export const useSpotlightCapture = ({
  paneElement,
  enabled,
  onCapture,
}: UseSpotlightCaptureOptions): UseSpotlightCaptureResult => {
  const [buttonStyle, setButtonStyle] = useState<CSSProperties | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);

  // The line the pill currently anchors to. Held in a ref (not state) so the
  // document-level drag handlers always read the live value.
  const activeLineRef = useRef<number | null>(null);
  const selectStartRef = useRef<number | null>(null);
  const selectCurrentRef = useRef<number | null>(null);
  // Keep the latest onCapture reachable from the effect without re-subscribing.
  const onCaptureRef = useRef(onCapture);
  useEffect(() => {
    onCaptureRef.current = onCapture;
  }, [onCapture]);

  const positionPillAt = useCallback(
    (lineEl: HTMLElement): void => {
      const lineRect = lineEl.getBoundingClientRect();
      const bounds = paneElement?.getBoundingClientRect();
      // Right-align to the visible pane's right edge so the pill never overlaps
      // the line-number gutter on the left; vertically centre on the line.
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

  // Paint the given line range blue (clearing all others), reusing the shared
  // shadow-DOM paint helper so capture and hover-highlight agree on the DOM.
  const paintRange = useCallback(
    (start: number, end: number): void => {
      const shadowRoot = shadowRootOf(paneElement);
      if (shadowRoot) paintLineRange(shadowRoot, start, end);
    },
    [paneElement],
  );

  const clearPaint = useCallback((): void => {
    const shadowRoot = shadowRootOf(paneElement);
    if (shadowRoot) clearLinePaint(shadowRoot);
  }, [paneElement]);

  // Hover tracking: anchor the pill to whatever line the pointer is over.
  // Crucially, we do NOT hide the pill when the pointer moves off a line onto
  // the gutter or the pill itself — only when it leaves the whole pane — so the
  // user can travel from the line to the pill without it vanishing.
  //
  // Listeners live on the visible pane, NOT the Pierre wrapper: the pill is
  // `position: fixed` but rendered as a SIBLING of the Pierre content, so
  // attaching to the Pierre wrapper would fire `mouseleave` the instant the
  // pointer crossed onto the pill (a non-descendant), hiding it — the flicker.
  // The pane encloses both the pill and the Pierre content, so hovering the
  // pill stays "inside" and never triggers a leave.
  //
  // Keyed on `paneElement` (a callback-ref state), so the listeners attach the
  // moment the pane mounts regardless of highlighter-readiness timing. No
  // readiness gate is needed: the move handler simply finds no `[data-line]`
  // until Pierre has painted rows, so the pill stays hidden until there's
  // something to point at.
  useEffect(() => {
    if (!paneElement || !enabled) return;

    const handleMove = (e: MouseEvent): void => {
      if (isSelecting) return;
      const lineEl = lineElementFromEvent(e);
      const line = lineNumberOf(lineEl);
      if (line !== null && lineEl !== null) {
        activeLineRef.current = line;
        positionPillAt(lineEl);
      }
    };

    const handleLeave = (): void => {
      if (isSelecting) return;
      activeLineRef.current = null;
      setButtonStyle(null);
    };

    paneElement.addEventListener("mousemove", handleMove, { passive: true });
    paneElement.addEventListener("mouseleave", handleLeave);
    return (): void => {
      paneElement.removeEventListener("mousemove", handleMove);
      paneElement.removeEventListener("mouseleave", handleLeave);
    };
  }, [paneElement, enabled, isSelecting, positionPillAt]);

  // Selection choreography: attach document-level listeners while a drag is in
  // progress so the release can land anywhere (over a line, the gutter, or off
  // the pane entirely), not just back on the pill.
  useEffect(() => {
    if (!isSelecting) return;

    const handleMove = (e: MouseEvent): void => {
      const line = lineNumberOf(lineElementFromEvent(e));
      if (line === null) return;
      selectCurrentRef.current = line;
      const start = selectStartRef.current;
      if (start !== null) paintRange(start, line);
    };

    const handleUp = (): void => {
      const start = selectStartRef.current;
      const end = selectCurrentRef.current ?? start;
      clearPaint();
      setIsSelecting(false);
      if (start === null || end === null) return;
      const lineStart = Math.min(start, end);
      const lineEnd = Math.max(start, end);
      const shadowRoot = shadowRootOf(paneElement);
      const snippet = shadowRoot ? snippetForRange(shadowRoot, lineStart, lineEnd) : "";
      const startEl = shadowRoot?.querySelector(`[data-line="${lineStart}"]`) as HTMLElement | null;
      onCaptureRef.current({ lineStart, lineEnd, snippet, side: sideOf(startEl) });
    };

    document.addEventListener("mousemove", handleMove, { passive: true });
    document.addEventListener("mouseup", handleUp);
    return (): void => {
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
    };
  }, [isSelecting, paintRange, clearPaint, paneElement]);

  const onButtonMouseDown = useCallback(
    (e: ReactMouseEvent): void => {
      e.preventDefault();
      e.stopPropagation();
      const start = activeLineRef.current;
      if (start === null) return;
      selectStartRef.current = start;
      selectCurrentRef.current = start;
      setIsSelecting(true);
      paintRange(start, start);
    },
    [paintRange],
  );

  return { buttonStyle, isSelecting, onButtonMouseDown };
};
