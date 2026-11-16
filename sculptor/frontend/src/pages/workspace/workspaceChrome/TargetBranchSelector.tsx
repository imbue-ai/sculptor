import { Text } from "@radix-ui/themes";
import { AlertCircle } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { ElementIds } from "~/api";
import type { WorkspaceVcs } from "~/common/utils/workspaceVcs.ts";
import type { BadgeInfo } from "~/components/BranchCombobox.tsx";
import { BranchCombobox, type BranchWithBadges } from "~/components/BranchCombobox.tsx";

import styles from "./TargetBranchSelector.module.scss";

type MismatchInfo = {
  /** The base branch the existing PR targets, as the code host names it (e.g. "main") */
  prBaseName: string;
  /** Badge to show on the candidates that open PRs into that base (e.g. "PR #847") */
  badge: BadgeInfo;
};

type TargetBranchSelectorProps = {
  vcs: WorkspaceVcs;
  currentTargetBranch: string | null;
  targetBranches: Array<string>;
  /** The PR base name of each candidate, from the backend. */
  prBaseNames: Readonly<Record<string, string>>;
  onBranchChange: (branch: string) => void;
  onOpenChange?: (open: boolean) => void;
  variant?: "default" | "amber";
  mismatch?: MismatchInfo | null;
};

export const TargetBranchSelector = ({
  vcs,
  currentTargetBranch,
  targetBranches,
  prBaseNames,
  onBranchChange,
  onOpenChange,
  variant = "default",
  mismatch,
}: TargetBranchSelectorProps): ReactElement => {
  const branches: Array<BranchWithBadges> = useMemo(() => {
    return targetBranches.map((branch) => ({
      branch,
      badges: mismatch && prBaseNames[branch] === mismatch.prBaseName ? [mismatch.badge] : [],
    }));
  }, [targetBranches, prBaseNames, mismatch]);

  // A missing target is shown as a warning: until the user picks one, the
  // workspace has nothing to open a pull request into.
  const isAmber = variant === "amber" || currentTargetBranch === null;
  const label = currentTargetBranch ?? (vcs === "jj" ? "No target bookmark" : "No target branch");

  return (
    <BranchCombobox
      selectedBranch={currentTargetBranch}
      onBranchSelected={onBranchChange}
      branches={branches}
      triggerVariant="ghost"
      triggerContent={
        isAmber ? (
          <span className={styles.amberText}>
            <AlertCircle size={10} className={styles.amberIcon} />
            <Text size="1" truncate>
              {label}
            </Text>
          </span>
        ) : (
          <Text size="1" truncate>
            {label}
          </Text>
        )
      }
      testId={ElementIds.TARGET_BRANCH_SELECTOR}
      className={isAmber ? styles.triggerAmber : styles.trigger}
      onOpenChange={onOpenChange}
    />
  );
};
