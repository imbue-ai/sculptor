import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RecentWorkspaceResponse } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";

import { ClosedWorkspaceRow } from "./ClosedWorkspaceRow.tsx";

type Store = ReturnType<typeof createStore>;

const makeWorkspace = (
  strategy: WorkspaceInitializationStrategy,
  overrides: Partial<RecentWorkspaceResponse> = {},
): RecentWorkspaceResponse =>
  ({
    objectId: "ws-1",
    projectId: "proj-1",
    description: "My workspace",
    initializationStrategy: strategy,
    // Keep sourceBranch null and seed no branch info so displayBranch is falsy:
    // this avoids rendering the branch badge and PrButton, keeping the row
    // isolated to the metadata line under test.
    sourceBranch: null,
    isDeleted: false,
    projectName: "Core",
    agentCount: 1,
    lastActivityAt: "2024-01-01T00:00:00Z",
    ...overrides,
  }) as unknown as RecentWorkspaceResponse;

const renderRow = (workspace: RecentWorkspaceResponse, options: { store?: Store } = {}): void => {
  const store = options.store ?? createStore();
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>
        <MemoryRouter>{children}</MemoryRouter>
      </Theme>
    </Provider>
  );
  render(<ClosedWorkspaceRow workspace={workspace} onReopen={vi.fn()} onDelete={vi.fn()} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ClosedWorkspaceRow init-strategy label", () => {
  // Bug: WORKTREE workspaces were mislabeled "clone". The fix uses an
  // exhaustive Record mapping each WorkspaceInitializationStrategy to its label.
  it("labels a WORKTREE workspace as 'worktree', not 'clone'", () => {
    renderRow(makeWorkspace(WorkspaceInitializationStrategy.WORKTREE));
    const meta = screen.getByText(/agent/).textContent ?? "";
    expect(meta).toContain("worktree");
    expect(meta).not.toContain("clone");
  });

  it("labels a CLONE workspace as 'clone'", () => {
    renderRow(makeWorkspace(WorkspaceInitializationStrategy.CLONE));
    const meta = screen.getByText(/agent/).textContent ?? "";
    expect(meta).toContain("clone");
    expect(meta).not.toContain("worktree");
  });

  it("labels an IN_PLACE workspace as 'in-place'", () => {
    renderRow(makeWorkspace(WorkspaceInitializationStrategy.IN_PLACE));
    const meta = screen.getByText(/agent/).textContent ?? "";
    expect(meta).toContain("in-place");
  });
});
