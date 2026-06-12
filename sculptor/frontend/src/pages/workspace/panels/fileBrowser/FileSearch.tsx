import { IconButton } from "@radix-ui/themes";
import { Search, X } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef } from "react";

import { ElementIds } from "~/api";

import styles from "./FileSearch.module.scss";

type FileSearchProps = {
  query: string;
  onQueryChange: (query: string) => void;
  onClose: () => void;
  resultCount: number;
};

export const FileSearch = ({ query, onQueryChange, onClose, resultCount }: FileSearchProps): ReactElement => {
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-focus on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>): void => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>): void => {
      onQueryChange(e.target.value);
    },
    [onQueryChange],
  );

  return (
    <div className={styles.container}>
      <Search size={14} className={styles.icon} />
      <input
        ref={inputRef}
        type="text"
        className={styles.input}
        placeholder="Search files..."
        value={query}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        data-testid={ElementIds.FILE_BROWSER_SEARCH_INPUT}
      />
      {query.length > 0 && <span className={styles.resultCount}>{resultCount} found</span>}
      <IconButton
        variant="ghost"
        size="1"
        color="gray"
        className={styles.closeButton}
        onClick={onClose}
        data-testid={ElementIds.FILE_BROWSER_SEARCH_CLOSE}
      >
        <X size={14} />
      </IconButton>
    </div>
  );
};
