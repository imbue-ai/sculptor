import { Flex, Text } from "@radix-ui/themes";
import { MoreVertical } from "lucide-react";
import type { ReactElement } from "react";

import type { RevisionHistoryResponse, RevisionInfo } from "~/api";
import { ElementIds } from "~/api";
import { shortCommitId } from "~/common/utils/jjChangeId.ts";

import styles from "./HistoryPanel.module.scss";
import { RevisionRow } from "./RevisionRow.tsx";

const forkPointLabel = (inputs: { target: string | null; forkPoint: string | null }): string => {
  const parts = [inputs.target, inputs.forkPoint === null ? null : shortCommitId(inputs.forkPoint)].filter(
    (part): part is string => part !== null,
  );
  return parts.length === 0 ? "fork point" : `fork point (${parts.join(" · ")})`;
};

/** The foot of the list: where the workspace's stack forks from its target. */
const RevisionsForkPoint = ({
  target,
  forkPoint,
  hideTopLine,
}: {
  target: string | null;
  forkPoint: string | null;
  hideTopLine: boolean;
}): ReactElement => (
  <div className={styles.terminus}>
    <div className={styles.terminusGraph}>
      <div className={`${styles.terminusLine} ${hideTopLine ? styles.graphLineHidden : ""}`} />
      <div className={styles.terminusDot} />
      <div className={styles.terminusLine} />
      <MoreVertical size={12} color="var(--gray-7)" />
    </div>
    <Text size="1" color="gray" className={styles.terminusLabel} data-testid={ElementIds.REVISIONS_FORK_POINT}>
      {forkPointLabel({ target, forkPoint })}
    </Text>
  </div>
);

type RevisionListProps = {
  /** Undefined until the revisions load; null when the workspace has none to show. */
  history: RevisionHistoryResponse | null | undefined;
  isPending: boolean;
  /** The workspace's target bookmark, named in the footer. */
  target: string | null;
  /** The change ids of the revisions whose files are listed. */
  expandedChangeIds: ReadonlySet<string>;
  onToggleRevision: (changeId: string) => void;
  onSelectFile: (revision: RevisionInfo, filePath: string) => void;
};

/**
 * A jj workspace's revisions, newest first, from the working copy back to the
 * fork point with the workspace's target.
 */
export const RevisionList = ({
  history,
  isPending,
  target,
  expandedChangeIds,
  onToggleRevision,
  onSelectFile,
}: RevisionListProps): ReactElement => (
  <Flex direction="column" flexGrow="1" overflow="hidden" data-testid={ElementIds.HISTORY_PANEL}>
    <Flex direction="column" flexGrow="1" className={styles.scrollArea}>
      {isPending && (
        <Flex align="center" justify="center" flexGrow="1">
          <Text size="2" color="gray">
            Loading revisions…
          </Text>
        </Flex>
      )}
      {!isPending && !history && (
        <Flex align="center" justify="center" flexGrow="1">
          <Text size="2" color="gray">
            No revisions available
          </Text>
        </Flex>
      )}
      {!isPending && history && (
        <>
          {history.revisions.map((revision, index) => (
            <RevisionRow
              key={revision.commitId}
              revision={revision}
              isFirst={index === 0}
              isExpanded={expandedChangeIds.has(revision.changeId)}
              onToggle={() => onToggleRevision(revision.changeId)}
              onFileClick={(filePath) => onSelectFile(revision, filePath)}
            />
          ))}
          <RevisionsForkPoint
            target={target}
            forkPoint={history.forkPoint}
            hideTopLine={history.revisions.length === 0}
          />
        </>
      )}
    </Flex>
  </Flex>
);
