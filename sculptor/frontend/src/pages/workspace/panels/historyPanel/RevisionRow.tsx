import { Badge, Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useMemo } from "react";

import type { RevisionInfo } from "~/api";
import { ElementIds } from "~/api";
import { formatRelativeTime } from "~/common/utils/formatRelativeTime.ts";
import { shortChangeId, shortCommitId } from "~/common/utils/jjChangeId.ts";

import { CommitGraph } from "./CommitGraph.tsx";
import { HistoryFileList } from "./HistoryFileList.tsx";
import historyStyles from "./HistoryPanel.module.scss";
import styles from "./RevisionRow.module.scss";

type FlagChip = {
  label: string;
  color: "green" | "gray" | "red" | "amber";
  isSet: boolean;
};

const flagChipsOf = (revision: RevisionInfo): Array<FlagChip> =>
  [
    { label: "working copy", color: "green" as const, isSet: revision.isWorkingCopy },
    { label: "empty", color: "gray" as const, isSet: revision.isEmpty },
    { label: "conflict", color: "red" as const, isSet: revision.hasConflict },
    { label: "divergent", color: "amber" as const, isSet: revision.isDivergent },
  ].filter((chip) => chip.isSet);

const RevisionMeta = ({ revision }: { revision: RevisionInfo }): ReactElement => {
  const changeId = shortChangeId({ changeId: revision.changeId, uniquePrefixLength: revision.changeIdPrefixLength });
  const { additions, deletions } = useMemo(
    () =>
      revision.files.reduce(
        (totals, file) => ({
          additions: totals.additions + file.additions,
          deletions: totals.deletions + file.deletions,
        }),
        { additions: 0, deletions: 0 },
      ),
    [revision.files],
  );
  const fileCount = revision.files.length;

  return (
    <Text size="1" className={historyStyles.commitMeta}>
      <span className={styles.changeId}>
        <strong>{changeId.uniquePrefix}</strong>
        {changeId.rest}
      </span>
      {fileCount > 0 && (
        <>
          {" · "}
          <span className={historyStyles.commitAdditions}>+{additions}</span>{" "}
          <span className={historyStyles.commitDeletions}>-{deletions}</span>
          {" · "}
          {fileCount} {fileCount === 1 ? "file" : "files"}
        </>
      )}
      {" · "}
      {formatRelativeTime(revision.timestamp)}
      {" · "}
      <span className={historyStyles.commitHash}>{shortCommitId(revision.commitId)}</span>
    </Text>
  );
};

type RevisionRowProps = {
  revision: RevisionInfo;
  /** The newest row, whose graph line starts at its dot. */
  isFirst: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  onFileClick: (filePath: string) => void;
};

/**
 * One jj revision in the Revisions panel: its description's first line, its
 * change id with the unique prefix emphasised, stats, time and commit id, and
 * chips for its bookmarks and flags. Clicking it lists its files. An empty
 * working copy is muted, since it holds nothing yet.
 */
export const RevisionRow = ({
  revision,
  isFirst,
  isExpanded,
  onToggle,
  onFileClick,
}: RevisionRowProps): ReactElement => {
  const description = revision.description.split("\n", 1)[0].trim();
  const isMuted = revision.isWorkingCopy && revision.isEmpty;
  const flagChips = flagChipsOf(revision);
  const historyFiles = useMemo(
    () =>
      revision.files.map((file) => ({
        path: file.path,
        status: file.status,
        additions: file.additions,
        deletions: file.deletions,
      })),
    [revision.files],
  );

  return (
    <div
      className={`${historyStyles.commitEntry} ${isMuted ? styles.muted : ""}`}
      data-testid={ElementIds.REVISION_ENTRY}
      data-change-id={revision.changeId}
      data-muted={isMuted}
    >
      <Flex>
        <CommitGraph isHead={revision.isWorkingCopy} hideTopLine={isFirst} />
        <Flex direction="column" flexGrow="1" className={historyStyles.commitInfo} onClick={onToggle}>
          <Text
            size="2"
            weight="medium"
            truncate
            className={`${historyStyles.commitMessage} ${description === "" ? styles.noDescription : ""}`}
          >
            {description === "" ? "(no description set)" : description}
          </Text>
          <RevisionMeta revision={revision} />
          {(revision.bookmarks.length > 0 || flagChips.length > 0) && (
            <Flex wrap="wrap" gap="1" mt="1">
              {revision.bookmarks.map((bookmark) => (
                <Badge key={bookmark} size="1" color="blue" variant="soft" className={styles.bookmark}>
                  {bookmark}
                </Badge>
              ))}
              {flagChips.map((chip) => (
                <Badge key={chip.label} size="1" color={chip.color} variant="soft">
                  {chip.label}
                </Badge>
              ))}
            </Flex>
          )}
        </Flex>
      </Flex>
      {isExpanded && historyFiles.length > 0 && (
        <div className={historyStyles.commitFiles}>
          <div className={historyStyles.commitFilesGraphLine} />
          <HistoryFileList files={historyFiles} viewMode="flat" onFileClick={(filePath) => onFileClick(filePath)} />
        </div>
      )}
    </div>
  );
};
