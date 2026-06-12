import { Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { taskAtomFamily } from "~/common/state/atoms/tasks";
import { AgentStatusDot as AgentStatusDotBase, getAgentDotStatus } from "~/components/statusDot";

import { useRelativeTime } from "../hooks/useRelativeTime";
import styles from "./AgentStatusDot.module.scss";

type BannerAgentStatusDotProps = {
  taskId: string | null | undefined;
  workspaceCreatedAt: string | undefined;
};

const STATUS_LABELS: Record<string, string> = {
  running: "Running",
  waiting: "Waiting",
  error: "Error",
  unread: "Ready",
  read: "Idle",
};

export const AgentStatusDot = ({ taskId, workspaceCreatedAt }: BannerAgentStatusDotProps): ReactElement => {
  const task = useAtomValue(taskAtomFamily(taskId ?? ""));
  const dotStatus = task ? getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt) : "read";
  const activeTime = useRelativeTime(task?.updatedAt);
  const createdTime = useRelativeTime(workspaceCreatedAt);

  const tooltipContent = (
    <div className={styles.tooltipContent}>
      <Text size="1" weight="medium">
        {STATUS_LABELS[dotStatus] ?? "Idle"}
      </Text>
      {activeTime.relativeTime && <Text size="1">Active {activeTime.relativeTime}</Text>}
      {createdTime.relativeTime && <Text size="1">Created {createdTime.relativeTime}</Text>}
    </div>
  );

  return (
    <Tooltip content={tooltipContent}>
      <span data-testid={ElementIds.AGENT_STATUS_DOT} style={{ display: "inline-flex" }}>
        <AgentStatusDotBase status={dotStatus} />
      </span>
    </Tooltip>
  );
};
