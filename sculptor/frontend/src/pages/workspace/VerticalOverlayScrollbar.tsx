import type { PointerEvent as ReactPointerEvent, ReactElement, RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import styles from "./VerticalOverlayScrollbar.module.scss";

// Smallest thumb height (px) so a tiny thumb on very long content stays grabbable.
const MIN_THUMB_HEIGHT = 24;

// Overlay strip width (px). The track is transparent and non-interactive; this
// is just the room the thumb has to widen into from the host's right edge.
const TRACK_WIDTH_PX = 14;

// The overlay portals into the host's Radix theme root, not <body>: the scrollbar
// color tokens (`--scrollbar-thumb-color` → `--gray-a*`) are scoped to
// `.radix-themes` (see styles/tokens.css), so a <body> portal resolves no color
// and paints the thumb transparent. The theme root still sits outside the host's
// `overflow` clip and above the panel resize handle.
const THEME_ROOT_SELECTOR = ".radix-themes";

type Geometry = {
  // Viewport position of the scroll container (from getBoundingClientRect).
  top: number;
  right: number;
  height: number;
  // Scroll metrics of the same element.
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
};

const EMPTY_GEOMETRY: Geometry = {
  top: 0,
  right: 0,
  height: 0,
  scrollTop: 0,
  scrollHeight: 0,
  clientHeight: 0,
};

const computeThumbHeight = (geometry: Geometry): number =>
  Math.max(MIN_THUMB_HEIGHT, (geometry.clientHeight / geometry.scrollHeight) * geometry.height);

type VerticalOverlayScrollbarProps = {
  /** The scrollable element this scrollbar drives and tracks. */
  scrollRef: RefObject<HTMLElement | null>;
  /** Applied to the draggable thumb so tests (and callers) can target it. */
  thumbTestId?: string;
  /**
   * `id` of the scroll container the thumb controls, exposed as the thumb's
   * `aria-controls`. Wiring it gives the `role="scrollbar"` thumb its expected
   * relationship to the scrolled region, so it surfaces in accessibility trees
   * (and Playwright snapshots) instead of reading as empty.
   */
  scrollContainerId?: string;
};

/**
 * A vertical scrollbar rendered as an overlay portaled into the host's Radix
 * theme root, so it can sit above an adjacent panel resize handle without being
 * clipped by the host's `overflow` or trapped beneath it in a sibling stacking
 * context — while still inheriting the theme's color tokens.
 *
 * Only the thumb is interactive (`pointer-events: auto`); the surrounding track
 * is transparent to the pointer, so a drag that starts anywhere other than the
 * thumb falls through to whatever is behind it (the resize handle). The thumb is
 * thin by default and widens on hover/drag — a larger target that, while
 * expanded, owns the pointer over the panel edge. This resolves the
 * narrow-scrollbar vs. splitter hit-box conflict (SCU-1321) generically: any
 * scroll container next to a resize handle adopts it by passing its ref.
 *
 * The host must suppress its own native scrollbar (the `hidden-scrollbar` SCSS
 * mixin) so the two don't both render; this component draws the visible one.
 */
export const VerticalOverlayScrollbar = ({
  scrollRef,
  thumbTestId,
  scrollContainerId,
}: VerticalOverlayScrollbarProps): ReactElement | null => {
  const [geometry, setGeometry] = useState<Geometry>(EMPTY_GEOMETRY);
  const [isHovered, setIsHovered] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);

  // The pointer-move drag handler runs outside React's render, so it reads
  // geometry from a ref synced after each commit (writing a ref during render
  // is disallowed).
  const geometryRef = useRef(geometry);
  useEffect(() => {
    geometryRef.current = geometry;
  });
  const isDraggingRef = useRef(false);
  const dragStartYRef = useRef(0);
  const dragStartScrollTopRef = useRef(0);

  // Mirror the host's geometry so the thumb tracks it, split by update
  // frequency: the hot `scroll` path reads only `scrollTop` (the sole thing a
  // scroll changes), keeping `getBoundingClientRect` — which can force a
  // synchronous layout — on the rarer size/position path.
  useEffect((): (() => void) | void => {
    const element = scrollRef.current;
    if (!element) return;
    const themeRoot = element.closest<HTMLElement>(THEME_ROOT_SELECTOR);
    setPortalTarget(themeRoot);

    const readScrollTop = (): void => {
      setGeometry((prev) => (prev.scrollTop === element.scrollTop ? prev : { ...prev, scrollTop: element.scrollTop }));
    };

    const readRect = (): void => {
      const rect = element.getBoundingClientRect();
      setGeometry((prev) => {
        const next: Geometry = {
          top: rect.top,
          right: rect.right,
          height: rect.height,
          scrollTop: element.scrollTop,
          scrollHeight: element.scrollHeight,
          clientHeight: element.clientHeight,
        };
        if (
          prev.top === next.top &&
          prev.right === next.right &&
          prev.height === next.height &&
          prev.scrollTop === next.scrollTop &&
          prev.scrollHeight === next.scrollHeight &&
          prev.clientHeight === next.clientHeight
        ) {
          return prev;
        }
        return next;
      });
    };

    readRect();
    element.addEventListener("scroll", readScrollTop, { passive: true });
    // Rect, scrollHeight and clientHeight change on panel/window resize and on
    // content growth — the child's height grows scrollHeight without resizing
    // the host (e.g. streaming chat output or an expanding file tree).
    const resizeObserver = new ResizeObserver(readRect);
    resizeObserver.observe(element);
    const content = element.firstElementChild;
    if (content) resizeObserver.observe(content);
    // A layout shift can MOVE the host without resizing it or the window — e.g.
    // collapsing an adjacent sidebar grows a container the host lives in and
    // slides the host sideways. That fires neither the host's own ResizeObserver
    // nor `window resize`, so the fixed, viewport-positioned overlay would stay
    // stranded at the host's old x, floating over whatever moved into that space.
    // Observe the ancestor chain up to the theme root too: whichever ancestor
    // absorbs the shift resizes, which re-reads the host's rect and repositions
    // the overlay. The track is `position: fixed` / `pointer-events: none`, so
    // restyling it can't resize an observed ancestor — no ResizeObserver loop.
    for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
      resizeObserver.observe(ancestor);
      if (ancestor === themeRoot) break;
    }
    window.addEventListener("resize", readRect);

    return (): void => {
      element.removeEventListener("scroll", readScrollTop);
      resizeObserver.disconnect();
      window.removeEventListener("resize", readRect);
    };
  }, [scrollRef]);

  const scrollTo = useCallback(
    (scrollTop: number): void => {
      const element = scrollRef.current;
      if (!element) return;
      const maxScroll = element.scrollHeight - element.clientHeight;
      element.scrollTop = Math.max(0, Math.min(scrollTop, maxScroll));
    },
    [scrollRef],
  );

  const handlePointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      if (e.button !== 0) return;
      // Claim the gesture before it can reach the resize handle behind us.
      e.preventDefault();
      e.stopPropagation();
      e.currentTarget.setPointerCapture(e.pointerId);
      isDraggingRef.current = true;
      setIsDragging(true);
      dragStartYRef.current = e.clientY;
      dragStartScrollTopRef.current = scrollRef.current?.scrollTop ?? 0;
    },
    [scrollRef],
  );

  const handlePointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      if (!isDraggingRef.current) return;
      const g = geometryRef.current;
      const maxScroll = g.scrollHeight - g.clientHeight;
      const travel = g.height - computeThumbHeight(g);
      if (maxScroll <= 0 || travel <= 0) return;
      const deltaY = e.clientY - dragStartYRef.current;
      scrollTo(dragStartScrollTopRef.current + (deltaY * maxScroll) / travel);
    },
    [scrollTo],
  );

  const endDrag = useCallback((): void => {
    isDraggingRef.current = false;
    setIsDragging(false);
  }, []);

  const maxScroll = Math.max(0, geometry.scrollHeight - geometry.clientHeight);
  if (maxScroll <= 0 || geometry.height <= 0 || portalTarget === null) return null;

  const thumbHeight = computeThumbHeight(geometry);
  const travel = geometry.height - thumbHeight;
  const scrollFraction = geometry.scrollTop / maxScroll;
  const thumbTop = travel > 0 ? scrollFraction * travel : 0;
  // Scroll progress as a 0–100 percentage for the ARIA scrollbar role, which
  // pairs `aria-valuenow` with `aria-controls`. It rides the same per-scroll
  // render as `thumbTop`, so no extra work outside the existing update path.
  const scrollPercent = Math.round(scrollFraction * 100);
  const isActive = isHovered || isDragging;

  return createPortal(
    <div
      className={`${styles.track} ${isActive ? styles.active : ""}`}
      style={{
        top: geometry.top,
        left: geometry.right - TRACK_WIDTH_PX,
        width: TRACK_WIDTH_PX,
        height: geometry.height,
      }}
    >
      <div
        className={styles.thumb}
        data-testid={thumbTestId}
        role="scrollbar"
        aria-orientation="vertical"
        aria-label="Scrollbar"
        aria-controls={scrollContainerId}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={scrollPercent}
        style={{ height: thumbHeight, transform: `translateY(${thumbTop}px)` }}
        onPointerEnter={(): void => setIsHovered(true)}
        onPointerLeave={(): void => setIsHovered(false)}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onLostPointerCapture={endDrag}
      />
    </div>,
    portalTarget,
  );
};
