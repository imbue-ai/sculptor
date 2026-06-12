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
    if (isEditing && inputRef.current) {
      // Defer focus to the next animation frame so it runs after Radix UI's
      // ContextMenu restores focus to the trigger element on close.
      requestAnimationFrame(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      });
    }
  }, [isEditing]);

  if (!isEditing) {
    return null;
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter") {
      e.preventDefault();
      const trimmed = inputRef.current?.value.trim() ?? "";
      if (trimmed && trimmed !== value) {
        onCommit(trimmed);
      } else {
        onCancel();
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    }
  };

  const handleBlur = (): void => {
    const trimmed = inputRef.current?.value.trim() ?? "";
    if (trimmed && trimmed !== value) {
      onCommit(trimmed);
    } else {
      onCancel();
    }
  };

  return (
    <input
      ref={inputRef}
      defaultValue={value}
      onKeyDown={handleKeyDown}
      onBlur={handleBlur}
      onClick={(e) => e.stopPropagation()}
      className={`${styles.renameInput} ${className ?? ""}`}
      data-testid={ElementIds.INLINE_RENAME_INPUT}
    />
  );
};
