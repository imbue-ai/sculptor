import { SearchIcon } from "lucide-react";
import type { ReactElement, RefObject } from "react";

import { ElementIds } from "../../../api";
import styles from "./WorkspaceSearchBar.module.scss";

type WorkspaceSearchBarProps = {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  inputRef: RefObject<HTMLInputElement>;
  autoFocus?: boolean;
  onEscape: () => void;
};

export const WorkspaceSearchBar = ({
  searchQuery,
  onSearchChange,
  inputRef,
  autoFocus,
  onEscape,
}: WorkspaceSearchBarProps): ReactElement => {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Escape") {
      e.preventDefault();
      onEscape();
    }
  };

  return (
    <div className={styles.container}>
      <SearchIcon size={14} className={styles.searchIcon} />
      <input
        ref={inputRef}
        type="text"
        value={searchQuery}
        onChange={(e): void => onSearchChange(e.target.value)}
        onKeyDown={handleKeyDown}
        autoFocus={autoFocus}
        placeholder="Search workspaces..."
        className={styles.input}
        data-testid={ElementIds.WORKSPACE_SEARCH_INPUT}
      />
    </div>
  );
};
