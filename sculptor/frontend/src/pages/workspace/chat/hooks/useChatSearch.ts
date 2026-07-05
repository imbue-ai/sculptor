import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtom, useAtomValue } from "jotai";
import { useCallback, useEffect, useMemo } from "react";

import type { ChatMessage } from "~/api";
import {
  chatSearchActiveIndexAtom,
  chatSearchQueryAtom,
  chatSearchVisibleAtom,
} from "~/common/state/atoms/chatSearch.ts";

import type { SearchMatch } from "../searchUtils.ts";
import { findMatches } from "../searchUtils.ts";

type UseChatSearchReturn = {
  matches: Array<SearchMatch>;
  activeMatch: SearchMatch | null;
  totalMatchCount: number;
  activeIndex: number;
  navigateToMatch: (index: number) => void;
  isSearchVisible: boolean;
  query: string;
};

export const useChatSearch = (
  filteredMessages: ReadonlyArray<ChatMessage>,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
): UseChatSearchReturn => {
  const isSearchVisible = useAtomValue(chatSearchVisibleAtom);
  const query = useAtomValue(chatSearchQueryAtom);
  const [activeIndex, setActiveIndex] = useAtom(chatSearchActiveIndexAtom);

  // Compute matches — no debounce here because ChatSearchBar already
  // debounces writes to the global query atom. A second debounce layer
  // caused a race where the "no results" indicator in ChatSearchBar
  // fired before matches arrived, producing a brief 0/0 red flash.
  const matches = useMemo(
    () => (isSearchVisible && query ? findMatches(filteredMessages, query) : []),
    [filteredMessages, query, isSearchVisible],
  );

  // Clamp active index
  const clampedIndex = matches.length > 0 ? Math.min(activeIndex, matches.length - 1) : 0;

  // Reset active index when matches change
  useEffect(() => {
    if (activeIndex >= matches.length) {
      setActiveIndex(matches.length > 0 ? matches.length - 1 : 0);
    }
  }, [matches.length, activeIndex, setActiveIndex]);

  const activeMatch = matches.length > 0 ? (matches[clampedIndex] ?? null) : null;

  const navigateToMatch = useCallback(
    (index: number): void => {
      if (matches.length === 0) return;

      // Wrap around
      const wrappedIndex = ((index % matches.length) + matches.length) % matches.length;
      setActiveIndex(wrappedIndex);

      const match = matches[wrappedIndex];
      if (match) {
        // Skip scrolling if the target message is already visible in the viewport.
        // This avoids scroll jumps when cycling between nearby matches.
        const scrollElement = virtualizer.scrollElement;
        if (scrollElement) {
          const scrollOffset = virtualizer.scrollOffset ?? 0;
          const viewportHeight = scrollElement.clientHeight;
          const targetItem = virtualizer.getVirtualItems().find((item) => item.index === match.messageIndex);
          if (targetItem) {
            const isVisible = targetItem.start < scrollOffset + viewportHeight && targetItem.end > scrollOffset;
            if (isVisible) return;
          }
        }

        virtualizer.scrollToIndex(match.messageIndex, { align: "start" });
      }
    },
    [matches, setActiveIndex, virtualizer],
  );

  return {
    matches,
    activeMatch,
    totalMatchCount: matches.length,
    activeIndex: clampedIndex,
    navigateToMatch,
    isSearchVisible,
    query,
  };
};
