import { Text, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useTask } from "~/common/state/hooks/useTaskHelpers";
import { type AgentDotStatus, getAgentDotStatus } from "~/common/utils/statusDot.ts";
import { AgentStatusDot as AgentStatusDotBase } from "~/components/statusDot";

import { useRelativeTime } from "./hooks/useRelativeTime";
import styles from "./PeekAgentStatusDot.module.scss";

type BannerAgentStatusDotProps = {
  taskId: string | null | undefined;
  workspaceCreatedAt: string | undefined;
};

const STATUS_LABELS: Record<AgentDotStatus, string> = {
  running: "Running",
  waiting: "Waiting",
  error: "Error",
  unread: "Ready",
  read: "Idle",
};

export const PeekAgentStatusDot = ({ taskId, workspaceCreatedAt }: BannerAgentStatusDotProps): ReactElement => {
  const task = useTask(taskId ?? "");
  const dotStatus = task ? getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt) : "read";
  const activeTime = useRelativeTime(task?.updatedAt);
  const createdTime = useRelativeTime(workspaceCreatedAt);

  const tooltipContent = (
    <div className={styles.tooltipContent}>
      <Text size="1" weight="medium">
        {STATUS_LABELS[dotStatus]}
      </Text>
      {activeTime.relativeTime && <Text size="1">Active {activeTime.relativeTime}</Text>}
      {createdTime.relativeTime && <Text size="1">Created {createdTime.relativeTime}</Text>}
    </div>
  );

  return (
    <Tooltip content={tooltipContent}>
      <span data-testid={ElementIds.AGENT_STATUS_DOT} className={styles.dotWrapper}>
        <AgentStatusDotBase status={dotStatus} />
      </span>
    </Tooltip>
  );
};
