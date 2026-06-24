import { Flex, Text } from "@radix-ui/themes";
import { GitBranchIcon } from "lucide-react";
import type { ReactElement } from "react";
import { memo, useCallback, useMemo, useRef, useState } from "react";

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
};

const BranchSelectorComponent = ({
  repoInfo,
  fetchRepoInfo,
  sourceBranch,
  setUserSelectedBranch,
  disabled = false,
  triggerVariant = "soft",
}: BranchSelectorProps): ReactElement => {
  const [isFetchingBranches, setIsFetchingBranches] = useState(false);
  // Drop refresh requests that arrive while one is already in flight, so they
  // don't stack into concurrent fetches.
  const isFetchingRef = useRef(false);

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

  // Refresh the branch list in response to a user interaction (selecting a
  // branch or opening the dropdown), straight from the handler. A request that
  // arrives while a refresh is in flight is dropped.
  const triggerFetch = useCallback((): void => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    setIsFetchingBranches(true);
    void fetchRepoInfo().finally(() => {
      isFetchingRef.current = false;
      setIsFetchingBranches(false);
    });
  }, [fetchRepoInfo]);

  return (
    <BranchSelectorCore
      selectedBranch={selectedBranchName}
      onBranchSelected={(branch) => {
        setUserSelectedBranch(branch);
        triggerFetch();
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
      className={styles.dropdownButton}
      onOpenChange={(open) => {
        if (open) triggerFetch();
      }}
    />
  );
};

export const BranchSelector = memo(BranchSelectorComponent);
