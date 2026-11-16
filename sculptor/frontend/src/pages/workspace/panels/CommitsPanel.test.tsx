import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import type { RevisionHistoryResponse, RevisionInfo, Workspace } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { invalidateWorkspaceGitQueries, queryClient } from "~/common/state/queryClient.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";
import { activeWorkspaceIdAtom } from "~/pages/workspace/layout/atoms/section.ts";

import { CommitsPanel } from "./CommitsPanel.tsx";

const { mockGetWorkspaceRevisions, mockGetWorkspaceCommits, mockGetWorkspaceCommitDiff } = vi.hoisted(() => ({
  mockGetWorkspaceRevisions: vi.fn(),
  mockGetWorkspaceCommits: vi.fn(),
  mockGetWorkspaceCommitDiff: vi.fn(),
}));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return {
    ...actual,
    getWorkspaceRevisions: mockGetWorkspaceRevisions,
    getWorkspaceCommits: mockGetWorkspaceCommits,
    getWorkspaceCommitDiff: mockGetWorkspaceCommitDiff,
  };
});

const WORKSPACE_ID = "ws-commits-panel";
const FORK_POINT = "9876543210fedcba9876543210fedcba98765432";
const CHANGE_ID = "dddddddddddddddddddddddddddddddd";

const describedRevision = (commitId: string): RevisionInfo => ({
  changeId: CHANGE_ID,
  changeIdPrefixLength: 1,
  commitId,
  description: "Add notes",
  authorName: "Ada Lovelace",
  timestamp: new Date().toISOString(),
  parentCommitIds: [FORK_POINT],
  files: [{ path: "notes.md", status: "A", oldPath: null, additions: 1, deletions: 0 }],
  bookmarks: ["dev/notes"],
  isWorkingCopy: true,
  isEmpty: false,
  hasConflict: false,
  isDivergent: false,
});

const historyAt = (commitId: string): RevisionHistoryResponse => ({
  revisions: [describedRevision(commitId)],
  forkPoint: FORK_POINT,
});

const renderPanel = (initializationStrategy: WorkspaceInitializationStrategy): void => {
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
  store.set(activeWorkspaceIdAtom, WORKSPACE_ID);
  // The viewer's file menu reads the workspace from the route.
  renderWithProviders(
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route path="/ws/:workspaceID" element={<CommitsPanel />} />
      </Routes>
    </QueryClientProvider>,
    { store, initialEntries: [`/ws/${WORKSPACE_ID}`] },
  );
};

const commitDiffFor = (filePath: string): string =>
  `diff --git a/${filePath} b/${filePath}\nnew file mode 100644\n--- /dev/null\n+++ b/${filePath}\n@@ -0,0 +1 @@\n+notes\n`;

beforeEach(() => {
  mockGetWorkspaceCommits.mockResolvedValue({ data: { commits: [], forkPoint: FORK_POINT } });
  mockGetWorkspaceCommitDiff.mockImplementation(({ query }: { query: { commit_hash: string } }) =>
    Promise.resolve({ data: { diff: commitDiffFor("notes.md"), commitHash: query.commit_hash, parentHash: null } }),
  );
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  queryClient.clear();
});

describe("CommitsPanel", () => {
  it("lists a jj workspace's revisions and never asks for its commits", async () => {
    mockGetWorkspaceRevisions.mockResolvedValue({ data: historyAt("1111111111111111111111111111111111111111") });

    renderPanel(WorkspaceInitializationStrategy.JJ_WORKSPACE);

    const row = await screen.findByTestId(ElementIds.REVISION_ENTRY);
    expect(within(row).getByText("Add notes")).toBeTruthy();
    expect(screen.getByTestId(ElementIds.REVISIONS_FORK_POINT).textContent).toBe("fork point (main@origin · 98765432)");
    expect(mockGetWorkspaceCommits).not.toHaveBeenCalled();
  });

  it("lists a git workspace's commits and never asks for revisions", async () => {
    renderPanel(WorkspaceInitializationStrategy.WORKTREE);

    expect(await screen.findByTestId(ElementIds.HISTORY_TERMINUS)).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.REVISION_ENTRY)).toBeNull();
    expect(mockGetWorkspaceRevisions).not.toHaveBeenCalled();
  });

  it("follows a selected file's revision to the commit jj rewrites it to", async () => {
    const user = userEvent.setup();
    const firstCommitId = "1111111111111111111111111111111111111111";
    const rewrittenCommitId = "2222222222222222222222222222222222222222";
    mockGetWorkspaceRevisions.mockResolvedValue({ data: historyAt(firstCommitId) });
    renderPanel(WorkspaceInitializationStrategy.JJ_WORKSPACE);

    const row = await screen.findByTestId(ElementIds.REVISION_ENTRY);
    await user.click(within(row).getByText("Add notes"));
    await user.click(within(row).getByTestId(ElementIds.FILE_BROWSER_TREE_ROW));

    await waitFor(() =>
      expect(mockGetWorkspaceCommitDiff).toHaveBeenCalledWith(
        expect.objectContaining({ query: { commit_hash: firstCommitId } }),
      ),
    );

    mockGetWorkspaceRevisions.mockResolvedValue({ data: historyAt(rewrittenCommitId) });
    act(() => invalidateWorkspaceGitQueries(WORKSPACE_ID));

    await waitFor(() =>
      expect(mockGetWorkspaceCommitDiff).toHaveBeenCalledWith(
        expect.objectContaining({ query: { commit_hash: rewrittenCommitId } }),
      ),
    );
  });
});
