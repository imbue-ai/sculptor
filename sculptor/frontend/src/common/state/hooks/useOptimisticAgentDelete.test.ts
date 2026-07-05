import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { agentAtomFamily, agentIdsAtom } from "../atoms/agents";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { useOptimisticAgentDelete } from "./useOptimisticAgentDelete";

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
  useImbueParams: (): Record<string, unknown> => ({ agentId: undefined }),
}));

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const createMockAgent = (id: string): CodingAgentTaskView =>
  ({
    id,
    status: "RUNNING",
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

describe("useOptimisticAgentDelete", () => {
  it("retries the agent captured per-call, not the most recently failed agent", async () => {
    // Regression for the shared-ref bug: the toast's Retry used to re-delete
    // whichever agent failed most recently, so retrying the FIRST failure would
    // wrongly target the SECOND agent.
    const store = createStore();
    store.set(agentIdsAtom, ["agent-A", "agent-B"]);
    store.set(agentAtomFamily("agent-A"), createMockAgent("agent-A"));
    store.set(agentAtomFamily("agent-B"), createMockAgent("agent-B"));

    const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
      createElement(Provider, { store }, children);

    const { result } = renderHook(() => useOptimisticAgentDelete({ workspaceId: "ws-1" }), { wrapper });

    // Both initial deletes reject -> two error toasts (each set on the same atom).
    mockDeleteWorkspaceAgent.mockRejectedValue(new Error("network"));

    result.current.execute("agent-A", "Agent A");
    await flushMicrotasks();
    const firstRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    result.current.execute("agent-B", "Agent B");
    await flushMicrotasks();
    const secondRetry = store.get(deleteErrorToastAtom)?.action?.handleClick;

    expect(firstRetry).toBeDefined();
    expect(secondRetry).toBeDefined();
    expect(firstRetry).not.toBe(secondRetry);

    // Re-seed agent-A so its optimistic re-delete proceeds to the API call.
    store.set(agentAtomFamily("agent-A"), createMockAgent("agent-A"));
    store.set(agentIdsAtom, ["agent-A"]);

    mockDeleteWorkspaceAgent.mockClear();
    mockDeleteWorkspaceAgent.mockResolvedValue(undefined);

    // Invoke the FIRST failure's Retry. It must re-delete agent-A, not agent-B.
    firstRetry!();
    await flushMicrotasks();

    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledTimes(1);
    expect(mockDeleteWorkspaceAgent).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ agent_id: "agent-A" }) }),
    );
  });
});
