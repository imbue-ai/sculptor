import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it } from "vitest";

import type { Workspace } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { queryClient } from "~/common/state/queryClient.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { ChatAgentProvider } from "./ChatAgentContext.tsx";
import { ChatIntro } from "./ChatIntro.tsx";

const renderIntro = (initializationStrategy: WorkspaceInitializationStrategy): void => {
  const store = createStore();
  const workspace: Workspace = {
    objectId: "ws1",
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "My workspace",
    initializationStrategy,
    sourceBranch: "main@origin",
    requestedBranchName: "dev/feature",
  };
  store.set(workspaceAtomFamily("ws1"), workspace);
  renderWithProviders(
    <QueryClientProvider client={queryClient}>
      <ChatAgentProvider workspaceId="ws1" agentId="agent-1">
        <ChatIntro />
      </ChatAgentProvider>
    </QueryClientProvider>,
    { store },
  );
};

afterEach(() => {
  cleanup();
});

describe("ChatIntro", () => {
  it("tells the user that a jj workspace has no git inside", () => {
    renderIntro(WorkspaceInitializationStrategy.JJ_WORKSPACE);

    const intro = screen.getByTestId(ElementIds.ALPHA_CHAT_INTRO);
    expect(intro.textContent).toContain("jj workspace on main@origin");
    expect(intro.textContent).toContain("This workspace has no git inside. Agents use jj for version control here.");
  });

  it("says nothing about jj in a git workspace", () => {
    renderIntro(WorkspaceInitializationStrategy.WORKTREE);

    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_INTRO).textContent).not.toContain("no git inside");
  });
});
