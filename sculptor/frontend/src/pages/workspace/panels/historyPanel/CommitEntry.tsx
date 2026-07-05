import * as HoverCard from "@radix-ui/react-hover-card";
import { Flex, IconButton, Text } from "@radix-ui/themes";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { type CommitInfo, ElementIds } from "~/api";
import { formatRelativeTime } from "~/common/utils/formatRelativeTime.ts";
import type { FileStatus, ViewMode } from "~/pages/workspace/panels/fileBrowser/types/fileBrowser.ts";

import { CommitGraph } from "./CommitGraph.tsx";
import { HistoryFileList } from "./HistoryFileList.tsx";
import styles from "./HistoryPanel.module.scss";
import { MergeSpurRow } from "./MergeSpurRow.tsx";
import { TerminusIndicator } from "./TerminusIndicator.tsx";

const HOVER_CARD_OPEN_DELAY_MS = 400;
const HOVER_CARD_CLOSE_DELAY_MS = 300;
// Extra margin beyond the open delay before re-enabling hover after a click,
// so a click that collapses the row can't immediately re-trigger the hover card.
const CLICK_SUPPRESS_BUFFER_MS = 100;

const useDiffStats = (
  files: CommitInfo["files"],
): { totalAdditions: number; totalDeletions: number; fileCount: number } =>
  useMemo(() => {
    let totalAdditions = 0;
    let totalDeletions = 0;
    for (const f of files) {
      totalAdditions += f.additions;
      totalDeletions += f.deletions;
    }
    return { totalAdditions, totalDeletions, fileCount: files.length };
  }, [files]);

const CommitMeta = ({ commit }: { commit: CommitInfo }): ReactElement => {
  const { totalAdditions, totalDeletions, fileCount } = useDiffStats(commit.files);

  return (
    <Text size="1" className={styles.commitMeta} data-testid={ElementIds.HISTORY_COMMIT_META}>
      {fileCount > 0 && (
        <>
          <span className={styles.commitAdditions}>+{totalAdditions}</span>{" "}
          <span className={styles.commitDeletions}>-{totalDeletions}</span>
          {" · "}
          {fileCount} {fileCount === 1 ? "file" : "files"}
          {" · "}
        </>
      )}
      {formatRelativeTime(commit.timestamp)}
      {" · "}
      <span className={styles.commitHash}>{commit.shortHash}</span>
    </Text>
  );
};

const COPY_FEEDBACK_DURATION_MS = 2000;

const CommitPopoverContent = ({ commit }: { commit: CommitInfo }): ReactElement => {
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const { totalAdditions, totalDeletions, fileCount } = useDiffStats(commit.files);

  useEffect((): (() => void) => () => clearTimeout(copyTimerRef.current), []);

  const handleCopyHash = useCallback((): void => {
    void navigator.clipboard.writeText(commit.hash).then(() => {
      setIsCopied(true);
      clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setIsCopied(false), COPY_FEEDBACK_DURATION_MS);
    });
  }, [commit.hash]);

  return (
    <Flex direction="column" gap="2" className={styles.popoverBody} data-testid={ElementIds.HISTORY_COMMIT_POPOVER}>
      <Text size="2" weight="medium" className={styles.popoverMessage}>
        {commit.message}
      </Text>
      <Flex direction="column" gap="1" className={styles.popoverMeta}>
        <Flex justify="between" align="center">
          <Text size="1" color="gray">
            Author
          </Text>
          <Text size="1">{commit.authorName}</Text>
        </Flex>
        <Flex justify="between" align="center">
          <Text size="1" color="gray">
            Date
          </Text>
          <Text size="1">
            {new Date(commit.timestamp).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}{" "}
            · {formatRelativeTime(commit.timestamp)}
          </Text>
        </Flex>
        <Flex justify="between" align="center">
          <Text size="1" color="gray">
            Commit id
          </Text>
          <Flex align="center" gap="2">
            <Text size="1" className={styles.popoverHash}>
              {commit.shortHash}
            </Text>
            <IconButton variant="ghost" size="1" onClick={handleCopyHash} color="gray">
              {isCopied ? <CheckIcon size={12} /> : <CopyIcon size={12} />}
            </IconButton>
          </Flex>
        </Flex>
        {fileCount > 0 && (
          <Flex justify="between" align="center">
            <Text size="1" color="gray">
              Changes
            </Text>
            <Text size="1">
              <span className={styles.commitAdditions}>+{totalAdditions}</span>{" "}
              <span className={styles.commitDeletions}>-{totalDeletions}</span>
              {" · "}
              {fileCount} {fileCount === 1 ? "file" : "files"}
            </Text>
          </Flex>
        )}
      </Flex>
    </Flex>
  );
};

/** Expanded merge commit: shows the side-branch commit list with graph lines. */
const MergeBranchView = ({
  commit,
  sideBranch,
}: {
  commit: CommitInfo;
  sideBranch: Array<CommitInfo>;
}): ReactElement => (
  <div className={styles.sideBranch}>
    <MergeSpurRow parentHash={commit.parentHashes[1]} connected />
    <Flex>
      {/* Main line continuation through the nested branch */}
      <div className={styles.commitFilesGraphSpacer}>
        <div className={styles.graphLineBottom} />
      </div>
      <Flex direction="column" flexGrow="1">
        {sideBranch.map((sc) => (
          <SideBranchEntry key={sc.hash} commit={sc} />
        ))}
        <TerminusIndicator forkPoint={sideBranch[sideBranch.length - 1].parentHashes[0] ?? null} hideTopLine={false} />
      </Flex>
    </Flex>
  </div>
);

