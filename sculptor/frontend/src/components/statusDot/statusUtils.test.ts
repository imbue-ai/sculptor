import { describe, expect, it } from "vitest";

import { TaskStatus } from "~/api";

import { computeWorkspaceDotStatus, getAgentDotStatus } from "./statusUtils";

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

describe("computeWorkspaceDotStatus", () => {
  it("flags a workspace as unread when an agent has unseen updates", () => {
    expect(computeWorkspaceDotStatus([unreadTask("agent-1")]).hasUnread).toBe(true);
  });

  it("does not flag a workspace whose only unread agent is the focused one", () => {
    expect(computeWorkspaceDotStatus([unreadTask("agent-1")], "agent-1").hasUnread).toBe(false);
  });

  it("still flags unread agents in the workspace that are not focused", () => {
    // The focused agent lives in another workspace; this workspace's agent is
    // genuinely unread and must keep its indicator.
    expect(computeWorkspaceDotStatus([unreadTask("agent-1")], "agent-in-other-workspace").hasUnread).toBe(true);
  });
});
