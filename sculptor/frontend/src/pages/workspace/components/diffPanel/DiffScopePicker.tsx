import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./DiffScopePicker.module.scss";
import type { DiffScope } from "./types.ts";

type DiffScopePickerProps = {
  scope: DiffScope;
  onScopeChange: (scope: DiffScope) => void;
  hasTargetBranch?: boolean;
  uncommittedCount?: number;
  allCount?: number;
};

const formatLabel = (label: string, count: number | undefined): string =>
  count != null && count > 0 ? `${label} ${count}` : label;

export const DiffScopePicker = ({
  scope,
  onScopeChange,
  hasTargetBranch = true,
  uncommittedCount,
  allCount,
}: DiffScopePickerProps): ReactElement => {
  const effectiveScope = !hasTargetBranch && scope === "vs-target-branch" ? "uncommitted" : scope;

  const optionClassName = (optionScope: DiffScope): string =>
    `${styles.option} ${effectiveScope === optionScope ? styles.optionActive : ""}`;

  return (
    <div className={styles.picker} data-testid={ElementIds.DIFF_SCOPE_PICKER}>
      {hasTargetBranch && (
        <button
          type="button"
          className={optionClassName("vs-target-branch")}
          onClick={() => onScopeChange("vs-target-branch")}
          data-testid={ElementIds.DIFF_SCOPE_ALL}
        >
          {formatLabel("All", allCount)}
        </button>
      )}
      <button
        type="button"
        className={optionClassName("uncommitted")}
        onClick={() => onScopeChange("uncommitted")}
        data-testid={ElementIds.DIFF_SCOPE_UNCOMMITTED}
      >
        {formatLabel("Uncommitted", uncommittedCount)}
      </button>
    </div>
  );
};
