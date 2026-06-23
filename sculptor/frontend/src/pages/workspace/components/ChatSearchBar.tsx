import { Cross1Icon } from "@radix-ui/react-icons";
import { useSetAtom } from "jotai";
import type { KeyboardEvent, ReactElement, RefObject } from "react";
import { useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { chatSearchQueryAtom } from "~/common/state/atoms/chatSearch";

import styles from "./ChatSearchBar.module.scss";

const SEARCH_DEBOUNCE_MS = 150;
const NO_RESULTS_DELAY_MS = 350;

type ChatSearchBarProps = {
  totalMatchCount: number;
  activeIndex: number;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
  inputRef: RefObject<HTMLInputElement | null>;
};

export const ChatSearchBar = ({
  totalMatchCount,
  activeIndex,
  onNext,
  onPrev,
  onClose,
  inputRef,
}: ChatSearchBarProps): ReactElement => {
  const setGlobalQuery = useSetAtom(chatSearchQueryAtom);
  const [localQuery, setLocalQuery] = useState("");
  const [isNoResultsVisible, setIsNoResultsVisible] = useState(false);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const noResultsTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Debounce writes to the global query atom
  useEffect(() => {
    clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      setGlobalQuery(localQuery);
    }, SEARCH_DEBOUNCE_MS);

    return (): void => clearTimeout(debounceTimerRef.current);
  }, [localQuery, setGlobalQuery]);

  // Clear the global search query when the search bar closes (unmounts) so
  // highlights are removed and a fresh mount starts with an empty query.
  useEffect(() => {
    return (): void => {
      setGlobalQuery("");
    };
  }, [setGlobalQuery]);

  // Delay the "no results" indicator so it doesn't flash while the search
  // pipeline (debounce → global query → highlight rebuild → domMatchCount)
  // is still settling. Each keystroke resets the timer so the red state only
  // appears after the user stops typing AND the search has had time to run.
  // Clear immediately when results are found.
  const hasQuery = localQuery !== "";
  const hasStaleNoResults = hasQuery && totalMatchCount === 0;

  // Clear the indicator the instant the no-results condition lifts (results
  // appear or the query clears). Adjusting during render with a prev-value
  // guard keeps the reset out of the effect, and re-arms the debounce so the
  // red state must be earned again next time the condition recurs.
  const [prevStaleNoResults, setPrevStaleNoResults] = useState({ value: hasStaleNoResults });
  if (hasStaleNoResults !== prevStaleNoResults.value) {
    setPrevStaleNoResults({ value: hasStaleNoResults });
    if (!hasStaleNoResults) {
      setIsNoResultsVisible(false);
    }
  }

  useEffect(() => {
    clearTimeout(noResultsTimerRef.current);
    if (!hasStaleNoResults) {
      return;
    }
    // Wait longer than the search debounce so the highlight rebuild has time
    // to complete before committing to the "no results" state.
    noResultsTimerRef.current = setTimeout(() => {
      setIsNoResultsVisible(true);
    }, NO_RESULTS_DELAY_MS);

    return (): void => clearTimeout(noResultsTimerRef.current);
  }, [hasStaleNoResults, localQuery]);

  const hasNoResults = isNoResultsVisible;
  const areControlsVisible = hasQuery;

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      // Flush debounce immediately on navigation
      clearTimeout(debounceTimerRef.current);
      setGlobalQuery(localQuery);
      onPrev();
    } else if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(debounceTimerRef.current);
      setGlobalQuery(localQuery);
      onNext();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  const counterText = hasQuery && totalMatchCount > 0 ? `${activeIndex + 1}/${totalMatchCount}` : "0/0";

  return (
    <div
      role="search"
      aria-label="Find in conversation"
      className={styles.searchBar}
      data-testid={ElementIds.CHAT_SEARCH_BAR}
    >
      <span className={styles.searchIcon} aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="7" cy="7" r="4.5" />
          <path d="M10.5 10.5L14 14" />
        </svg>
      </span>

      <input
        ref={inputRef}
        type="text"
        className={`${styles.searchInput} ${hasNoResults ? styles.searchInputNoResults : ""}`}
        value={localQuery}
        onChange={(e): void => setLocalQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Find in conversation..."
        aria-label="Search conversation"
        data-testid={ElementIds.CHAT_SEARCH_INPUT}
      />

      <span
        className={`${styles.searchCount} ${hasNoResults ? styles.searchCountNoResults : ""}`}
        style={{ visibility: areControlsVisible ? "visible" : "hidden" }}
        aria-live="polite"
        aria-atomic="true"
        data-testid={ElementIds.CHAT_SEARCH_MATCH_COUNTER}
      >
        {counterText}
      </span>

      <div className={styles.searchNavGroup} style={{ visibility: areControlsVisible ? "visible" : "hidden" }}>
        <button
          type="button"
          className={styles.searchNavBtn}
          onClick={onPrev}
          disabled={totalMatchCount === 0}
          aria-label="Previous match (Shift+Enter)"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M8 3v10M4 7l4-4 4 4" />
          </svg>
        </button>
        <button
          type="button"
          className={styles.searchNavBtn}
          onClick={onNext}
          disabled={totalMatchCount === 0}
          aria-label="Next match (Enter)"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M8 3v10M4 9l4 4 4-4" />
          </svg>
        </button>
      </div>

      <button type="button" className={styles.searchClose} onClick={onClose} aria-label="Close search (Escape)">
        <Cross1Icon width={14} height={14} />
      </button>
    </div>
  );
};
