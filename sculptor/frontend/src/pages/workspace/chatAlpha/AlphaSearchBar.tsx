import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef } from "react";

import { chatSearchFocusRequestAtom, chatSearchVisibleAtom } from "~/common/state/atoms/chatSearch.ts";

import { ChatSearchBar } from "./ChatSearchBar.tsx";

type AlphaSearchBarProps = {
  totalMatchCount: number;
  activeIndex: number;
  navigateToMatch: (index: number) => void;
};

export const AlphaSearchBar = ({
  totalMatchCount,
  activeIndex,
  navigateToMatch,
}: AlphaSearchBarProps): ReactElement => {
  const setSearchVisible = useSetAtom(chatSearchVisibleAtom);
  const inputRef = useRef<HTMLInputElement>(null);
  const focusRequest = useAtomValue(chatSearchFocusRequestAtom);

  const handleClose = useCallback((): void => {
    setSearchVisible(false);
  }, [setSearchVisible]);

  const handleNext = useCallback((): void => {
    navigateToMatch(activeIndex + 1);
  }, [navigateToMatch, activeIndex]);

  const handlePrev = useCallback((): void => {
    navigateToMatch(activeIndex - 1);
  }, [navigateToMatch, activeIndex]);

  // Focus input on mount and on focus requests
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [focusRequest]);

  return (
    <ChatSearchBar
      totalMatchCount={totalMatchCount}
      activeIndex={activeIndex}
      onNext={handleNext}
      onPrev={handlePrev}
      onClose={handleClose}
      inputRef={inputRef}
    />
  );
};
