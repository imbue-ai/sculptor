import { IconButton, Skeleton, Tooltip } from "@radix-ui/themes";
import { GitBranchIcon, SparklesIcon } from "lucide-react";
import type { ReactElement } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy as Strategy } from "~/api";

import styles from "./BranchNameField.module.scss";
import type { BranchNameStatus } from "./hooks/useBranchNamePreview.ts";
import { sanitizeBranchName } from "./sanitizeBranchName.ts";

type BranchNameFieldProps = {
  mode: WorkspaceInitializationStrategy;
  /** The displayed value (override-or-preview). */
  value: string;
  /** Whether the user has typed into the field; distinguishes auto-fill from manual entry. */
  isManuallyEdited: boolean;
  /** True while the preview fetch is in flight. */
  isLoading: boolean;
  /** Result of the debounced branch-name validation on `value`. */
  status: BranchNameStatus;
  /** Called whenever the user types into the input (already sanitized). */
  onUserEdit: (value: string) => void;
  /** Called when the user clicks the shuffle button to re-roll the name. */
  onShuffle: () => void;
  disabled?: boolean;
  /**
   * Visual style. "chip" (default) is the bordered pill used in the breadcrumb
   * row. "plain" is a borderless, iconless variant that reads as an editable
   * subtitle — used directly under the workspace title.
   */
  variant?: "chip" | "plain";
};

/**
 * The branch-name field: a monospace pill with input sanitization, a shuffle
 * button to re-roll the auto-filled name, a skeleton that stands in for the input
 * on a cold open, and an error row rendered only when a name is invalid or
 * clashes with an existing branch.
 */
export const BranchNameField = ({
  mode,
  value,
  isManuallyEdited,
  isLoading,
  status,
  onUserEdit,
  onShuffle,
  disabled,
  variant = "chip",
}: BranchNameFieldProps): ReactElement | undefined => {
  // In-place workspaces use the current branch, so there is no field to render.
  if (mode === Strategy.IN_PLACE) {
    return undefined;
  }

  const placeholder = mode === Strategy.WORKTREE ? "Branch name (required)" : "Branch name (optional)";
  // The as-you-type sanitizer keeps most illegal characters out of `value`, so
  // "invalid" only fires on the residue it deliberately lets through (trailing
  // '.' or '/', a '.lock' suffix) — see sanitizeBranchName.ts.
  const isInvalid = status === "invalid";
  const hasCollision = status === "exists";
  const hasError = isInvalid || hasCollision;
  const isPlain = variant === "plain";
  // The sparkles glyph doubles as the loading affordance: it pulses while a
  // fresh auto-filled name is being generated (there is no separate spinner).
  const isGenerating = isLoading && !isManuallyEdited;
  // On a cold open there is no name yet, so the empty input would flash its
  // placeholder while the first auto-filled name is fetched. Show a skeleton in
  // its place instead. Once a name exists (re-roll/edit), the field stays put and
  // the pulsing sparkle carries the loading state.
  const isColdLoading = isLoading && !isManuallyEdited && value.trim() === "";
  // The plain variant hugs its content so the shuffle button trails the branch
  // text instead of floating at the end of a full-width row. The input is
  // monospace, so 1ch maps to one glyph: size it to the value (or the
  // placeholder while empty) with a 4ch floor, plus 1ch for the caret. Done in
  // JS rather than CSS `field-sizing`, which Chromium supports but Firefox and
  // Safari (the web build) don't. The chip variant flexes to fill its row and
  // takes no explicit width.
  const plainInputWidth = isPlain ? `${Math.max(value.length || placeholder.length, 4) + 1}ch` : undefined;

  return (
    <div className={styles.container} data-testid={ElementIds.NEW_WORKSPACE_CONTEXT_PILL}>
      <div className={`${styles.pill} ${isPlain ? styles.pillPlain : ""} ${hasError ? styles.pillError : ""}`}>
        {isPlain ? null : (
          <span className={styles.prefix}>
            <GitBranchIcon size={12} />
          </span>
        )}
        {isColdLoading ? (
          <Skeleton className={styles.fieldSkeleton} />
        ) : (
          <input
            type="text"
            className={styles.input}
            style={{ width: plainInputWidth }}
            value={value}
            onChange={(e): void => onUserEdit(sanitizeBranchName(e.target.value))}
            placeholder={placeholder}
            data-testid={ElementIds.BRANCH_NAME_INPUT}
            disabled={disabled}
            spellCheck={false}
            autoComplete="off"
          />
        )}
        <Tooltip content="Shuffle branch name">
          <IconButton
            type="button"
            variant="ghost"
            size="1"
            className={styles.shuffleButton}
            aria-label="Shuffle branch name"
            data-testid={ElementIds.BRANCH_NAME_SHUFFLE_BUTTON}
            disabled={disabled}
            onClick={onShuffle}
          >
            <SparklesIcon size={12} className={isGenerating ? styles.sparkleLoading : undefined} />
          </IconButton>
        </Tooltip>
      </div>
      {/* Error rendered only when present, so an error-free field is the same
          height as the breadcrumb chips (no always-reserved empty slot). */}
      {hasError ? (
        <div className={styles.errorSlot}>
          {isInvalid ? (
            <span className={styles.error} data-testid={ElementIds.BRANCH_NAME_INVALID_ERROR}>
              &apos;{value}&apos; is not a valid branch name
            </span>
          ) : (
            <span className={styles.error} data-testid={ElementIds.BRANCH_NAME_COLLISION_ERROR}>
              Branch &apos;{value}&apos; already exists
            </span>
          )}
        </div>
      ) : null}
    </div>
  );
};
