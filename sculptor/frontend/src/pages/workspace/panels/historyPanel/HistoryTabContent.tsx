import { Flex, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { ElementIds } from "~/api";
import { useWorkspaceCommits } from "~/common/state/hooks/useWorkspaceCommits.ts";
import { openCommitDiffTabAtom } from "~/pages/workspace/diffPanel/atoms.ts";
import type { ViewMode } from "~/pages/workspace/panels/fileBrowser/types.ts";

import { expandedCommitsAtomFamily, toggleCommitExpandedAtom } from "./atoms.ts";
import { CommitEntry } from "./CommitEntry.tsx";
import { buildCommitGraph } from "./commitGraph.ts";
import styles from "./HistoryPanel.module.scss";
import { TerminusIndicator } from "./TerminusIndicator.tsx";

type HistoryTabContentProps = {
  workspaceId: string;
  viewMode?: ViewMode;
  /**
   * When set, a commit-file click calls this instead of opening a global
   * commit-diff tab. The CommitsPanel passes its own selection setter so its
   * embedded viewer is driven by per-panel state rather than the shared
   * diff-panel tab list.
   */
  onSelectCommitFile?: (commitHash: string, filePath: string) => void;
};

export const HistoryTabContent = ({
  workspaceId,
  viewMode = "flat",
  onSelectCommitFile,
}: HistoryTabContentProps): ReactElement => {
  const { data, isPending } = useWorkspaceCommits(workspaceId);
  const expandedCommits = useAtomValue(expandedCommitsAtomFamily(workspaceId));
  const toggleExpanded = useSetAtom(toggleCommitExpandedAtom);
  const openCommitDiffTab = useSetAtom(openCommitDiffTabAtom);
  const graph = useMemo(() => buildCommitGraph(data?.commits ?? []), [data?.commits]);

  const handleFileClick = useCallback(
    (commitHash: string, filePath: string): void => {
      if (onSelectCommitFile) {
        onSelectCommitFile(commitHash, filePath);
        return;
      }
      openCommitDiffTab({ workspaceId, commitHash, filePath });
    },
    [workspaceId, onSelectCommitFile, openCommitDiffTab],
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
              onFileClick={(filePath) => handleFileClick(commit.hash, filePath)}
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
