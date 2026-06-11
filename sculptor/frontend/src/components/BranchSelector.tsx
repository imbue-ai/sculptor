import { Flex, Text } from "@radix-ui/themes";
import { GitBranchIcon } from "lucide-react";
import type { ReactElement } from "react";
import { memo, useEffect, useMemo, useState } from "react";

import type { RepoInfo } from "~/api";
import { ElementIds } from "~/api";
import { BranchSelectorCore, type BranchWithBadges } from "~/components/BranchSelectorCore.tsx";

import styles from "./BranchSelector.module.scss";

type BranchSelectorProps = {
  repoInfo: RepoInfo | null;
  fetchRepoInfo: () => Promise<RepoInfo | undefined>;
  sourceBranch: string | undefined;
  setUserSelectedBranch: (branch: string) => void;
  disabled?: boolean;
  triggerVariant?: "soft" | "ghost";
  /** Forwarded to the underlying Select.Trigger — useful for chip-style overrides. */
  className?: string;
};

const BranchSelectorComponent = ({
  repoInfo,
  fetchRepoInfo,
  sourceBranch,
  setUserSelectedBranch,
  disabled = false,
  triggerVariant = "soft",
  className,
}: BranchSelectorProps): ReactElement => {
  const [shouldFetch, setShouldFetch] = useState(false);
  const [isFetchingBranches, setIsFetchingBranches] = useState(false);

  const selectedBranchName = sourceBranch || "";
  const areBranchesLoaded = (repoInfo?.recentBranches?.length ?? 0) > 0;

  const branches: Array<BranchWithBadges> = useMemo(() => {
    const branchOptions = repoInfo?.recentBranches || [];

    return branchOptions.map((branch) => {
      const isCurrentBranch = branch === repoInfo?.currentBranch;
      const badges: Array<string | { text: string; tooltip?: string }> = [];

      if (isCurrentBranch) {
        badges.push("current");
      }

      return {
        branch,
        badges,
      };
    });
  }, [repoInfo]);

  const displayBranchName = selectedBranchName;

  useEffect(() => {
    if (shouldFetch && !isFetchingBranches) {
      setIsFetchingBranches(true);
      fetchRepoInfo().finally(() => {
        setShouldFetch(false);
        setIsFetchingBranches(false);
      });
    }
  }, [shouldFetch, fetchRepoInfo, isFetchingBranches]);

  return (
    <BranchSelectorCore
      selectedBranch={selectedBranchName}
      onBranchSelected={(branch) => {
        setUserSelectedBranch(branch);
        setShouldFetch(true);
      }}
      branches={branches}
      isLoadingBranches={!areBranchesLoaded && isFetchingBranches}
      disabled={disabled}
      triggerContent={
        <Flex align="center" gap="1" className={styles.dropdownButton}>
          <GitBranchIcon size={12} />
          <Text className={styles.selectorLabel}>source</Text>
          <Text className={styles.branchName} truncate={true}>
            {displayBranchName}
          </Text>
        </Flex>
      }
      triggerVariant={triggerVariant}
      testId={ElementIds.BRANCH_SELECTOR}
      className={className ? `${styles.dropdownButton} ${className}` : styles.dropdownButton}
      onOpenChange={(open) => open && setShouldFetch(true)}
    />
  );
};

export const BranchSelector = memo(BranchSelectorComponent);
