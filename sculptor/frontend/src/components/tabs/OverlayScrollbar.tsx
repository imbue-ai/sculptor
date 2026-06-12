import type { PointerEvent as ReactPointerEvent, ReactElement, RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import styles from "./OverlayScrollbar.module.scss";

const MIN_THUMB_WIDTH = 30;

type OverlayScrollbarProps = {
  /** Ref to the scrollable container element. */
  scrollRef: RefObject<HTMLElement | null>;
  /** Extra class name applied to the track element, for parent hover rules. */
  className?: string;
};

type ScrollMetrics = {
  scrollLeft: number;
  scrollWidth: number;
  clientWidth: number;
};

/** Compute thumb width as a fraction of the track, with a minimum size. */
const computeThumbWidth = (trackWidth: number, metrics: ScrollMetrics): number => {
  if (metrics.scrollWidth <= metrics.clientWidth || trackWidth <= 0) return 0;
  const fraction = metrics.clientWidth / metrics.scrollWidth;
  return Math.max(MIN_THUMB_WIDTH, fraction * trackWidth);
};

/**
 * A thin horizontal scrollbar that renders on top of content via absolute
 * positioning, without reserving any layout space. Syncs with the scroll
 * position of the referenced container.
 */
export const OverlayScrollbar = ({ scrollRef, className }: OverlayScrollbarProps): ReactElement | null => {
  const trackRef = useRef<HTMLDivElement>(null);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartScrollRef = useRef(0);

  const [metrics, setMetrics] = useState<ScrollMetrics>({ scrollLeft: 0, scrollWidth: 0, clientWidth: 0 });
  const metricsRef = useRef(metrics);
  metricsRef.current = metrics;

  const [trackWidth, setTrackWidth] = useState(0);
  const trackWidthRef = useRef(trackWidth);
  trackWidthRef.current = trackWidth;

  // Sync scroll metrics from the container.
  useEffect((): (() => void) | void => {
    const el = scrollRef.current;
    if (!el) return;

    const update = (): void => {
      setMetrics((prev) => {
        const next: ScrollMetrics = {
          scrollLeft: el.scrollLeft,
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        };
        if (
          prev.scrollLeft === next.scrollLeft &&
          prev.scrollWidth === next.scrollWidth &&
          prev.clientWidth === next.clientWidth
        ) {
          return prev;
        }
        return next;
      });
    };

    update();
    el.addEventListener("scroll", update, { passive: true });

    const observer = new ResizeObserver(update);
    observer.observe(el);

    // Also observe children changes (tabs added/removed).
    const mutationObserver = new MutationObserver(update);
    mutationObserver.observe(el, { childList: true });

    return (): void => {
      el.removeEventListener("scroll", update);
      observer.disconnect();
      mutationObserver.disconnect();
    };
  }, [scrollRef]);

  // Track width via ResizeObserver.
  const hasOverflow = metrics.scrollWidth > metrics.clientWidth;
  useEffect((): (() => void) | void => {
    const el = trackRef.current;
    if (!el) return;
    const observer = new ResizeObserver((): void => {
      setTrackWidth(el.clientWidth);
    });
    observer.observe(el);
    setTrackWidth(el.clientWidth);
    return (): void => {
      observer.disconnect();
    };
  }, [hasOverflow]);

  /** Scroll the container to an absolute position. */
  const scrollTo = useCallback(
    (scrollLeft: number): void => {
      const el = scrollRef.current;
      if (!el) return;
      const maxScroll = el.scrollWidth - el.clientWidth;
      el.scrollLeft = Math.max(0, Math.min(scrollLeft, maxScroll));
    },
    [scrollRef],
  );

  const handleTrackClick = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      const track = trackRef.current;
      const el = scrollRef.current;
      if (!track || !el) return;
      const maxScroll = el.scrollWidth - el.clientWidth;
      if (maxScroll <= 0) return;
      const rect = track.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      scrollTo(ratio * maxScroll);
    },
    [scrollRef, scrollTo],
  );

  const handleThumbPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      e.stopPropagation();
      e.currentTarget.setPointerCapture(e.pointerId);
      isDraggingRef.current = true;
      dragStartXRef.current = e.clientX;
      dragStartScrollRef.current = scrollRef.current?.scrollLeft ?? 0;
    },
    [scrollRef],
  );

  const handleThumbPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      if (!isDraggingRef.current) return;
      const el = scrollRef.current;
      if (!el) return;
      const maxScroll = el.scrollWidth - el.clientWidth;
      const tw = trackWidthRef.current;
      if (maxScroll <= 0 || tw <= 0) return;
      const thumbW = computeThumbWidth(tw, metricsRef.current);
      const scrollPerPixel = maxScroll / (tw - thumbW);
      const deltaX = e.clientX - dragStartXRef.current;
      scrollTo(dragStartScrollRef.current + deltaX * scrollPerPixel);
    },
    [scrollRef, scrollTo],
  );

  const handleThumbPointerUp = useCallback((): void => {
    isDraggingRef.current = false;
  }, []);

  if (!hasOverflow) return null;

  const thumbW = computeThumbWidth(trackWidth, metrics);
  const maxScroll = metrics.scrollWidth - metrics.clientWidth;
  const thumbX = maxScroll > 0 && trackWidth > thumbW ? (metrics.scrollLeft / maxScroll) * (trackWidth - thumbW) : 0;

  return (
    <div ref={trackRef} className={`${styles.track} ${className ?? ""}`} onPointerDown={handleTrackClick}>
      <div
        className={styles.thumb}
        style={{ width: thumbW, transform: `translateX(${thumbX}px)` }}
        onPointerDown={handleThumbPointerDown}
        onPointerMove={handleThumbPointerMove}
        onPointerUp={handleThumbPointerUp}
        onLostPointerCapture={handleThumbPointerUp}
      />
    </div>
  );
};
