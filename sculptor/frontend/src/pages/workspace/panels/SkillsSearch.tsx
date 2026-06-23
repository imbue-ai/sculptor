import { IconButton } from "@radix-ui/themes";
import { Search, X } from "lucide-react";
import type { ChangeEvent, KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef } from "react";

import { ElementIds } from "~/api";

import styles from "./SkillsSearch.module.scss";

type SkillsSearchProps = {
  query: string;
  onQueryChange: (query: string) => void;
  onClose: () => void;
  /** Move the panel's keyboard selection. The handlers manage list state in
   * the parent so the selection survives input re-renders and so the
   * caller can scroll the chosen chip into view. */
  onArrowDown?: () => void;
  onArrowUp?: () => void;
  /** Activate the currently-selected chip — typically inserts /skill-name. */
  onEnter?: () => void;
};

export const SkillsSearch = ({
  query,
  onQueryChange,
  onClose,
  onArrowDown,
  onArrowUp,
  onEnter,
}: SkillsSearchProps): ReactElement => {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>): void => {
      if (e.key === "Escape") {
        onClose();
        return;
      }

      // Arrow keys would otherwise jump the input's caret to the start/end
      // of its (single-line) value; we override them to drive list selection.
      if (e.key === "ArrowDown") {
        e.preventDefault();
        onArrowDown?.();
        return;
      }

      if (e.key === "ArrowUp") {
        e.preventDefault();
        onArrowUp?.();
        return;
      }

      if (e.key === "Enter") {
        e.preventDefault();
        onEnter?.();
      }
    },
    [onClose, onArrowDown, onArrowUp, onEnter],
  );

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>): void => {
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
        placeholder="Search skills..."
        data-testid={ElementIds.SKILLS_PANEL_SEARCH_INPUT}
        value={query}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
      />
      <IconButton variant="ghost" size="1" color="gray" className={styles.closeButton} onClick={onClose}>
        <X size={14} />
      </IconButton>
    </div>
  );
};
