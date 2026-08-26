import { describe, expect, it } from "vitest";

import { TaskStatus } from "~/api";

import type { AgentDotStatus } from "./statusUtils";
import {
  computeWorkspaceDotStatus,
  getAgentDotStatus,
  getWorkspaceAttentionRank,
  WORKSPACE_ATTENTION_TIER,
} from "./statusUtils";

// An agent whose content changed after the last recorded read — the raw
// timestamp comparison classifies it as "unread".
const READ_AT = "2024-01-01T00:00:00.000Z";
const UPDATED_AT_LATER = "2024-01-01T00:00:05.000Z";

type WorkspaceTask = {
  id: string;
  status: TaskStatus;
  lastReadAt: string | null;
  updatedAt: string;
};

const unreadTask = (id: string): WorkspaceTask => ({
  id,
  status: TaskStatus.READY,
  lastReadAt: READ_AT,
  updatedAt: UPDATED_AT_LATER,
});

describe("getAgentDotStatus", () => {
  it("reports an unfocused agent with newer content as unread", () => {
    expect(getAgentDotStatus(TaskStatus.READY, READ_AT, UPDATED_AT_LATER)).toBe("unread");
    expect(getAgentDotStatus(TaskStatus.READY, null, UPDATED_AT_LATER)).toBe("unread");
  });

  it("reports the focused agent as read when content is newer than the last read", () => {
    // Focused with a prior read timestamp: focus wins over a newer updatedAt.
    expect(getAgentDotStatus(TaskStatus.READY, READ_AT, UPDATED_AT_LATER, true)).toBe("read");
  });

  it("honors an explicit mark-unread on the focused agent", () => {
    // lastReadAt === null means the user marked it unread; that must win even
    // while the agent is focused, so focus does not override it back to read.
    expect(getAgentDotStatus(TaskStatus.READY, null, UPDATED_AT_LATER, true)).toBe("unread");
  });

  it("does not let focus override an in-flight or errored status", () => {
    expect(getAgentDotStatus(TaskStatus.RUNNING, null, UPDATED_AT_LATER, true)).toBe("running");
    expect(getAgentDotStatus(TaskStatus.BUILDING, null, UPDATED_AT_LATER, true)).toBe("running");
    expect(getAgentDotStatus(TaskStatus.WAITING, null, UPDATED_AT_LATER, true)).toBe("waiting");
    expect(getAgentDotStatus(TaskStatus.ERROR, null, UPDATED_AT_LATER, true)).toBe("error");
    // A request-level error still surfaces as "error" while focused — the
    // user should see it failed; it clears via the existing mark-read path.
    expect(getAgentDotStatus(TaskStatus.REQUEST_ERROR, READ_AT, UPDATED_AT_LATER, true)).toBe("error");
  });
});

// Focus reaches the workspace aggregate through the injectable per-task
// resolver (not a positional parameter): callers close over the viewed agent's
// id and map the match onto getAgentDotStatus's isFocused flag, exactly like
// the production resolvers in unreadOverrides.ts/workspaces.ts.
const resolveWithViewedAgent =
  (viewedAgentId: string) =>
  (task: WorkspaceTask): AgentDotStatus =>
    getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt, task.id === viewedAgentId);

describe("computeWorkspaceDotStatus", () => {
  it("flags a workspace as unread when an agent has unseen updates", () => {
    expect(computeWorkspaceDotStatus([unreadTask("agent-1")]).hasUnread).toBe(true);
  });

  it("does not flag a workspace whose only unread agent is the focused one", () => {
    expect(computeWorkspaceDotStatus([unreadTask("agent-1")], resolveWithViewedAgent("agent-1")).hasUnread).toBe(false);
  });

  it("still flags unread agents in the workspace that are not focused", () => {
    // The focused agent lives in another workspace; this workspace's agent is
    // genuinely unread and must keep its indicator.
    expect(
      computeWorkspaceDotStatus([unreadTask("agent-1")], resolveWithViewedAgent("agent-in-other-workspace")).hasUnread,
    ).toBe(true);
  });
});

const taskWith = (status: TaskStatus, lastReadAt: string | null, updatedAt: string): WorkspaceTask => ({
  id: `task-${status}-${String(lastReadAt)}`,
  status,
  lastReadAt,
  updatedAt,
});

describe("getWorkspaceAttentionRank", () => {
  it("ranks an empty / task-less workspace as IDLE", () => {
    expect(getWorkspaceAttentionRank([])).toBe(WORKSPACE_ATTENTION_TIER.IDLE);
  });

  it("ranks a waiting workspace at the top (WAITING)", () => {
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.WAITING, READ_AT, READ_AT)])).toBe(
      WORKSPACE_ATTENTION_TIER.WAITING,
    );
  });

  it("prefers WAITING over an un-acked error in the same workspace", () => {
    expect(
      getWorkspaceAttentionRank([
        taskWith(TaskStatus.ERROR, READ_AT, UPDATED_AT_LATER),
        taskWith(TaskStatus.WAITING, READ_AT, READ_AT),
      ]),
    ).toBe(WORKSPACE_ATTENTION_TIER.WAITING);
  });

  it("ranks an un-acked error (errored, not viewed since) as UNACKED_ERROR", () => {
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.ERROR, READ_AT, UPDATED_AT_LATER)])).toBe(
      WORKSPACE_ATTENTION_TIER.UNACKED_ERROR,
    );
    // Never read at all also counts as un-acked.
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.ERROR, null, UPDATED_AT_LATER)])).toBe(
      WORKSPACE_ATTENTION_TIER.UNACKED_ERROR,
    );
  });

  it("drops an acked (already-viewed) error to IDLE", () => {
    // Full ERROR stays red but was viewed after it broke (lastReadAt >= updatedAt).
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.ERROR, UPDATED_AT_LATER, READ_AT)])).toBe(
      WORKSPACE_ATTENTION_TIER.IDLE,
    );
  });

  it("treats a read REQUEST_ERROR as acked (IDLE), an unread one as un-acked", () => {
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.REQUEST_ERROR, UPDATED_AT_LATER, READ_AT)])).toBe(
      WORKSPACE_ATTENTION_TIER.IDLE,
    );
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.REQUEST_ERROR, READ_AT, UPDATED_AT_LATER)])).toBe(
      WORKSPACE_ATTENTION_TIER.UNACKED_ERROR,
    );
  });

  it("ranks an unread (non-error) reply as UNREAD", () => {
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.READY, READ_AT, UPDATED_AT_LATER)])).toBe(
      WORKSPACE_ATTENTION_TIER.UNREAD,
    );
  });

  it("ranks a running / building workspace as RUNNING", () => {
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.RUNNING, READ_AT, READ_AT)])).toBe(
      WORKSPACE_ATTENTION_TIER.RUNNING,
    );
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.BUILDING, READ_AT, READ_AT)])).toBe(
      WORKSPACE_ATTENTION_TIER.RUNNING,
    );
  });

  it("ranks a fully-read idle workspace as IDLE", () => {
    expect(getWorkspaceAttentionRank([taskWith(TaskStatus.READY, UPDATED_AT_LATER, READ_AT)])).toBe(
      WORKSPACE_ATTENTION_TIER.IDLE,
    );
  });
});
