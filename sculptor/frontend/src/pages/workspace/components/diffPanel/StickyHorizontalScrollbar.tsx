import type { PointerEvent as ReactPointerEvent, ReactElement, RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import styles from "./StickyHorizontalScrollbar.module.scss";

/** How often to re-measure overflow and re-sync scroll state, in milliseconds. */
const POLL_INTERVAL_MS = 500;
/** Smallest thumb width, in pixels, so it stays grabbable on very wide diffs. */
const MIN_THUMB_WIDTH_PX = 30;

type StickyHorizontalScrollbarProps = {
  /** Container element whose descendant diffs-container shadow DOMs hold the [data-code] elements. */
  containerRef: RefObject<HTMLElement | null>;
};

/** Queries all [data-code] elements inside Pierre's shadow DOMs within the container. */
const findCodeElements = (container: HTMLElement): Array<Element> => {
  const elements: Array<Element> = [];
  for (const dc of container.querySelectorAll("diffs-container")) {
    const shadowRoot = dc.shadowRoot;
    if (shadowRoot) {
      elements.push(...shadowRoot.querySelectorAll("[data-code]"));
    }
  }
  return elements;
};

/** Check whether an element is still attached to a document. */
const isConnected = (el: Element): boolean => el.isConnected;

type ScrollState = {
  /** Maximum scrollLeft value across all code elements. */
  maxScrollRange: number;
  /** Current scrollLeft position. */
  scrollLeft: number;
};

/**
 * A custom horizontal scrollbar rendered outside the vertical scroll area,
 * always visible at the bottom of the diff panel. It renders a track and
 * draggable thumb using plain divs (no native scrollbar dependency) and
 * syncs bidirectionally with Pierre's `[data-code]` elements inside the
 * shadow DOM.
 */
export const StickyHorizontalScrollbar = ({ containerRef }: StickyHorizontalScrollbarProps): ReactElement | null => {
  const trackRef = useRef<HTMLDivElement>(null);
  const codeElementsRef = useRef<Array<Element>>([]);
  const isSyncingRef = useRef(false);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartScrollRef = useRef(0);

  // scrollState drives rendering (thumb position/size). We also keep a ref
  // mirror so that pointer-event callbacks can read the latest values without
  // being recreated on every scroll tick (avoids unnecessary re-renders). The
  // refs are read only inside callbacks, never during render, so syncing them
  // in an effect keeps render pure without changing behavior.
  const [scrollState, setScrollState] = useState<ScrollState>({ maxScrollRange: 0, scrollLeft: 0 });
  const scrollStateRef = useRef(scrollState);
  useEffect(() => {
    scrollStateRef.current = scrollState;
  });

  const [trackWidth, setTrackWidth] = useState(0);
  const trackWidthRef = useRef(trackWidth);
  useEffect(() => {
    trackWidthRef.current = trackWidth;
  });

  /**
   * Core polling loop that discovers [data-code] elements inside Pierre's
   * shadow DOM, measures their overflow, and keeps scroll state in sync.
   *
   * Pierre renders asynchronously via web workers, and hunk expansion
   * replaces shadow DOM content with new elements. A simple interval
   * handles both cases reliably without complex observer plumbing.
   */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let scrollCleanup: (() => void) | null = null;

    const rebindListeners = (elements: Array<Element>): void => {
      scrollCleanup?.();
      scrollCleanup = null;
      codeElementsRef.current = elements;

      if (elements.length > 0) {
        const handleCodeScroll = (): void => {
          if (isSyncingRef.current) return;
          const el = elements[0];
          if (!el) return;
          setScrollState((prev) => (prev.scrollLeft === el.scrollLeft ? prev : { ...prev, scrollLeft: el.scrollLeft }));
        };

        for (const el of elements) {
          el.addEventListener("scroll", handleCodeScroll);
        }

        scrollCleanup = (): void => {
          for (const el of elements) {
            el.removeEventListener("scroll", handleCodeScroll);
          }
        };
      }
    };

    const poll = (): void => {
      // Skip state updates while the user is dragging the thumb — the drag
      // handler owns the scroll position during that time.
      if (isDraggingRef.current) return;

      const elements = findCodeElements(container);

      // Detect when elements have been replaced (e.g. hunk expansion replaces
      // shadow DOM content). We check whether the tracked elements are still
      // attached to the document, rather than relying on a fragile identity
      // string that can't distinguish same-count replacements.
      const isStale =
        codeElementsRef.current.length !== elements.length ||
        (codeElementsRef.current.length > 0 && !codeElementsRef.current.every(isConnected));
      if (isStale || (codeElementsRef.current.length === 0 && elements.length > 0)) {
        rebindListeners(elements);
      }

      // Update overflow dimensions.
      if (elements.length === 0) {
        setScrollState((prev) => (prev.maxScrollRange === 0 ? prev : { maxScrollRange: 0, scrollLeft: 0 }));
        return;
      }
      let maxRange = 0;
      let currentScroll = 0;
      for (const el of elements) {
        maxRange = Math.max(maxRange, el.scrollWidth - el.clientWidth);
        currentScroll = el.scrollLeft;
      }
      setScrollState((prev) =>
        prev.maxScrollRange === maxRange && prev.scrollLeft === currentScroll
          ? prev
          : { maxScrollRange: maxRange, scrollLeft: currentScroll },
      );
    };

    // Run immediately, then poll at a low frequency.
    poll();
    const intervalId = setInterval(poll, POLL_INTERVAL_MS);

    return (): void => {
      clearInterval(intervalId);
      scrollCleanup?.();
    };
  }, [containerRef]);

  // Track the track element's own width via ResizeObserver.
  // Re-run when maxScrollRange changes because the track DOM element only
  // exists when maxScrollRange > 0 (the component returns null otherwise).
  const hasOverflow = scrollState.maxScrollRange > 0;
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      setTrackWidth(el.clientWidth);
    });
    observer.observe(el);
    setTrackWidth(el.clientWidth);
    return (): void => {
      observer.disconnect();
    };
  }, [hasOverflow]);

  /** Set scrollLeft on all code elements and update local state. */
  const scrollTo = useCallback(
    (newScrollLeft: number): void => {
      const maxRange = scrollStateRef.current.maxScrollRange;
      const clamped = Math.max(0, Math.min(newScrollLeft, maxRange));
      isSyncingRef.current = true;
      // Always query fresh elements so we never write to stale detached nodes.
      const container = containerRef.current;
      const elements = container ? findCodeElements(container) : codeElementsRef.current;
      for (const el of elements) {
        // Imperative DOM scroll sync across the code panes.
        // eslint-disable-next-line react-hooks/immutability
        el.scrollLeft = clamped;
      }
      setScrollState((prev) => ({ ...prev, scrollLeft: clamped }));
      // Writing scrollLeft above queues a scroll event that fires before the
      // next paint; release the sync guard after it so the code-scroll listener
      // ignores our own programmatic scroll rather than echoing it back.
      requestAnimationFrame(() => {
        isSyncingRef.current = false;
      });
    },
    [containerRef],
  );

  // Click on track to jump to position
  const handleTrackClick = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      const track = trackRef.current;
      const maxRange = scrollStateRef.current.maxScrollRange;
      if (!track || maxRange <= 0) return;
      const rect = track.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const ratio = clickX / rect.width;
      scrollTo(ratio * maxRange);
    },
    [scrollTo],
  );

  // Thumb drag handlers — read from refs so callbacks are stable.
  const handleThumbPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>): void => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartScrollRef.current = scrollStateRef.current.scrollLeft;
  }, []);

  const handleThumbPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>): void => {
      const { maxScrollRange } = scrollStateRef.current;
      const tw = trackWidthRef.current;
      if (!isDraggingRef.current || maxScrollRange <= 0 || tw <= 0) return;
      const deltaX = e.clientX - dragStartXRef.current;
      const thumbW = computeThumbWidth(tw, maxScrollRange);
      const scrollPerPixel = maxScrollRange / (tw - thumbW);
      scrollTo(dragStartScrollRef.current + deltaX * scrollPerPixel);
    },
    [scrollTo],
  );

  const handleThumbPointerUp = useCallback((): void => {
    isDraggingRef.current = false;
  }, []);

  if (scrollState.maxScrollRange <= 0) return null;

  const thumbW = computeThumbWidth(trackWidth, scrollState.maxScrollRange);
  const thumbX =
    trackWidth > thumbW ? (scrollState.scrollLeft / scrollState.maxScrollRange) * (trackWidth - thumbW) : 0;

  return (
    <div ref={trackRef} className={styles.track} onPointerDown={handleTrackClick}>
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

/** Compute thumb width as a fraction of the track, with a minimum size. */
const computeThumbWidth = (trackW: number, maxScrollRange: number): number => {
  if (maxScrollRange <= 0 || trackW <= 0) return 0;
  const fraction = trackW / (trackW + maxScrollRange);
  return Math.max(MIN_THUMB_WIDTH_PX, fraction * trackW);
};
