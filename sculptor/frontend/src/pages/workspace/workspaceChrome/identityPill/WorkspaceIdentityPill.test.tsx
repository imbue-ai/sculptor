import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it } from "vitest";

import type { Workspace } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { workspaceBranchAtomFamily } from "~/common/state/atoms/workspaceBranch.ts";
import { workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { WorkspaceIdentityPill } from "./WorkspaceIdentityPill.tsx";

const setWorkspace = (
  store: ReturnType<typeof createStore>,
  initializationStrategy: WorkspaceInitializationStrategy,
): void => {
  const workspace: Workspace = {
    objectId: "ws1",
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "My workspace",
    initializationStrategy,
    sourceBranch: "main",
    requestedBranchName: "dev/feature",
  };
  store.set(workspaceAtomFamily("ws1"), workspace);
};

afterEach(() => {
  cleanup();
});

describe("WorkspaceIdentityPill", () => {
  it("shows a git workspace's branch and copies it on click", async () => {
    const user = userEvent.setup();
    const store = createStore();
    setWorkspace(store, WorkspaceInitializationStrategy.WORKTREE);
    store.set(workspaceBranchAtomFamily("ws1"), { workspaceId: "ws1", currentBranch: "dev/feature" });

    renderWithProviders(<WorkspaceIdentityPill workspaceId="ws1" />, { store });
    await user.click(screen.getByTestId(ElementIds.BRANCH_NAME));

    expect(screen.queryByTestId(ElementIds.JJ_IDENTITY_PILL)).toBeNull();
    expect(await navigator.clipboard.readText()).toBe("dev/feature");
  });

  it("shows a jj workspace's bookmark pill", () => {
    const store = createStore();
    setWorkspace(store, WorkspaceInitializationStrategy.JJ_WORKSPACE);
    store.set(workspaceJjStateAtomFamily("ws1"), {
      workspaceId: "ws1",
      workingCopyChangeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
      workingCopyChangeIdPrefixLength: 2,
      workingCopyDescription: "",
      isWorkingCopyEmpty: true,
      bookmarks: ["dev/feature"],
      primaryBookmark: "dev/feature",
      unbookmarkedRevisionCount: 0,
      hasConflict: false,
      isDivergent: false,
      isWorkingCopyStale: false,
    });

    renderWithProviders(<WorkspaceIdentityPill workspaceId="ws1" />, { store });

    expect(screen.getByTestId(ElementIds.JJ_IDENTITY_PILL).textContent).toContain("dev/feature");
    expect(screen.queryByTestId(ElementIds.BRANCH_NAME)).toBeNull();
  });
});
