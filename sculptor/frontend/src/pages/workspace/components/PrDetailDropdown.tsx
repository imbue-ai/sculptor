import { Flex, Link, Separator, Switch, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { CheckIcon, ClockIcon, ExternalLinkIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useEffect } from "react";

import type { PrStatusInfo } from "../../../api";
import { ElementIds } from "../../../api";
import {
  ciBabysitterStatusAtomFamily,
  fetchCiBabysitterStatusAtom,
  setCiBabysitterPausedAtom,
} from "../../../common/state/atoms/ciBabysitterStatus";
import { isCiBabysitterEnabledAtom } from "../../../common/state/atoms/userConfig";
import type { GitProvider } from "./PrButton";
import styles from "./PrDetailDropdown.module.scss";

type PrDetailDropdownProps = {
  prStatus: PrStatusInfo;
  gitProvider: GitProvider;
};

const formatRelativeTime = (isoTimestamp: string | null | undefined): string => {
  if (!isoTimestamp) return "";

  const now = Date.now();
  const then = new Date(isoTimestamp).getTime();
  const diffMs = now - then;
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) return "just now";
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? "" : "s"} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;

  return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
};

const getPipelineBadge = (status: string | null | undefined): ReactElement | null => {
  switch (status) {
    case "passed":
      return <span className={`${styles.badge} ${styles.badgePassed}`}>Passed</span>;
    case "running":
      return <span className={`${styles.badge} ${styles.badgeRunning}`}>Running</span>;
    case "failed":
      return <span className={`${styles.badge} ${styles.badgeFailed}`}>Failed</span>;
    case null:
    case undefined:
    default:
      return null;
  }
};

