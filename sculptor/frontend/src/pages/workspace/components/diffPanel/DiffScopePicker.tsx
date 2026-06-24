import { SegmentedControl } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import type { DiffScope } from "./types.ts";

type DiffScopePickerProps = {
  scope: DiffScope;
  onScopeChange: (scope: DiffScope) => void;
  hasTargetBranch?: boolean;
  uncommittedCount?: number;
  allCount?: number;
};

const formatLabel = (inputs: { label: string; count: number | undefined }): string => {
  const { label, count } = inputs;
  return count !== undefined && count > 0 ? `${label} ${count}` : label;
};

export const DiffScopePicker = ({
  scope,
  onScopeChange,
  hasTargetBranch = true,
  uncommittedCount,
  allCount,
}: DiffScopePickerProps): ReactElement => {
  const effectiveScope = !hasTargetBranch && scope === "vs-target-branch" ? "uncommitted" : scope;

  return (
    <SegmentedControl.Root
      size="1"
      value={effectiveScope}
      onValueChange={(value) => onScopeChange(value as DiffScope)}
      data-testid={ElementIds.DIFF_SCOPE_PICKER}
    >
      {hasTargetBranch && (
        <SegmentedControl.Item value="vs-target-branch" data-testid={ElementIds.DIFF_SCOPE_ALL}>
          {formatLabel({ label: "All", count: allCount })}
        </SegmentedControl.Item>
      )}
      <SegmentedControl.Item value="uncommitted" data-testid={ElementIds.DIFF_SCOPE_UNCOMMITTED}>
        {formatLabel({ label: "Uncommitted", count: uncommittedCount })}
      </SegmentedControl.Item>
    </SegmentedControl.Root>
  );
};
