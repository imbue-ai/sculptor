import { Flex, IconButton, Text } from "@radix-ui/themes";
import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef } from "react";

import { ElementIds } from "~/api";

import styles from "./InFileSearchBar.module.scss";

type InFileSearchBarProps = {
  query: string;
  onQueryChange: (query: string) => void;
  currentMatch: number;
  totalMatches: number;
  onNextMatch: () => void;
  onPrevMatch: () => void;
  onClose: () => void;
  focusRequest: number;
};

export const InFileSearchBar = ({
  query,
  onQueryChange,
  currentMatch,
  totalMatches,
  onNextMatch,
  onPrevMatch,
  onClose,
  focusRequest,
}: InFileSearchBarProps): ReactElement => {
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus + select on mount, and again whenever focusRequest changes (e.g. user
  // hits the find-in-file shortcut while the bar is already open).
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [focusRequest]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>): void => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (e.shiftKey) {
          onPrevMatch();
        } else {
          onNextMatch();
        }
      }
    },
    [onClose, onNextMatch, onPrevMatch],
  );

  const matchCounter = (): string => {
    if (query === "") return "";
    if (totalMatches === 0) return "No results";
    return `${currentMatch} of ${totalMatches}`;
  };

  return (
    <Flex
      align="center"
      gap="2"
      px="2"
      py="1"
      flexShrink="0"
      className={styles.bar}
      data-testid={ElementIds.DIFF_IN_FILE_SEARCH_BAR}
    >
      <Search size={14} className={styles.icon} />
      <div className={styles.inputWrapper}>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Find in file..."
          className={styles.input}
          data-testid={ElementIds.DIFF_IN_FILE_SEARCH_INPUT}
        />
        <Text size="1" color="gray" className={styles.counter}>
          {matchCounter()}
        </Text>
      </div>
      <IconButton variant="ghost" size="1" color="gray" onClick={onPrevMatch} disabled={totalMatches === 0}>
        <ChevronUp size={14} />
      </IconButton>
      <IconButton variant="ghost" size="1" color="gray" onClick={onNextMatch} disabled={totalMatches === 0}>
        <ChevronDown size={14} />
      </IconButton>
      <IconButton variant="ghost" size="1" color="gray" onClick={onClose}>
        <X size={14} />
      </IconButton>
    </Flex>
  );
};
