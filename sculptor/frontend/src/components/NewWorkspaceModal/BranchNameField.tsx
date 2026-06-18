import { IconButton, Tooltip } from "@radix-ui/themes";
import { GitBranchPlusIcon, ShuffleIcon } from "lucide-react";
import type { KeyboardEvent, ReactElement, Ref } from "react";
import { useEffect, useRef, useState } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy as Strategy } from "~/api";

import styles from "./BranchNameField.module.scss";
import type { BranchNameCollisionState } from "./useBranchNamePreview.ts";

type BranchNameFieldProps = {
  mode: WorkspaceInitializationStrategy;
  /** The displayed value (override-or-preview). */
  value: string;
  /** Whether the user has typed into the field; controls auto-fill and the reset link. */
  isManuallyEdited: boolean;
  /** True while the preview fetch is in flight. */
  isLoading: boolean;
  /** Result of the debounced collision check on `value`. */
  collision: BranchNameCollisionState;
  /** Called whenever the user types into the input. */
  onUserEdit: (value: string) => void;
  /** Called when the user clicks the shuffle button to request a fresh auto-filled name. */
  onReset: () => void;
  disabled?: boolean;
  /** Ref forwarded to the input — used by parent for cross-field nav. */
  inputRef?: Ref<HTMLInputElement>;
  /** Keydown handler attached to the input. */
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void;
  /** Surface a red border on the pill — wired when the field is in an
   *  error state (e.g. required-but-empty). The "required" caption
   *  itself lives outside this component, in the parent's pill row. */
  isError?: boolean;
  /** Validation error message to surface inline, or null when valid.
   *  When non-null the pill is also forced into the error border state. */
  validationError?: string | null;
};

// Inputs accept anything the user types, but git rejects whitespace and
// a handful of reserved characters (`~ ^ : ? * [ \`) in branch names.
// Sanitize on input so a typed " " becomes "-" and `:` / `?` etc. don't
// slip through to fail later at submit time. The `+` quantifier
// collapses runs (e.g. `"foo  bar"` → `"foo-bar"`, not `"foo--bar"`).
// Slash is left alone so users can type multi-segment paths like
// `team/feature/foo`.
const sanitizeBranchName = (value: string): string => value.replace(/[\s~^:?*[\\]+/g, "-");

// Matches Radix's default tooltip hover delay so the controlled-open
// behavior here feels the same as every other tooltip in the app.
const TOOLTIP_HOVER_DELAY_MS = 700;

export const BranchNameField = ({
  mode,
  value,
  isManuallyEdited,
  isLoading,
  collision,
  onUserEdit,
  onReset,
  disabled,
  inputRef,
  onKeyDown,
  isError,
  validationError,
}: BranchNameFieldProps): ReactElement | null => {
  const [isTooltipOpen, setIsTooltipOpen] = useState(false);
  const tooltipTimerRef = useRef<number | undefined>(undefined);

  // Always cancel any in-flight open-after-delay timer when the
  // component unmounts so we don't pop a tooltip onto a torn-down
  // anchor.
  useEffect(() => {
    return (): void => {
      if (tooltipTimerRef.current !== undefined) {
        window.clearTimeout(tooltipTimerRef.current);
      }
    };
  }, []);

  const handlePillMouseEnter = (): void => {
    if (tooltipTimerRef.current !== undefined) {
      window.clearTimeout(tooltipTimerRef.current);
    }
    tooltipTimerRef.current = window.setTimeout(() => {
      setIsTooltipOpen(true);
      tooltipTimerRef.current = undefined;
    }, TOOLTIP_HOVER_DELAY_MS);
  };

  const handlePillMouseLeave = (): void => {
    if (tooltipTimerRef.current !== undefined) {
      window.clearTimeout(tooltipTimerRef.current);
      tooltipTimerRef.current = undefined;
    }
    setIsTooltipOpen(false);
  };

  if (mode === Strategy.IN_PLACE) {
    return null;
  }

  const isWorktree = mode === Strategy.WORKTREE;
  const placeholder = isWorktree ? "branch-name" : "branch-name (optional)";
  const hasValidationError = validationError != null;
  const pillClassName = [
    styles.pill,
    isManuallyEdited ? styles.pillActive : null,
    isError || hasValidationError ? styles.pillError : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={styles.container}>
      <div
        className={pillClassName}
        // Hover anywhere on the pill drives the tooltip's open state,
        // but the Tooltip wrapper itself sits on the icon so the popup
        // anchors (and centers) on it rather than on the much wider
        // input. Keyboard focus deliberately does NOT open the tooltip
        // — once a user is editing, the field's purpose is obvious and
        // a hovering popup just gets in their way.
        onMouseEnter={handlePillMouseEnter}
        onMouseLeave={handlePillMouseLeave}
      >
        <Tooltip content="Workspace branch, can be changed later" side="bottom" open={isTooltipOpen}>
          <span className={styles.icon}>
            <GitBranchPlusIcon size={12} />
          </span>
        </Tooltip>
        <input
          ref={inputRef}
          type="text"
          className={styles.input}
          value={value}
          onChange={(e): void => onUserEdit(sanitizeBranchName(e.target.value))}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          data-testid={ElementIds.BRANCH_NAME_INPUT}
          disabled={disabled}
          aria-label="Branch name"
        />
        {isLoading && !isManuallyEdited ? <span className={styles.spinnerInline}>…</span> : null}
        {/* Always-on "shuffle" button: clears any user override and
            re-fetches a fresh auto-filled name from the backend. Sits
            here regardless of edited state so the user can request a
            new suggestion at any time without having to first dirty
            the field. */}
        <IconButton
          type="button"
          size="1"
          variant="ghost"
          color="gray"
          className={styles.shuffleButton}
          data-testid={ElementIds.BRANCH_NAME_RESET_BUTTON}
          onClick={(e): void => {
            e.preventDefault();
            onReset();
          }}
          disabled={disabled}
          aria-label="Suggest a new branch name"
        >
          <ShuffleIcon size={12} />
        </IconButton>
      </div>
      {/* Always render the error slot so the field's height is stable.
          When there's nothing to say, an `&nbsp;` keeps the line-box
          alive without showing visible text — otherwise the inline
          error would push the modal body downward each time it
          appeared. */}
      {hasValidationError ? (
        <span className={styles.error}>{validationError}</span>
      ) : collision === "exists" ? (
        <span className={styles.error} data-testid={ElementIds.BRANCH_NAME_COLLISION_ERROR}>
          Branch &apos;{value}&apos; already exists
        </span>
      ) : (
        <span className={styles.error} aria-hidden="true">
          &nbsp;
        </span>
      )}
    </div>
  );
};
