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
  // Track the in-flight fetch and whether another was requested while it ran,
  // so a trigger during a fetch refreshes exactly once more on completion
  // (matching the previous flag-watching effect) without stacking requests.
  const isFetchingRef = useRef(false);
  const isRefetchQueuedRef = useRef(false);

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
  // branch or opening the dropdown). Triggered directly from the handlers
  // rather than via a watched flag + effect. A trigger that arrives while a
  // fetch is in flight queues exactly one more refresh on completion (matching
  // the previous flag-watching effect) without stacking concurrent requests.
  // See docs/development/review/react.md (`no_effect_for_event_handling`).
  const triggerFetch = useCallback((): void => {
    if (isFetchingRef.current) {
      isRefetchQueuedRef.current = true;
      return;
    }
    isFetchingRef.current = true;
    setIsFetchingBranches(true);
    const runFetch = (): void => {
      void fetchRepoInfo().finally(() => {
        if (isRefetchQueuedRef.current) {
          isRefetchQueuedRef.current = false;
          runFetch();
          return;
        }
        isFetchingRef.current = false;
        setIsFetchingBranches(false);
      });
    };
    runFetch();
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
