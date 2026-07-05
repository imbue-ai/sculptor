import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { BlandCircle, PulsingCircle } from "~/components/PulsingCircle.tsx";

import type { AgentDotStatus, WorkspaceDotStatus } from "../../common/utils/statusDot";
import styles from "./StatusDot.module.scss";

type AgentStatusDotProps = {
  status: AgentDotStatus;
  size?: number;
};

/** Renders a single dot for an agent's status. */
export const AgentStatusDot = ({ status, size = 8 }: AgentStatusDotProps): ReactElement => {
  switch (status) {
    case "running":
      return <PulsingCircle size={size} className={styles.runningDot} />;
    case "waiting":
      return <BlandCircle size={size} className={styles.waitingDot} />;
    case "error":
      return <BlandCircle size={size} className={styles.errorDot} />;
    case "unread":
      return <BlandCircle size={size} className={styles.readyDot} />;
    case "read":
      return <BlandCircle size={size} className={styles.readDot} />;
  }
};

type WorkspaceStatusDotsProps = {
  status: WorkspaceDotStatus;
  size?: number;
};

/**
 * Renders one or two dots summarising a workspace's aggregate agent status.
 *
 * When some (but not all) agents have errors, two dots are shown: an error dot
 * plus either a running, waiting, or ready/read dot.
 */
export const WorkspaceStatusDots = ({ status, size = 9 }: WorkspaceStatusDotsProps): ReactElement => {
  if (status.hasError && !status.isAllError) {
    return (
      <Flex align="center" gap="1">
        <BlandCircle size={size} className={styles.errorDot} />
        {status.hasRunning ? (
          <PulsingCircle size={size} className={styles.runningDot} />
        ) : status.hasWaiting ? (
          <BlandCircle size={size} className={styles.waitingDot} />
        ) : (
          <BlandCircle size={size} className={status.hasUnread ? styles.readyDot : styles.readDot} />
        )}
      </Flex>
    );
  }

  if (status.isAllError) {
    return <BlandCircle size={size} className={styles.errorDot} />;
  }

  if (status.hasWaiting) {
    return <BlandCircle size={size} className={styles.waitingDot} />;
  }

  if (status.hasRunning) {
    return <PulsingCircle size={size} className={styles.runningDot} />;
  }

  return <BlandCircle size={size} className={status.hasUnread ? styles.readyDot : styles.readDot} />;
};
