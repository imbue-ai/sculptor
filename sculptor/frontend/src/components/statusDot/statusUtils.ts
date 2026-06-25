import { TaskStatus } from "~/api";

/**
 * Visual status for a single agent's status dot.
 *
 * This is the single source of truth for how TaskStatus maps to a dot appearance.
 * All components showing an agent status dot should derive from this.
 */
export type AgentDotStatus = "running" | "waiting" | "error" | "unread" | "read";

function hasUnreadUpdate(lastReadAt: string | null, updatedAt: string): boolean {
  return lastReadAt === null || new Date(updatedAt) > new Date(lastReadAt);
}

export function getAgentDotStatus(
  status: TaskStatus,
  lastReadAt: string | null,
  updatedAt: string,
  isFocused: boolean = false,
): AgentDotStatus {
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
    return hasUnreadUpdate(lastReadAt, updatedAt) ? "error" : "read";
  }

  // The agent the user is currently viewing reads as "read" so its dot doesn't
  // flash unread while the debounced mark-read settles. An explicit mark-unread
  // (lastReadAt === null) is still honored while focused — the user can mark the
  // active agent unread and it must stay unread.
  if (isFocused && lastReadAt !== null) {
    return "read";
  }

  return hasUnreadUpdate(lastReadAt, updatedAt) ? "unread" : "read";
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
  id: string;
  status: TaskStatus;
  lastReadAt: string | null;
  updatedAt: string;
  isDeleted?: boolean;
  isArchived?: boolean;
};

// `focusedAgentId` is the agent the user is currently viewing (or null when no
// agent is focused, e.g. on the home page); it is treated as read — see
// getAgentDotStatus.
export function computeWorkspaceDotStatus(
  tasks: ReadonlyArray<AgentTaskLike>,
  focusedAgentId: string | null = null,
): WorkspaceDotStatus {
  const activeTasks = tasks.filter((task) => !task.isDeleted && !task.isArchived);

  if (activeTasks.length === 0) {
    return EMPTY_WORKSPACE_DOT_STATUS;
  }

  const dotStatuses = activeTasks.map((task) =>
    getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt, task.id === focusedAgentId),
  );
  const hasError = dotStatuses.some((dotStatus) => dotStatus === "error");
  const hasWaiting = activeTasks.some((task) => task.status === TaskStatus.WAITING);
  const hasRunning = activeTasks.some(
    (task) => task.status === TaskStatus.RUNNING || task.status === TaskStatus.BUILDING,
  );
  const isAllError = dotStatuses.every((dotStatus) => dotStatus === "error");
  const hasUnread = dotStatuses.some((dotStatus) => dotStatus === "unread");

  return { hasError, hasWaiting, hasRunning, isAllError, hasUnread };
}
