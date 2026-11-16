import { Flex, Text } from "@radix-ui/themes";
import { BookmarkIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import type { JjBookmarkChoice } from "~/api";
import { ElementIds } from "~/api";
import { BranchCombobox, type BranchWithBadges } from "~/components/BranchCombobox.tsx";

import styles from "./BranchSelector.module.scss";

type JjBookmarkSelectorProps = {
  bookmarks: ReadonlyArray<JjBookmarkChoice> | undefined;
  /** The picked bookmark's symbol; undefined starts the jj workspace from its target. */
  selectedBookmark: string | undefined;
  onBookmarkSelected: (symbol: string) => void;
  /** Called when the picker opens, to fetch the bookmarks again. */
  onOpen: () => void;
  isLoading: boolean;
  className?: string;
};

/**
 * The source picker for a jj workspace: the repository's bookmarks, local
 * (`main`) and remote (`main@origin`). With none picked, the workspace starts
 * from its target bookmark.
 */
export const JjBookmarkSelector = ({
  bookmarks,
  selectedBookmark,
  onBookmarkSelected,
  onOpen,
  isLoading,
  className,
}: JjBookmarkSelectorProps): ReactElement => {
  const choices: Array<BranchWithBadges> = useMemo(
    () => (bookmarks ?? []).map((bookmark) => ({ branch: bookmark.symbol, badges: [] })),
    [bookmarks],
  );

  return (
    <BranchCombobox
      selectedBranch={selectedBookmark ?? null}
      onBranchSelected={onBookmarkSelected}
      branches={choices}
      isLoadingBranches={isLoading && bookmarks === undefined}
      triggerContent={
        <Flex align="center" gap="1" className={styles.dropdownButton}>
          <BookmarkIcon size={12} />
          <Text className={styles.selectorLabel}>source</Text>
          {selectedBookmark === undefined ? (
            <Text className={styles.selectorLabel}>same as target</Text>
          ) : (
            <Text className={styles.branchName} truncate={true}>
              {selectedBookmark}
            </Text>
          )}
        </Flex>
      }
      triggerVariant="ghost"
      testId={ElementIds.BRANCH_SELECTOR}
      className={className ? `${styles.dropdownButton} ${className}` : styles.dropdownButton}
      onOpenChange={(open) => {
        if (open) onOpen();
      }}
    />
  );
};
