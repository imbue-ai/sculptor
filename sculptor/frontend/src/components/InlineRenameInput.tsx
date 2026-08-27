import type { ReactElement } from "react";
import { useEffect, useRef } from "react";

import { ElementIds } from "../api";
import styles from "./InlineRenameInput.module.scss";

type InlineRenameInputProps = {
  value: string;
  onCommit: (newValue: string) => void;
  onCancel: () => void;
  isEditing: boolean;
  className?: string;
};

export const InlineRenameInput = ({
  value,
  onCommit,
  onCancel,
  isEditing,
  className,
}: InlineRenameInputProps): ReactElement | null => {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isEditing || !inputRef.current) {
      return;
    }
    // Focus is taken synchronously: nothing may compete for focus after this runs,
    // or the resulting blur cancels the rename. Every Radix menu/dialog surface
    // that starts a rename therefore suppresses its close-time focus restore
    // (onCloseAutoFocus + preventDefault) — keep that contract when adding a new
    // rename entry point.
    inputRef.current.focus();
    inputRef.current.select();
  }, [isEditing]);

  if (!isEditing) {
    return null;
  }

  const commitOrCancel = (): void => {
    const trimmed = inputRef.current?.value.trim() ?? "";
    if (trimmed && trimmed !== value) {
      onCommit(trimmed);
    } else {
      onCancel();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitOrCancel();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    }
  };

  return (
    <input
      ref={inputRef}
      defaultValue={value}
      onKeyDown={handleKeyDown}
      onBlur={commitOrCancel}
      onClick={(e) => e.stopPropagation()}
      className={`${styles.renameInput} ${className ?? ""}`}
      data-testid={ElementIds.INLINE_RENAME_INPUT}
    />
  );
};
