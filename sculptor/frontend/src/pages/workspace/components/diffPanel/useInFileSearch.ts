import type { RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { findScrollableChild } from "./useScrollPreservation.ts";

const IN_FILE_SEARCH_ALL = "in-file-search-all";
const IN_FILE_SEARCH_CURRENT = "in-file-search-current";
const MUTATION_DEBOUNCE_MS = 150;
const SCROLL_PADDING_PX = 100;

type UseInFileSearchParams = {
  diffContentRef: RefObject<HTMLElement | null>;
  query: string;
  isActive: boolean;
  /** Active file path — triggers a search rebuild when the user switches tabs. */
  activeFilePath: string | null;
};

type UseInFileSearchResult = {
  currentMatch: number;
  totalMatches: number;
  goToNextMatch: () => void;
  goToPrevMatch: () => void;
  clearHighlights: () => void;
};

/**
 * Walk the DOM tree (including shadow roots) to find text nodes containing
 * searchable diff content. Only text inside Pierre's code containers is
 * collected — this excludes line-number gutters, hunk separators, expand
 * buttons, and any other diff chrome. @pierre/diffs 1.2 marks them with
 * `data-code` (1.0 used `data-column-content`; both are accepted).
 */
const collectTextNodes = (root: Node): Array<Text> => {
  const textNodes: Array<Text> = [];

  const walk = (node: Node, insideContent: boolean): void => {
    if (node.nodeType === Node.TEXT_NODE) {
      if (insideContent) {
        textNodes.push(node as Text);
      }
      return;
    }

    const isContentColumn =
      node instanceof HTMLElement && (node.hasAttribute("data-code") || node.hasAttribute("data-column-content"));

    // Traverse into shadow root if available
    if (node instanceof HTMLElement && node.shadowRoot) {
      walk(node.shadowRoot, insideContent || isContentColumn);
    }

    let child = node.firstChild;
    while (child) {
      walk(child, insideContent || isContentColumn);
      child = child.nextSibling;
    }
  };

  walk(root, false);
  return textNodes;
};

/**
 * Build Range objects for all occurrences of `query` in text nodes.
 * Case-insensitive search.
 */
const buildHighlightRanges = (textNodes: Array<Text>, query: string): Array<Range> => {
  const lowerQuery = query.toLowerCase();
  const queryLength = query.length;
  const ranges: Array<Range> = [];

  for (const textNode of textNodes) {
    const text = textNode.textContent;
    if (!text) continue;

    const lowerText = text.toLowerCase();
    let pos = 0;
    while (true) {
      const idx = lowerText.indexOf(lowerQuery, pos);
      if (idx === -1) break;

      const range = document.createRange();
      range.setStart(textNode, idx);
      range.setEnd(textNode, idx + queryLength);
      ranges.push(range);
      pos = idx + 1;
    }
  }

  return ranges;
};

/**
 * Scroll a range into view within the diff content container.
 * The container itself has `overflow: hidden`; the actual scrollable element
 * is a child rendered by Pierre, so we locate it first.
 */
const scrollRangeIntoView = (range: Range, container: HTMLElement): void => {
  const scrollable = findScrollableChild(container) ?? container;
  const rangeRect = range.getBoundingClientRect();
  const scrollableRect = scrollable.getBoundingClientRect();

  const isVisible =
    rangeRect.top >= scrollableRect.top + SCROLL_PADDING_PX &&
    rangeRect.bottom <= scrollableRect.bottom - SCROLL_PADDING_PX;

  if (!isVisible) {
    const offsetFromTop = rangeRect.top - scrollableRect.top;
    scrollable.scrollBy({ top: offsetFromTop - SCROLL_PADDING_PX, behavior: "smooth" });
  }
};

export const useInFileSearch = ({
  diffContentRef,
  query,
  isActive,
  activeFilePath,
}: UseInFileSearchParams): UseInFileSearchResult => {
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);
  const [totalMatches, setTotalMatches] = useState(0);
  const rangesRef = useRef<Array<Range>>([]);
  const [domVersion, setDomVersion] = useState(0);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const clearHighlights = useCallback((): void => {
    CSS.highlights?.delete(IN_FILE_SEARCH_ALL);
    CSS.highlights?.delete(IN_FILE_SEARCH_CURRENT);
    rangesRef.current = [];
    setTotalMatches(0);
    setCurrentMatchIndex(0);
  }, []);

  // Watch for DOM mutations (Pierre re-rendering, hunk expand/collapse).
  // Pierre fills its `<diffs-container>` shadow root asynchronously from a
  // web worker, and shadow-DOM mutations are invisible to a light-DOM
  // observer on the host. Attach an observer to every shadow root we find
  // so a worker-driven render still triggers a rebuild.
  useEffect(() => {
    const container = diffContentRef.current;
    if (!isActive || query === "" || !container) return;

    const observers: Array<MutationObserver> = [];
    const observedRoots = new Set<Node>();

    const scheduleRebuild = (): void => {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(() => {
        setDomVersion((v) => v + 1);
      }, MUTATION_DEBOUNCE_MS);
    };

    const attachObserver = (root: Node): void => {
      if (observedRoots.has(root)) return;
      observedRoots.add(root);
      const observer = new MutationObserver(() => {
        // A mutation may have added new shadow hosts — re-scan before rebuilding.
        walkAndAttach(container);
        scheduleRebuild();
      });
      observer.observe(root, { childList: true, subtree: true });
      observers.push(observer);
    };

    const walkAndAttach = (node: Node): void => {
      if (node instanceof HTMLElement && node.shadowRoot) {
        attachObserver(node.shadowRoot);
        let shadowChild = node.shadowRoot.firstChild;
        while (shadowChild) {
          walkAndAttach(shadowChild);
          shadowChild = shadowChild.nextSibling;
        }
      }
      let child = node.firstChild;
      while (child) {
        walkAndAttach(child);
        child = child.nextSibling;
      }
    };

    attachObserver(container);
    walkAndAttach(container);

    return (): void => {
      for (const observer of observers) observer.disconnect();
      clearTimeout(debounceTimerRef.current);
    };
  }, [diffContentRef, isActive, query]);

  // Rebuild highlights when query, DOM, or active state changes
  useEffect(() => {
    if (!isActive || query === "" || !diffContentRef.current || !("highlights" in CSS)) {
      clearHighlights();
      return;
    }

    const container = diffContentRef.current;
    const textNodes = collectTextNodes(container);
    const ranges = buildHighlightRanges(textNodes, query);
    rangesRef.current = ranges;
    setTotalMatches(ranges.length);

    if (ranges.length > 0) {
      CSS.highlights.set(IN_FILE_SEARCH_ALL, new Highlight(...ranges));
      const newIndex = 0;
      setCurrentMatchIndex(newIndex);
      CSS.highlights.set(IN_FILE_SEARCH_CURRENT, new Highlight(ranges[newIndex]));
      scrollRangeIntoView(ranges[newIndex], container);
    } else {
      CSS.highlights.delete(IN_FILE_SEARCH_ALL);
      CSS.highlights.delete(IN_FILE_SEARCH_CURRENT);
      setCurrentMatchIndex(0);
    }

    return (): void => {
      CSS.highlights?.delete(IN_FILE_SEARCH_ALL);
      CSS.highlights?.delete(IN_FILE_SEARCH_CURRENT);
    };
  }, [isActive, query, diffContentRef, domVersion, clearHighlights, activeFilePath]);

  /** Highlight and scroll to the match at the given index. */
  const activateMatch = useCallback(
    (index: number): void => {
      const ranges = rangesRef.current;
      if ("highlights" in CSS && ranges[index]) {
        CSS.highlights.set(IN_FILE_SEARCH_CURRENT, new Highlight(ranges[index]));
      }
      const container = diffContentRef.current;
      if (container && ranges[index]) {
        scrollRangeIntoView(ranges[index], container);
      }
    },
    [diffContentRef],
  );

  const goToNextMatch = useCallback((): void => {
    const ranges = rangesRef.current;
    if (ranges.length === 0) return;
    setCurrentMatchIndex((prev) => {
      const next = (prev + 1) % ranges.length;
      // Schedule side effects after the state update (outside the updater).
      queueMicrotask(() => activateMatch(next));
      return next;
    });
  }, [activateMatch]);

  const goToPrevMatch = useCallback((): void => {
    const ranges = rangesRef.current;
    if (ranges.length === 0) return;
    setCurrentMatchIndex((prev) => {
      const next = (prev - 1 + ranges.length) % ranges.length;
      queueMicrotask(() => activateMatch(next));
      return next;
    });
  }, [activateMatch]);

  return {
    currentMatch: totalMatches > 0 ? currentMatchIndex + 1 : 0,
    totalMatches,
    goToNextMatch,
    goToPrevMatch,
    clearHighlights,
  };
};
