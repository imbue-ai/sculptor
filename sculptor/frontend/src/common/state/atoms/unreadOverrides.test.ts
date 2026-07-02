import { createStore } from "jotai";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { taskAtomFamily } from "./tasks";
import {
  clearUnreadOverride,
  isUnreadOverrideActive,
  markAgentUnreadAtom,
  resetUnreadOverridesForTesting,
  setUnreadOverride,
} from "./unreadOverrides";

const { mockMarkWorkspaceAgentUnread } = vi.hoisted(() => ({
  mockMarkWorkspaceAgentUnread: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    markWorkspaceAgentUnread: mockMarkWorkspaceAgentUnread,
  };
});

const UPDATED_AT = "2024-01-01T00:00:00Z";
const LATER_UPDATED_AT = "2024-01-01T00:05:00Z";

const createMockTask = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: "task-1",
    updatedAt: UPDATED_AT,
    lastReadAt: "2024-01-01T00:01:00Z",
    isDeleted: false,
    ...overrides,
  }) as CodingAgentTaskView;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

beforeEach(() => {
  resetUnreadOverridesForTesting();
  mockMarkWorkspaceAgentUnread.mockReset();
  mockMarkWorkspaceAgentUnread.mockResolvedValue(undefined);
});

describe("unread override lifecycle", () => {
  it("is inactive for a task that was never marked", () => {
    expect(isUnreadOverrideActive("task-1", UPDATED_AT)).toBe(false);
  });

  it("is active while the task's updatedAt matches the value recorded at mark time", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    expect(isUnreadOverrideActive("task-1", UPDATED_AT)).toBe(true);
  });

  it("expires when the task's updatedAt advances (a new agent turn)", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    expect(isUnreadOverrideActive("task-1", LATER_UPDATED_AT)).toBe(false);
  });

  it("clears on clearUnreadOverride (a fresh activation of the agent)", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    clearUnreadOverride("task-1");
    expect(isUnreadOverrideActive("task-1", UPDATED_AT)).toBe(false);
  });

  it("tracks each task independently", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    setUnreadOverride("task-2", UPDATED_AT);
    clearUnreadOverride("task-1");
    expect(isUnreadOverrideActive("task-1", UPDATED_AT)).toBe(false);
    expect(isUnreadOverrideActive("task-2", UPDATED_AT)).toBe(true);
  });
});

describe("markAgentUnreadAtom", () => {
  it("records the override, clears lastReadAt optimistically, and persists", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), createMockTask());

    store.set(markAgentUnreadAtom, { workspaceId: "ws-1", taskId: "task-1" });

    expect(isUnreadOverrideActive("task-1", UPDATED_AT)).toBe(true);
    expect(store.get(taskAtomFamily("task-1"))?.lastReadAt).toBeNull();
    expect(mockMarkWorkspaceAgentUnread).toHaveBeenCalledWith({
      path: { workspace_id: "ws-1", agent_id: "task-1" },
    });
  });

  it("keys the override to the task's updatedAt at mark time", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), createMockTask());

    store.set(markAgentUnreadAtom, { workspaceId: "ws-1", taskId: "task-1" });

    // A later turn expires the override without an explicit clear.
    expect(isUnreadOverrideActive("task-1", LATER_UPDATED_AT)).toBe(false);
  });

  it("preserves the other task fields on the optimistic update", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), createMockTask({ title: "My agent" }));

    store.set(markAgentUnreadAtom, { workspaceId: "ws-1", taskId: "task-1" });

    const task = store.get(taskAtomFamily("task-1"));
    expect(task?.title).toBe("My agent");
    expect(task?.updatedAt).toBe(UPDATED_AT);
  });

  it("does nothing for an unknown task", () => {
    const store = createStore();

    store.set(markAgentUnreadAtom, { workspaceId: "ws-1", taskId: "missing-task" });

    expect(isUnreadOverrideActive("missing-task", UPDATED_AT)).toBe(false);
    expect(mockMarkWorkspaceAgentUnread).not.toHaveBeenCalled();
  });

  it("keeps the optimistic state when the persist call rejects (fire-and-forget)", async () => {
    mockMarkWorkspaceAgentUnread.mockRejectedValue(new Error("network down"));
    const store = createStore();
    store.set(taskAtomFamily("task-1"), createMockTask());

    store.set(markAgentUnreadAtom, { workspaceId: "ws-1", taskId: "task-1" });
    await flushMicrotasks();

    expect(isUnreadOverrideActive("task-1", UPDATED_AT)).toBe(true);
    expect(store.get(taskAtomFamily("task-1"))?.lastReadAt).toBeNull();
  });
});
