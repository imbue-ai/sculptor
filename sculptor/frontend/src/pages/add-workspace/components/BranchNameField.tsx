import { Link } from "@radix-ui/themes";
import { GitBranchIcon } from "lucide-react";
import type { ReactElement } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy as Strategy } from "~/api";

import type { BranchNameCollisionState } from "../hooks/useBranchNamePreview";
import styles from "./BranchNameField.module.scss";

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
  /** Latest auto-filled preview, used by `onReset`. */
  preview: string;
  /** Called whenever the user types into the input. */
  onUserEdit: (value: string) => void;
  /** Called when the user clicks the "reset" link to return to auto-fill mode. */
  onReset: () => void;
  disabled?: boolean;
};

export const BranchNameField = ({
  mode,
  value,
  isManuallyEdited,
  isLoading,
  collision,
  preview,
  onUserEdit,
  onReset,
  disabled,
}: BranchNameFieldProps): ReactElement | undefined => {
  if (mode === Strategy.IN_PLACE) {
    return undefined;
  }

  const shouldShowRequiredHint = mode === Strategy.WORKTREE && value.trim() === "";
  const placeholder = mode === Strategy.WORKTREE ? "Branch name (required)" : "Branch name (optional)";

  return (
    <div className={styles.container}>
      <div className={styles.row}>
        <span className={styles.prefix}>
          <GitBranchIcon size={12} />
          branch
        </span>
        <input
          type="text"
          className={styles.input}
          value={value}
          onChange={(e): void => onUserEdit(e.target.value)}
          placeholder={placeholder}
          data-testid={ElementIds.BRANCH_NAME_INPUT}
          disabled={disabled}
        />
        {isLoading && !isManuallyEdited ? <span className={styles.spinner}>…</span> : null}
        {shouldShowRequiredHint && collision !== "exists" ? (
          <span className={styles.requiredHint}>required</span>
        ) : null}
        {isManuallyEdited && preview !== value ? (
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
      </div>
      {collision === "exists" ? (
        <span className={styles.error} data-testid={ElementIds.BRANCH_NAME_COLLISION_ERROR}>
          Branch &apos;{value}&apos; already exists
        </span>
      ) : null}
    </div>
  );
};