const SideBranchEntry = ({ commit }: { commit: CommitInfo }): ReactElement => {
  const [isHoverOpen, setIsHoverOpen] = useState<boolean>(false);
  const handleClick = useCallback((): void => setIsHoverOpen(false), []);

  return (
    <div className={styles.commitEntry}>
      <Flex>
        <CommitGraph isHead={false} hideTopLine={false} />
        <HoverCard.Root
          openDelay={HOVER_CARD_OPEN_DELAY_MS}
          closeDelay={HOVER_CARD_CLOSE_DELAY_MS}
          open={isHoverOpen}
          onOpenChange={setIsHoverOpen}
        >
          <HoverCard.Trigger asChild>
            <Flex direction="column" flexGrow="1" py="1" px="2" onClick={handleClick}>
              <Text size="2" weight="medium" className={styles.commitMessage} truncate>
                {commit.message}
              </Text>
              <CommitMeta commit={commit} />
            </Flex>
          </HoverCard.Trigger>
          <HoverCard.Content side="right" align="start" sideOffset={4} className={styles.popoverContent}>
            <CommitPopoverContent commit={commit} />
          </HoverCard.Content>
        </HoverCard.Root>
      </Flex>
    </div>
  );
};

type CommitEntryProps = {
  commit: CommitInfo;
  isHead: boolean;
  hideTopLine: boolean;
  isExpanded: boolean;
  viewMode: ViewMode;
  onToggle: () => void;
  onFileClick: (filePath: string, status: FileStatus) => void;
  /** Commits on the second-parent chain, shown nested when a merge is expanded. */
  sideBranch?: Array<CommitInfo>;
};

export const CommitEntry = ({
  commit,
  isHead,
  hideTopLine,
  isExpanded,
  viewMode,
  onToggle,
  onFileClick,
  sideBranch,
}: CommitEntryProps): ReactElement => {
  const [isHoverOpen, setIsHoverOpen] = useState<boolean>(false);
  const clickSuppressRef = useRef<boolean>(false);
  const suppressTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const isMerge = commit.parentHashes.length > 1;
  const hasSideBranch = sideBranch !== undefined && sideBranch.length > 0;

  useEffect((): (() => void) => () => clearTimeout(suppressTimerRef.current), []);

  const historyFiles = useMemo(
    () =>
      commit.files.map((f) => ({
        path: f.path,
        status: f.status,
        additions: f.additions,
        deletions: f.deletions,
      })),
    [commit.files],
  );

  const handleClick = useCallback((): void => {
    clickSuppressRef.current = true;
    setIsHoverOpen(false);
    onToggle();
    clearTimeout(suppressTimerRef.current);
    suppressTimerRef.current = setTimeout(() => {
      clickSuppressRef.current = false;
    }, HOVER_CARD_OPEN_DELAY_MS + CLICK_SUPPRESS_BUFFER_MS);
  }, [onToggle]);

  const handleHoverChange = useCallback((open: boolean): void => {
    if (open && clickSuppressRef.current) return;
    setIsHoverOpen(open);
  }, []);

  return (
    <div className={styles.commitEntry} data-testid={ElementIds.HISTORY_COMMIT_ENTRY}>
      <Flex>
        <CommitGraph isHead={isHead} hideTopLine={hideTopLine} />
        <HoverCard.Root
          openDelay={HOVER_CARD_OPEN_DELAY_MS}
          closeDelay={HOVER_CARD_CLOSE_DELAY_MS}
          open={isHoverOpen}
          onOpenChange={handleHoverChange}
        >
          <HoverCard.Trigger asChild>
            <Flex
              direction="column"
              flexGrow="1"
              className={styles.commitInfo}
              onClick={handleClick}
              data-testid={ElementIds.HISTORY_COMMIT_MESSAGE}
            >
              <Text size="2" weight="medium" className={styles.commitMessage} truncate>
                {commit.message}
              </Text>
              <CommitMeta commit={commit} />
            </Flex>
          </HoverCard.Trigger>
          <HoverCard.Content side="right" align="start" sideOffset={4} className={styles.popoverContent}>
            <CommitPopoverContent commit={commit} />
          </HoverCard.Content>
        </HoverCard.Root>
      </Flex>
      {isExpanded && isMerge && !hasSideBranch && <MergeSpurRow parentHash={commit.parentHashes[1]} />}
      {isExpanded && isMerge && hasSideBranch && <MergeBranchView commit={commit} sideBranch={sideBranch} />}
      {isExpanded && !isMerge && commit.files.length > 0 && (
        <div className={styles.commitFiles}>
          <div className={styles.commitFilesGraphLine} />
          <HistoryFileList files={historyFiles} viewMode={viewMode} onFileClick={onFileClick} />
        </div>
      )}
    </div>
  );
};
