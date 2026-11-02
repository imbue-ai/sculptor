import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RecentWorkspaceResponse, Workspace } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { workspaceBranchAtomFamily } from "~/common/state/atoms/workspaceBranch.ts";
import { updateWorkspacesAtom } from "~/common/state/atoms/workspaces.ts";
import { recentWorkspacesQueryKey } from "~/common/state/queryClient.ts";

import { RecentWorkspaces } from "./RecentWorkspaces.tsx";

type Store = ReturnType<typeof createStore>;

type WorkspaceFixture = {
  id: string;
  description: string;
  requestedBranchName: string | null;
  listedBranch: string | null;
};

// Every fixture was created from `main`; none of them is on it.
const SOURCE_BRANCH = "main";

const listed = (fixture: WorkspaceFixture): RecentWorkspaceResponse => ({
  objectId: fixture.id,
  projectId: "proj-1",
  description: fixture.description,
  initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
  sourceBranch: SOURCE_BRANCH,
  isDeleted: false,
  createdAt: "2024-01-01T00:00:00.000Z",
  projectName: "repo",
  agentCount: 0,
  isOpen: false,
  lastActivityAt: "2024-01-01T00:00:00.000Z",
  currentBranch: fixture.listedBranch,
});

const streamed = (fixture: WorkspaceFixture): Workspace => ({
  objectId: fixture.id,
  projectId: "proj-1",
  organizationReference: "org-1",
  description: fixture.description,
  initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
  sourceBranch: SOURCE_BRANCH,
  requestedBranchName: fixture.requestedBranchName,
  isOpen: false,
});

const renderRecentWorkspaces = (store: Store, fixtures: ReadonlyArray<WorkspaceFixture>): void => {
  store.set(updateWorkspacesAtom, fixtures.map(streamed));
  // A client of its own, seeded with the listing, so the list renders without
  // a fetch and the component's invalidations (on the app client) leave it be.
  const listingClient = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  listingClient.setQueryData(recentWorkspacesQueryKey(), fixtures.map(listed));
  render(
    <QueryClientProvider client={listingClient}>
      <Provider store={store}>
        <Theme>
          <RecentWorkspaces
            searchInputRef={createRef<HTMLInputElement>()}
            onWorkspaceClick={vi.fn()}
            onOpenInNewTab={vi.fn()}
            onEscapeToTitle={vi.fn()}
          />
        </Theme>
      </Provider>
    </QueryClientProvider>,
  );
};

const search = (query: string): void => {
  fireEvent.change(screen.getByTestId(ElementIds.WORKSPACE_SEARCH_INPUT), { target: { value: query } });
};

const visibleRowNames = (): Array<string> =>
  screen.queryAllByTestId(ElementIds.WORKSPACE_ROW).map((row) => row.querySelector("span")?.textContent ?? "");

afterEach(() => {
  cleanup();
});

describe("RecentWorkspaces search", () => {
  const renderThreeWorkspaces = (): void => {
    const store = createStore();
    store.set(workspaceBranchAtomFamily("ws-live"), { currentBranch: "dev/streamed", workspaceId: "ws-live" });
    renderRecentWorkspaces(store, [
      { id: "ws-live", description: "Streamed", requestedBranchName: "dev/old-name", listedBranch: null },
      { id: "ws-listed", description: "Listed", requestedBranchName: null, listedBranch: "dev/listed" },
      { id: "ws-requested", description: "Requested", requestedBranchName: "dev/requested", listedBranch: null },
    ]);
  };

  it("finds a workspace by the branch its row shows", () => {
    renderThreeWorkspaces();

    search("dev/streamed");
    expect(visibleRowNames()).toEqual(["Streamed"]);

    search("dev/listed");
    expect(visibleRowNames()).toEqual(["Listed"]);

    search("dev/requested");
    expect(visibleRowNames()).toEqual(["Requested"]);
  });

  it("does not find a workspace by a requested name its branch has replaced", () => {
    renderThreeWorkspaces();

    search("dev/old-name");

    expect(visibleRowNames()).toEqual([]);
  });

  it("does not find a workspace by the branch it was created from", () => {
    renderThreeWorkspaces();

    search(SOURCE_BRANCH);

    expect(visibleRowNames()).toEqual([]);
  });
});
