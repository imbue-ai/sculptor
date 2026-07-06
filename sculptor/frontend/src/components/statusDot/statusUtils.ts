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

  // The agent the user is currently viewing has its content on screen, so it
  // reads as "read". An explicit mark-unread (lastReadAt === null) is the
  // exception — the user can mark the active agent unread and it must stay so.
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

// Per-task dot resolution used by the workspace aggregate. Injectable (and
// generic over the caller's task type) so override-aware callers — the sidebar
// rows, matching the panel tabs' manual mark-as-unread — can substitute their
// resolver without this pure leaf module importing override state.
const resolveBaseDotStatus = (task: AgentTaskLike): AgentDotStatus =>
  getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt);

export function computeWorkspaceDotStatus<T extends AgentTaskLike>(
  tasks: ReadonlyArray<T>,
  resolveDotStatus: (task: T) => AgentDotStatus = resolveBaseDotStatus,
): WorkspaceDotStatus {
  const activeTasks = tasks.filter((task) => !task.isDeleted && !task.isArchived);

  if (activeTasks.length === 0) {
    return EMPTY_WORKSPACE_DOT_STATUS;
  }

  const hasError = activeTasks.some((task) => resolveDotStatus(task) === "error");
  const hasWaiting = activeTasks.some((task) => task.status === TaskStatus.WAITING);
  const hasRunning = activeTasks.some(
    (task) => task.status === TaskStatus.RUNNING || task.status === TaskStatus.BUILDING,
  );
  const isAllError = activeTasks.every((task) => resolveDotStatus(task) === "error");
  const hasUnread = activeTasks.some((task) => resolveDotStatus(task) === "unread");

  return { hasError, hasWaiting, hasRunning, isAllError, hasUnread };
}
