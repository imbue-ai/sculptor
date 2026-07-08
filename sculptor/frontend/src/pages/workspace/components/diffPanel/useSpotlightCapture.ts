import type { MouseEvent as ReactMouseEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

const MOVEMENT_THRESHOLD = 5;

type HoveredLine = { line: number; rect: DOMRect };

type UseSpotlightCaptureOptions = {
  containerRef: React.RefObject<HTMLDivElement | null>;
  isHighlighterReady: boolean;
};

type UseSpotlightCaptureResult = {
  hoveredLine: HoveredLine | null;
  isDragging: boolean;
  dragStartLine: number | null;
  dragEndLine: number | null;
  onButtonMouseDown: (e: ReactMouseEvent) => void;
  onButtonMouseUp: (e: ReactMouseEvent) => void;
  resolveCapture: (file: string, lineStart: number, lineEnd: number) => { snippet: string } | null;
};

const getLineFromComposedPath = (e: MouseEvent): number | null => {
  const el = e
    .composedPath()
    .find((node): node is HTMLElement => node instanceof HTMLElement && node.matches("[data-line]"));
  if (!el) return null;
  const lineStr = el.getAttribute("data-column-number");
  if (!lineStr) return null;
  const line = parseInt(lineStr, 10);
  return Number.isNaN(line) ? null : line;
};

const getSnippetFromRange = (shadowRoot: ShadowRoot, lineStart: number, lineEnd: number): string => {
  const lines: Array<string> = [];
  const allLines = shadowRoot.querySelectorAll("[data-line]");
  for (const lineEl of allLines) {
    const lineNum = parseInt(lineEl.getAttribute("data-column-number") ?? "", 10);
    if (!Number.isNaN(lineNum) && lineNum >= lineStart && lineNum <= lineEnd) {
      lines.push(lineEl.textContent ?? "");
    }
  }
  return lines.join("\n");
};

const getLineRect = (container: HTMLElement | null, line: number): DOMRect | undefined => {
  if (!container) return undefined;
  const shadowRoot = container.querySelector("diffs-container")?.shadowRoot;
  if (!shadowRoot) return undefined;
  const el = shadowRoot.querySelector(`[data-column-number="${line}"]`) as HTMLElement | null;
  return el?.getBoundingClientRect();
};

export const useSpotlightCapture = ({
  containerRef,
  isHighlighterReady,
}: UseSpotlightCaptureOptions): UseSpotlightCaptureResult => {
  const [hoveredLine, setHoveredLine] = useState<HoveredLine | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartLine, setDragStartLine] = useState<number | null>(null);
  const [dragEndLine, setDragEndLine] = useState<number | null>(null);

  const dragStartYRef = useRef(0);
  const dragStartLineRef = useRef<number | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !isHighlighterReady) return;

    const handleMouseMove = (e: MouseEvent): void => {
      const line = getLineFromComposedPath(e);
      if (line !== null) {
        const rect = getLineRect(container, line);
        setHoveredLine({ line, rect: rect ?? new DOMRect() });
      } else {
        setHoveredLine(null);
      }
    };

    container.addEventListener("mousemove", handleMouseMove, {
      passive: true,
    });
    return (): void => container.removeEventListener("mousemove", handleMouseMove);
  }, [containerRef, isHighlighterReady]);

  const onButtonMouseDown = useCallback(
    (e: ReactMouseEvent): void => {
      e.preventDefault();
      e.stopPropagation();
      const line = hoveredLine?.line;
      if (line === null || line === undefined) return;
      dragStartYRef.current = e.clientY;
      dragStartLineRef.current = line;
      setIsDragging(true);
      setDragStartLine(line);
      setDragEndLine(line);
    },
    [hoveredLine],
  );

  const onButtonMouseUp = useCallback(
    (e: ReactMouseEvent): void => {
      if (!isDragging) return;
      setIsDragging(false);
      const endLine = hoveredLine?.line ?? dragStartLineRef.current;
      const dx = Math.abs(e.clientX - dragStartYRef.current);
      const dy = Math.abs(e.clientY - dragStartYRef.current);
      const didMove = Math.sqrt(dx * dx + dy * dy) >= MOVEMENT_THRESHOLD;
      if (didMove) {
        setDragEndLine(endLine);
      } else {
        const start = dragStartLineRef.current;
        if (start !== null) {
          setDragStartLine(start);
          setDragEndLine(start);
        }
      }
      dragStartLineRef.current = null;
    },
    [isDragging, hoveredLine],
  );

  const resolveCapture = useCallback(
    (file: string, lineStart: number, lineEnd: number): { snippet: string } | null => {
      if (!file) return null;
      const container = containerRef.current;
      const shadowRoot = container?.querySelector("diffs-container")?.shadowRoot;
      const snippet = shadowRoot ? getSnippetFromRange(shadowRoot, lineStart, lineEnd) : "";
      return { snippet };
    },
    [containerRef],
  );

  return {
    hoveredLine,
    isDragging,
    dragStartLine,
    dragEndLine,
    onButtonMouseDown,
    onButtonMouseUp,
    resolveCapture,
  };
};
