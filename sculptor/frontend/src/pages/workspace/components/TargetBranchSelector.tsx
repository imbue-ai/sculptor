import { Text } from "@radix-ui/themes";
import { AlertCircle } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { ElementIds } from "~/api";
import type { BadgeInfo } from "~/components/BranchSelectorCore.tsx";
import { BranchSelectorCore, type BranchWithBadges } from "~/components/BranchSelectorCore.tsx";

import styles from "./TargetBranchSelector.module.scss";

type MismatchInfo = {
  /** The branch the existing MR/PR targets (bare name, e.g. "main") */
  targetBranch: string;
  /** Badge to show on that branch in the dropdown (e.g. "MR !847") */
  badge: BadgeInfo;
};

type TargetBranchSelectorProps = {
  currentTargetBranch: string;
  targetBranches: Array<string>;
  onBranchChange: (branch: string) => void;
  onOpenChange?: (open: boolean) => void;
  variant?: "default" | "amber";
  mismatch?: MismatchInfo | null;
};

export const TargetBranchSelector = ({
  currentTargetBranch,
  targetBranches,
  onBranchChange,
  onOpenChange,
  variant = "default",
  mismatch,
}: TargetBranchSelectorProps): ReactElement => {
  const branches: Array<BranchWithBadges> = useMemo(() => {
    return targetBranches.map((branch) => ({
      branch,
      badges: mismatch && branch === `origin/${mismatch.targetBranch}` ? [mismatch.badge] : [],
    }));
  }, [targetBranches, mismatch]);

  const isAmber = variant === "amber";

  return (
    <BranchSelectorCore
      selectedBranch={currentTargetBranch}
      onBranchSelected={onBranchChange}
      branches={branches}
      triggerVariant="ghost"
      triggerContent={
        isAmber ? (
          <span className={styles.amberText}>
            <AlertCircle size={10} className={styles.amberIcon} />
            <Text size="1" truncate>
              {currentTargetBranch}
            </Text>
          </span>
        ) : (
          <Text size="1" truncate>
            {currentTargetBranch}
          </Text>
        )
      }
      testId={ElementIds.TARGET_BRANCH_SELECTOR}
      className={isAmber ? styles.triggerAmber : styles.trigger}
      onOpenChange={onOpenChange}
    />
  );
};
