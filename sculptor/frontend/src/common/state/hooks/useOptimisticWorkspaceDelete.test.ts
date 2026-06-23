import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { Workspace } from "../../../api";
import { workspaceDeleteErrorToastAtom } from "../atoms/toasts";
import { updateWorkspacesAtom } from "../atoms/workspaces";
import { useOptimisticWorkspaceDelete } from "./useOptimisticWorkspaceDelete";

// Mock the delete endpoint so we can force failures and inspect retry targets.
const { mockDeleteWorkspace } = vi.hoisted(() => ({
  mockDeleteWorkspace: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    deleteWorkspace: mockDeleteWorkspace,
    // updateWorkspacesAtom hydration path may PATCH; keep it inert.
    updateWorkspace: vi.fn().mockResolvedValue({ data: {} }),
    batchUpdateOpenState: vi.fn().mockResolvedValue({ data: {} }),
  };
});

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const mockWorkspace = (objectId: string): Workspace =>
  ({
    objectId,
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "",
    initializationStrategy: "CLONE",
    isOpen: true,
    isDeleted: false,
  }) as Workspace;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useOptimisticWorkspaceDelete", () => {
  it("retries the workspace captured per-call, not the most recently failed workspace", async () => {
    // Regression for the shared-ref bug: the toast's Retry used to re-delete
    // whichever workspace failed most recently, so retrying the FIRST failure
    // would wrongly target the SECOND workspace.
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A"), mockWorkspace("ws-B")]);

    const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
      createElement(Provider, { store }, children);

    const { result } = renderHook(() => useOptimisticWorkspaceDelete({ onNavigateAfterDelete: vi.fn() }), { wrapper });

    // Both initial deletes reject -> two error toasts (each set on the same atom).
    mockDeleteWorkspace.mockRejectedValue(new Error("network"));

    result.current.execute("ws-A", "Workspace A");
    await flushMicrotasks();
    const firstRetry = store.get(workspaceDeleteErrorToastAtom)?.action?.handleClick;

    result.current.execute("ws-B", "Workspace B");
    await flushMicrotasks();
    const secondRetry = store.get(workspaceDeleteErrorToastAtom)?.action?.handleClick;

    expect(firstRetry).toBeDefined();
    expect(secondRetry).toBeDefined();
    expect(firstRetry).not.toBe(secondRetry);

    mockDeleteWorkspace.mockClear();
    mockDeleteWorkspace.mockResolvedValue(undefined);

    // Invoke the FIRST failure's Retry. It must re-delete ws-A, not ws-B.
    // (The catch's rollback restored ws-A so the optimistic re-delete proceeds.)
    firstRetry!();
    await flushMicrotasks();

    expect(mockDeleteWorkspace).toHaveBeenCalledTimes(1);
    expect(mockDeleteWorkspace).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ workspace_id: "ws-A" }) }),
    );
  });
});
