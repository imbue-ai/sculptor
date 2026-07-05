import { TaskStatus } from "~/api";

/**
 * Visual status for a single agent's status dot.
 *
 * This is the single source of truth for how TaskStatus maps to a dot appearance.
 * All components showing an agent status dot should derive from this.
 */
export type AgentDotStatus = "running" | "waiting" | "error" | "unread" | "read";

const hasUnreadUpdate = (lastReadAt: string | null, updatedAt: string): boolean => {
  return lastReadAt === null || new Date(updatedAt) > new Date(lastReadAt);
};

export const getAgentDotStatus = (
  status: TaskStatus,
  lastReadAt: string | null,
  updatedAt: string,
  isFocused: boolean = false,
): AgentDotStatus => {
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
};

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

type AgentLike = {
  id: string;
  status: TaskStatus;
  lastReadAt: string | null;
  updatedAt: string;
  isDeleted?: boolean;
  isArchived?: boolean;
};

// Per-agent dot resolution used by the workspace aggregate. Injectable (and
// generic over the caller's agent type) so override-aware callers — the sidebar
// rows, matching the panel tabs' manual mark-as-unread — can substitute their
// resolver without this pure leaf module importing override state.
const resolveBaseDotStatus = (agent: AgentLike): AgentDotStatus =>
  getAgentDotStatus(agent.status, agent.lastReadAt, agent.updatedAt);

export const computeWorkspaceDotStatus = <T extends AgentLike>(
  agents: ReadonlyArray<T>,
  resolveDotStatus: (agent: T) => AgentDotStatus = resolveBaseDotStatus,
): WorkspaceDotStatus => {
  const activeAgents = agents.filter((agent) => !agent.isDeleted && !agent.isArchived);

  if (activeAgents.length === 0) {
    return EMPTY_WORKSPACE_DOT_STATUS;
  }

  const hasError = activeAgents.some((agent) => resolveDotStatus(agent) === "error");
  const hasWaiting = activeAgents.some((agent) => agent.status === TaskStatus.WAITING);
  const hasRunning = activeAgents.some(
    (agent) => agent.status === TaskStatus.RUNNING || agent.status === TaskStatus.BUILDING,
  );
  const isAllError = activeAgents.every((agent) => resolveDotStatus(agent) === "error");
  const hasUnread = activeAgents.some((agent) => resolveDotStatus(agent) === "unread");

  return { hasError, hasWaiting, hasRunning, isAllError, hasUnread };
};
