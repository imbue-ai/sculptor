import { TaskStatus } from "~/api";

/**
 * Visual status for a single agent's status dot.
 *
 * This is the single source of truth for how TaskStatus maps to a dot appearance.
 * All components showing an agent status dot should derive from this.
 */
export type AgentDotStatus = "running" | "waiting" | "error" | "unread" | "read";

export function getAgentDotStatus(status: TaskStatus, lastReadAt: string | null, updatedAt: string): AgentDotStatus {
  if (status === TaskStatus.RUNNING || status === TaskStatus.BUILDING) {
    return "running";
  }

  if (status === TaskStatus.WAITING) {
    return "waiting";
  }

  if (status === TaskStatus.ERROR) {
    return "error";
  }

  // Request-level errors (e.g. API 429) show as "error" until the user views
  // the workspace, then clear to "read" — unlike full ERROR which persists.
  if (status === TaskStatus.REQUEST_ERROR) {
    if (lastReadAt === null || new Date(updatedAt) > new Date(lastReadAt)) {
      return "error";
    }
    return "read";
  }

  if (lastReadAt === null || new Date(updatedAt) > new Date(lastReadAt)) {
    return "unread";
  }
  return "read";
}

/**
 * Aggregated visual status for a workspace's status dot(s).
 *
 * Computed from the individual agent statuses within a workspace.
 */
export type WorkspaceDotStatus = {
  hasError: boolean;
  hasWaiting: boolean;
  hasRunning: boolean;
  isAllError: boolean;
  hasUnread: boolean;
};

export const EMPTY_WORKSPACE_DOT_STATUS: WorkspaceDotStatus = {
  hasError: false,
  hasWaiting: false,
  hasRunning: false,
  isAllError: false,
  hasUnread: false,
};

type AgentTaskLike = {
  status: TaskStatus;
  lastReadAt: string | null;
  updatedAt: string;
  isDeleted?: boolean;
  isArchived?: boolean;
};

export function computeWorkspaceDotStatus(tasks: ReadonlyArray<AgentTaskLike>): WorkspaceDotStatus {
  const activeTasks = tasks.filter((task) => !task.isDeleted && !task.isArchived);

  if (activeTasks.length === 0) {
    return EMPTY_WORKSPACE_DOT_STATUS;
  }

  const hasError = activeTasks.some((task) => {
    const dotStatus = getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt);
    return dotStatus === "error";
  });
  const hasWaiting = activeTasks.some((task) => task.status === TaskStatus.WAITING);
  const hasRunning = activeTasks.some(
    (task) => task.status === TaskStatus.RUNNING || task.status === TaskStatus.BUILDING,
  );
  const isAllError = activeTasks.every((task) => {
    const dotStatus = getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt);
    return dotStatus === "error";
  });
  const hasUnread = activeTasks.some((task) => {
    const dotStatus = getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt);
    return dotStatus === "unread";
  });

  return { hasError, hasWaiting, hasRunning, isAllError, hasUnread };
}
