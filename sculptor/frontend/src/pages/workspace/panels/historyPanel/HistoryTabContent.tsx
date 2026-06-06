import { Flex, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { ElementIds } from "~/api";
import { useWorkspaceCommits } from "~/common/state/hooks/useWorkspaceCommits.ts";
import { openCommitDiffTabAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";
import type { FileStatus, ViewMode } from "~/pages/workspace/panels/fileBrowser/types.ts";

import { expandedCommitsAtomFamily, toggleCommitExpandedAtom } from "./atoms.ts";
import { CommitEntry } from "./CommitEntry.tsx";
import { buildCommitGraph } from "./commitGraph.ts";
import styles from "./HistoryPanel.module.scss";
import { TerminusIndicator } from "./TerminusIndicator.tsx";

type HistoryTabContentProps = {
  workspaceId: string;
  viewMode?: ViewMode;
  /** Per-panel diff scope key — selecting a commit file opens it in this scope. */
  diffStateKey?: string;
};

export const HistoryTabContent = ({
  workspaceId,
  viewMode = "flat",
  diffStateKey,
}: HistoryTabContentProps): ReactElement => {
  const { data, isPending } = useWorkspaceCommits(workspaceId);
  const expandedCommits = useAtomValue(expandedCommitsAtomFamily(workspaceId));
  const toggleExpanded = useSetAtom(toggleCommitExpandedAtom);
  const openCommitDiffTab = useSetAtom(openCommitDiffTabAtom);
  const graph = useMemo(() => buildCommitGraph(data?.commits ?? []), [data?.commits]);

  const handleFileClick = useCallback(
    (commitHash: string, filePath: string, _status: FileStatus): void => {
      openCommitDiffTab({ workspaceId, stateKey: diffStateKey, commitHash, filePath });
    },
    [workspaceId, openCommitDiffTab, diffStateKey],
  );

  return (
    <Flex direction="column" flexGrow="1" overflow="hidden" data-testid={ElementIds.HISTORY_PANEL}>
      <Flex direction="column" flexGrow="1" className={styles.scrollArea}>
        {isPending && (
          <Flex align="center" justify="center" flexGrow="1">
            <Text size="2" color="gray">
              Loading history…
            </Text>
          </Flex>
        )}
        {!isPending && !data && (
          <Flex align="center" justify="center" flexGrow="1">
            <Text size="2" color="gray">
              No history available
            </Text>
          </Flex>
        )}
        {!isPending &&
          data &&
          graph.mainLine.length > 0 &&
          graph.mainLine.map((commit, index) => (
            <CommitEntry
              key={commit.hash}
              commit={commit}
              isHead={index === 0}
              hideTopLine={index === 0}
              isExpanded={expandedCommits.has(commit.hash)}
              viewMode={viewMode}
              onToggle={() => toggleExpanded({ workspaceId, commitHash: commit.hash })}
              onFileClick={(filePath, status) => handleFileClick(commit.hash, filePath, status)}
              sideBranch={graph.sideBranches.get(commit.hash)}
            />
          ))}
        {!isPending && data && (
          <TerminusIndicator
            forkPoint={
              graph.mainLine.length > 0
                ? (graph.mainLine[graph.mainLine.length - 1].parentHashes[0] ?? data.forkPoint)
                : data.forkPoint
            }
            hideTopLine={graph.mainLine.length === 0}
          />
        )}
      </Flex>
    </Flex>
  );
};