export const PrDetailDropdown = ({ prStatus, gitProvider }: PrDetailDropdownProps): ReactElement => {
  const approvedCount = prStatus.approvals?.filter((a) => a.approved).length ?? 0;
  const totalApprovals = prStatus.approvals?.length ?? 0;
  const commentCount = prStatus.unresolvedComments?.length ?? 0;

  const workspaceId = prStatus.workspaceId;
  const isBabysitterEnabled = useAtomValue(isCiBabysitterEnabledAtom);
  const babysitterState = useAtomValue(ciBabysitterStatusAtomFamily(workspaceId));
  const fetchBabysitterState = useSetAtom(fetchCiBabysitterStatusAtom);
  const setPaused = useSetAtom(setCiBabysitterPausedAtom);

  useEffect(() => {
    if (!isBabysitterEnabled) return;
    void fetchBabysitterState(workspaceId);
  }, [workspaceId, fetchBabysitterState, isBabysitterEnabled]);

  const isPaused = babysitterState?.paused ?? false;
  const isRetired = babysitterState?.retired ?? false;
  const isAtCap = babysitterState?.atCap ?? false;
  // Status line always shows something so flipping the toggle isn't a
  // visual no-op. Retired splits on prState so the user understands why
  // the toggle is disabled. "Active" subsumes both idle and "agent has
  // been triggered" — the babysitter tab itself signals the latter.
  let babysitterStatusText: string;
  if (babysitterState == null) {
    babysitterStatusText = "Loading…";
  } else if (isRetired && prStatus.prState === "merged") {
    babysitterStatusText = "Retired (MR merged)";
  } else if (isRetired && prStatus.prState === "closed") {
    babysitterStatusText = "Retired (MR closed)";
  } else if (isRetired) {
    babysitterStatusText = "Retired";
  } else if (isPaused) {
    babysitterStatusText = "Paused";
  } else if (isAtCap) {
    babysitterStatusText = `At retry cap (${babysitterState.retryCount}/${babysitterState.retryCap})`;
  } else {
    babysitterStatusText = "Active";
  }

  // The switch reads "CI Babysitter [ON/OFF]" — semantically the
  // visible state is the babysitter's activity, not its paused-ness.
  // ON = babysitter is active (paused=false); OFF = paused.
  const handlePauseChange = (nextActive: boolean): void => {
    void setPaused({ workspaceId, paused: !nextActive });
  };

  const isGitHub = gitProvider === "github";
  const prefix = isGitHub ? "#" : "!";
  const ciLabel = isGitHub ? "Checks" : "Pipeline";
  const noCiLabel = isGitHub ? "No checks" : "No pipeline";
  const reviewLabel = isGitHub ? "Reviews" : "Approvals";
  const noReviewerLabel = isGitHub ? "No reviews" : "No reviewers assigned";

  return (
    <div className={styles.dropdown} data-testid={ElementIds.PR_DROPDOWN}>
      {/* Header */}
      <Flex align="center" gap="2" mb="3">
        {prStatus.prWebUrl ? (
          <Link size="2" weight="medium" href={prStatus.prWebUrl} target="_blank" style={{ flex: 1 }} truncate>
            {prStatus.prTitle ?? `${prefix}${prStatus.prIid}`}
            <ExternalLinkIcon size={12} style={{ marginLeft: "var(--space-1)", verticalAlign: "middle" }} />
          </Link>
        ) : (
          <Text size="2" weight="medium" style={{ flex: 1 }} truncate>
            {prStatus.prTitle ?? `${prefix}${prStatus.prIid}`}
          </Text>
        )}
      </Flex>

      <Separator size="4" mb="3" />

      {/* Pipeline/Checks section */}
      <Flex direction="column" gap="1" mb="3">
        <Text className={styles.sectionTitle}>{ciLabel}</Text>
        {prStatus.pipelineStatus ? (
          <Flex align="center" gap="2">
            {getPipelineBadge(prStatus.pipelineStatus)}
            {prStatus.pipelineId != null &&
              (prStatus.pipelineWebUrl ? (
                <Link size="1" href={prStatus.pipelineWebUrl} target="_blank">
                  #{prStatus.pipelineId}
                </Link>
              ) : (
                <Text size="1" color="gray">
                  #{prStatus.pipelineId}
                </Text>
              ))}
            {prStatus.pipelineUpdatedAt && (
              <Text size="1" color="gray">
                {formatRelativeTime(prStatus.pipelineUpdatedAt)}
              </Text>
            )}
          </Flex>
        ) : (
          <Text size="1" color="gray">
            {noCiLabel}
          </Text>
        )}
      </Flex>

      {isBabysitterEnabled && (
        <>
          <Separator size="4" mb="3" />

          {/* CI Babysitter section (experimental) */}
          <Flex direction="column" gap="1" mb="3">
            <Flex align="center" justify="between">
              <Text className={styles.sectionTitle}>CI Babysitter</Text>
              <Switch
                data-testid={ElementIds.PR_BABYSITTER_PAUSE_TOGGLE}
                checked={!isPaused}
                onCheckedChange={handlePauseChange}
                disabled={isRetired}
              />
            </Flex>
            <Text size="1" color="gray" data-testid={ElementIds.PR_BABYSITTER_STATUS}>
              {babysitterStatusText}
            </Text>
          </Flex>
        </>
      )}

      <Separator size="4" mb="3" />

      {/* Approvals section */}
      <Flex direction="column" gap="1" mb="3">
        <Text className={styles.sectionTitle}>
          {reviewLabel} {totalApprovals > 0 && `(${approvedCount}/${totalApprovals})`}
        </Text>
        {totalApprovals > 0 ? (
          prStatus.approvals?.map((approval) => (
            <div key={approval.name} className={styles.reviewerRow}>
              <span className={styles.avatar}>{approval.name.charAt(0).toUpperCase()}</span>
              <Text size="1" style={{ flex: 1 }}>
                {approval.name}
              </Text>
              {approval.approved ? (
                <CheckIcon size={14} color="var(--green-9)" />
              ) : (
                <ClockIcon size={14} color="var(--orange-9)" />
              )}
            </div>
          ))
        ) : (
          <Text size="1" color="gray">
            {noReviewerLabel}
          </Text>
        )}
      </Flex>

      <Separator size="4" mb="3" />

      {/* Unresolved comments section */}
      <Flex direction="column" gap="1">
        <Text className={styles.sectionTitle}>Unresolved comments {commentCount > 0 && `(${commentCount})`}</Text>
        {commentCount > 0 ? (
          prStatus.unresolvedComments?.map((comment, index) => (
            <div key={`${comment.author}-${comment.filePath}-${comment.line}-${index}`} className={styles.commentCard}>
              <Flex direction="column" gap="1">
                <Flex align="center" gap="2">
                  <Text size="1" weight="medium">
                    {comment.author}
                  </Text>
                  {comment.filePath && (
                    <span className={styles.fileBadge}>
                      {comment.filePath.split("/").pop()}
                      {comment.line != null && `:${comment.line}`}
                    </span>
                  )}
                </Flex>
                <Text size="1" color="gray" className={styles.commentBody}>
                  {comment.body}
                </Text>
              </Flex>
            </div>
          ))
        ) : (
          <Text size="1" color="gray">
            No unresolved comments
          </Text>
        )}
      </Flex>
    </div>
  );
};
