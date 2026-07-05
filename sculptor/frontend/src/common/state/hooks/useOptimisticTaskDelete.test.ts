import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { taskAtomFamily, taskIdsAtom } from "../atoms/tasks";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { useOptimisticTaskDelete } from "./useOptimisticTaskDelete";

// Mock the delete endpoint so we can force failures and inspect retry targets.
const { mockDeleteWorkspaceAgent } = vi.hoisted(() => ({
  mockDeleteWorkspaceAgent: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    deleteWorkspaceAgent: mockDeleteWorkspaceAgent,
  };
});

vi.mock("~/common/hooks/navigation.ts", () => ({
  useImbueNavigate: (): Record<string, unknown> => ({ navigateToRoot: vi.fn() }),
  useImbueLocation: (): Record<string, unknown> => ({ isAgentRoute: false }),
  useImbueParams: (): Record<string, unknown> => ({ taskID: undefined }),
}));

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const createMockTask = (id: string): CodingAgentTaskView =>
  ({
    id,
    taskStatus: "RUNNING",
    isDeleted: false,
  }) as CodingAgentTaskView;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useOptimisticTaskDelete", () => {
  it("retries the task captured per-call, not the most recently failed task", async () => {
    // Regression for the shared-ref bug: the toast's Retry used to re-delete
    // whichever task failed most recently, so retrying the FIRST failure would
    // wrongly target the SECOND task.
    const store = createStore();
    store.set(taskIdsAtom, ["task-A", "task-B"]);
    store.set(taskAtomFamily("task-A"), createMockTask("task-A"));
    store.set(taskAtomFamily("task-B"), createMockTask("task-B"));

    const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
      createElement(Provider, { store }, children);

    const { result } = renderHook(() => useOptimisticTaskDelete({ workspaceId: "ws-1" }), { wrapper });

    // Both initial deletes reject -> two error toasts (each set on the same atom).
    mockDeleteWorkspaceAgent.mockRejectedValue(new Error("network"));

    result.current.execute("task-A", "Task A");
    await flushMicrotasks();
    const firstRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    result.current.execute("task-B", "Task B");
    await flushMicrotasks();
    const secondRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    expect(firstRetry).toBeDefined();
    expect(secondRetry).toBeDefined();
    expect(firstRetry).not.toBe(secondRetry);

    // Re-seed task-A so its optimistic re-delete proceeds to the API call.
    store.set(taskAtomFamily("task-A"), createMockTask("task-A"));
    store.set(taskIdsAtom, ["task-A"]);

    mockDeleteWorkspaceAgent.mockClear();
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    // Invoke the FIRST failure's Retry. It must re-delete task-A, not task-B.
    firstRetry!();
    await flushMicrotasks();

    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledTimes(1);
    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ agent_id: "task-A" }) }),
    );
  });
});
