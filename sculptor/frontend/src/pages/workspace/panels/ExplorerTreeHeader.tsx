import { Search } from "lucide-react";
import type { ChangeEvent, ReactElement } from "react";
import { useCallback } from "react";

import { ElementIds } from "~/api";

import styles from "./ExplorerTreeHeader.module.scss";

type ExplorerTreeHeaderProps = {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  placeholder?: string;
};

/**
 * The 41px list (sidebar) header shared by the Files / Changes / Commits panels:
 * a single search box whose height matches the viewer header so the two line up.
 * The list/tree view-options do not live here — they are merged into the
 * viewer's triple-dot menu. Panels whose list has no search (Commits)
 * simply do not render this header.
 */
export const ExplorerTreeHeader = ({
  searchQuery,
  onSearchChange,
  placeholder = "Search files…",
}: ExplorerTreeHeaderProps): ReactElement => {
  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>): void => {
      onSearchChange(e.target.value);
    },
    [onSearchChange],
  );

  return (
    <div className={styles.header}>
      <div className={styles.search}>
        <Search size={14} className={styles.searchIcon} />
        <input
          type="text"
          className={styles.searchInput}
          placeholder={placeholder}
          value={searchQuery}
          onChange={handleChange}
          data-testid={ElementIds.FILE_BROWSER_SEARCH_INPUT}
        />
      </div>
    </div>
  );
};
