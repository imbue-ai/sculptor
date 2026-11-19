import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import type { RevisionHistoryResponse, Workspace } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { invalidateWorkspaceRevisionsQueries, queryClient } from "~/common/state/queryClient.ts";

import { useWorkspaceRevisions } from "./useWorkspaceRevisions.ts";

const { mockGetWorkspaceRevisions } = vi.hoisted(() => ({ mockGetWorkspaceRevisions: vi.fn() }));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return { ...actual, getWorkspaceRevisions: mockGetWorkspaceRevisions };
});

const WORKSPACE_ID = "ws-revisions";

const HISTORY: RevisionHistoryResponse = { revisions: [], forkPoint: "9876543210fedcba9876543210fedcba98765432" };

const renderRevisions = (
  initializationStrategy: WorkspaceInitializationStrategy,
): { result: { current: ReturnType<typeof useWorkspaceRevisions> } } => {
  const store = createStore();
  const workspace: Workspace = {
    objectId: WORKSPACE_ID,
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "Workspace",
    initializationStrategy,
    sourceBranch: "main@origin",
    targetBranch: "main@origin",
  };
  store.set(workspaceAtomFamily(WORKSPACE_ID), workspace);
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <QueryClientProvider client={queryClient}>
      <Provider store={store}>{children}</Provider>
    </QueryClientProvider>
  );
  return renderHook(() => useWorkspaceRevisions(WORKSPACE_ID), { wrapper });
};

afterEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
});

describe("useWorkspaceRevisions", () => {
  it("reads a jj workspace's revisions", async () => {
    mockGetWorkspaceRevisions.mockResolvedValue({ data: HISTORY });

    const { result } = renderRevisions(WorkspaceInitializationStrategy.JJ_WORKSPACE);

    await waitFor(() => expect(result.current.data).toEqual(HISTORY));
    expect(mockGetWorkspaceRevisions).toHaveBeenCalledWith(
      expect.objectContaining({ path: { workspace_id: WORKSPACE_ID } }),
    );
  });

  it("reads the revisions again once they are invalidated", async () => {
    mockGetWorkspaceRevisions.mockResolvedValue({ data: HISTORY });
    const { result } = renderRevisions(WorkspaceInitializationStrategy.JJ_WORKSPACE);
    await waitFor(() => expect(result.current.data).toEqual(HISTORY));

    invalidateWorkspaceRevisionsQueries(WORKSPACE_ID);

    await waitFor(() => expect(mockGetWorkspaceRevisions).toHaveBeenCalledTimes(2));
  });

  it("asks nothing of a git workspace, which has commits instead", () => {
    const { result } = renderRevisions(WorkspaceInitializationStrategy.WORKTREE);

    expect(result.current.data).toBeUndefined();
    expect(mockGetWorkspaceRevisions).not.toHaveBeenCalled();
  });
});
