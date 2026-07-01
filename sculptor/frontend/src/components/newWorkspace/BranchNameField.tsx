import { IconButton, Link, Tooltip } from "@radix-ui/themes";
import { GitBranchIcon, ShuffleIcon } from "lucide-react";
import type { ReactElement } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy as Strategy } from "~/api";

import styles from "./BranchNameField.module.scss";
import type { BranchNameCollisionState } from "./hooks/useBranchNamePreview.ts";

type BranchNameFieldProps = {
  mode: WorkspaceInitializationStrategy;
  /** The displayed value (override-or-preview). */
  value: string;
  /** Whether the user has typed into the field; controls the reset link. */
  isManuallyEdited: boolean;
  /** True while the preview fetch is in flight. */
  isLoading: boolean;
  /** Result of the debounced collision check on `value`. */
  collision: BranchNameCollisionState;
  /** Latest auto-filled preview, used to decide whether to offer reset. */
  preview: string;
  /** Called whenever the user types into the input (already sanitized). */
  onUserEdit: (value: string) => void;
  /** Called when the user clicks "reset" to return to auto-fill mode. */
  onReset: () => void;
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
 * Strip characters git rejects in branch names as the user types, so the pill
 * only ever shows a name the create call can accept. Mirrors git's ref rules:
 * whitespace collapses to a hyphen; the reserved ref characters are dropped;
 * runs of dots collapse and a leading dot is removed (git forbids ".." and a
 * leading ".").
 */
const sanitizeBranchName = (raw: string): string =>
  raw
    .replace(/\s+/g, "-")
    .replace(/[~^:?*[\]\\@{} ]/g, "")
    .replace(/\.{2,}/g, ".")
    .replace(/^\.+/, "");

/**
 * The branch-name field: a monospace pill with input sanitization, a shuffle
 * button to re-roll the auto-filled name, and a STABLE error slot that is always
 * rendered (an empty fixed-height row when there is nothing to show) so the
 * dialog never jumps as the collision state changes.
 */
export const BranchNameField = ({
  mode,
  value,
  isManuallyEdited,
  isLoading,
  collision,
  preview,
  onUserEdit,
  onReset,
  onShuffle,
  disabled,
  variant = "chip",
}: BranchNameFieldProps): ReactElement | undefined => {
  // In-place workspaces use the current branch, so there is no field to render.
  if (mode === Strategy.IN_PLACE) {
    return undefined;
  }

  const placeholder = mode === Strategy.WORKTREE ? "Branch name (required)" : "Branch name (optional)";
  const hasCollision = collision === "exists";
  const canReset = isManuallyEdited && preview !== value;
  const isPlain = variant === "plain";

  return (
    <div className={styles.container} data-testid={ElementIds.NEW_WORKSPACE_CONTEXT_PILL}>
      <div className={`${styles.pill} ${isPlain ? styles.pillPlain : ""} ${hasCollision ? styles.pillError : ""}`}>
        {isPlain ? null : (
          <span className={styles.prefix}>
            <GitBranchIcon size={12} />
          </span>
        )}
        <input
          type="text"
          className={styles.input}
          value={value}
          onChange={(e): void => onUserEdit(sanitizeBranchName(e.target.value))}
          placeholder={placeholder}
          data-testid={ElementIds.BRANCH_NAME_INPUT}
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
        />
        {isLoading && !isManuallyEdited ? <span className={styles.spinner}>…</span> : null}
        {canReset ? (
          <Link
            href="#"
            size="1"
            data-testid={ElementIds.BRANCH_NAME_RESET_BUTTON}
            onClick={(e): void => {
              e.preventDefault();
              onReset();
            }}
          >
            reset
          </Link>
        ) : null}
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
            <ShuffleIcon size={12} />
          </IconButton>
        </Tooltip>
      </div>
      {/* Error rendered only when present, so an error-free field is the same
          height as the breadcrumb chips (no always-reserved empty slot). */}
      {hasCollision ? (
        <div className={styles.errorSlot}>
          <span className={styles.error} data-testid={ElementIds.BRANCH_NAME_COLLISION_ERROR}>
            Branch &apos;{value}&apos; already exists
          </span>
        </div>
      ) : null}
    </div>
  );
};
