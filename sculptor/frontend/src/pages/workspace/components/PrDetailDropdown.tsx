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
import styles from "./PrDetailDropdown.module.scss";

type PrDetailDropdownProps = {
  prStatus: PrStatusInfo;
};

const MS_PER_MINUTE = 60_000;
const MS_PER_HOUR = 3_600_000;
const MS_PER_DAY = 86_400_000;
const MINUTES_PER_HOUR = 60;
const HOURS_PER_DAY = 24;

const formatRelativeTime = (isoTimestamp: string | null | undefined): string => {
  if (!isoTimestamp) return "";

  const now = Date.now();
  const then = new Date(isoTimestamp).getTime();
  const diffMs = now - then;
  const diffMinutes = Math.floor(diffMs / MS_PER_MINUTE);
  const diffHours = Math.floor(diffMs / MS_PER_HOUR);
  const diffDays = Math.floor(diffMs / MS_PER_DAY);

  if (diffMinutes < 1) return "just now";
  if (diffMinutes < MINUTES_PER_HOUR) return `${diffMinutes} minute${diffMinutes === 1 ? "" : "s"} ago`;
  if (diffHours < HOURS_PER_DAY) return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;

  return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
};

const getPipelineBadge = (status: PrStatusInfo["pipelineStatus"]): ReactElement | undefined => {
  switch (status) {
    case "passed":
      return <span className={`${styles.badge} ${styles.badgePassed}`}>Passed</span>;
    case "running":
      return <span className={`${styles.badge} ${styles.badgeRunning}`}>Running</span>;
    case "failed":
      return <span className={`${styles.badge} ${styles.badgeFailed}`}>Failed</span>;
    case null:
    case undefined:
      return undefined;
  }
};

export const PrDetailDropdown = ({ prStatus }: PrDetailDropdownProps): ReactElement => {
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
  const disabledReason = babysitterState?.disabledReason ?? null;
  // A persistent reason (MRU non-driveable / pinned harness unavailable) means
  // the babysitter is inert until the user fixes the cause; a transient reason
  // ("will retry on the next failure") still leaves the pause toggle meaningful.
  const isPersistentlyDisabled = disabledReason != null && !(babysitterState?.disabledReasonIsTransient ?? false);
  // Status line always shows something so flipping the toggle isn't a
  // visual no-op. Retired splits on prState so the user understands why
  // the toggle is disabled. A disabled reason takes precedence over
  // "Active"/"At retry cap" so a non-driveable workspace never reads "Active".
  let babysitterStatusText: string;
  if (babysitterState == null) {
    babysitterStatusText = "Loading…";
  } else if (isRetired && prStatus.prState === "merged") {
    babysitterStatusText = "Retired (PR merged)";
  } else if (isRetired && prStatus.prState === "closed") {
    babysitterStatusText = "Retired (PR closed)";
  } else if (isRetired) {
    babysitterStatusText = "Retired";
  } else if (disabledReason != null) {
    babysitterStatusText = disabledReason;
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

  return (
    <div className={styles.dropdown} data-testid={ElementIds.PR_DROPDOWN}>
      <Flex align="center" gap="2" mb="3">
        {prStatus.prWebUrl ? (
          <Link size="2" weight="medium" href={prStatus.prWebUrl} target="_blank" style={{ flex: 1 }} truncate>
            {prStatus.prTitle ?? `#${prStatus.prIid}`}
            <ExternalLinkIcon size={12} style={{ marginLeft: "var(--space-1)", verticalAlign: "middle" }} />
          </Link>
        ) : (
          <Text size="2" weight="medium" style={{ flex: 1 }} truncate>
            {prStatus.prTitle ?? `#${prStatus.prIid}`}
          </Text>
        )}
      </Flex>

      <Separator size="4" mb="3" />

      <Flex direction="column" gap="1" mb="3">
        <Text className={styles.sectionTitle}>Checks</Text>
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
            No checks
          </Text>
        )}
      </Flex>

      {isBabysitterEnabled && (
        <>
          <Separator size="4" mb="3" />

          <Flex direction="column" gap="1" mb="3">
            <Flex align="center" justify="between">
              <Text className={styles.sectionTitle}>CI Babysitter</Text>
              <Switch
                data-testid={ElementIds.PR_BABYSITTER_PAUSE_TOGGLE}
                checked={!isPaused && !isPersistentlyDisabled}
                onCheckedChange={handlePauseChange}
                disabled={isRetired || isPersistentlyDisabled}
              />
            </Flex>
            <Text size="1" color="gray" data-testid={ElementIds.PR_BABYSITTER_STATUS}>
              {babysitterStatusText}
            </Text>
          </Flex>
        </>
      )}

      <Separator size="4" mb="3" />

      <Flex direction="column" gap="1" mb="3">
        <Text className={styles.sectionTitle}>
          Reviews {totalApprovals > 0 && `(${approvedCount}/${totalApprovals})`}
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
            No reviews
          </Text>
        )}
      </Flex>

      <Separator size="4" mb="3" />

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
