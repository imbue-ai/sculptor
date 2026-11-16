import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "~/api";
import type { Project, Workspace } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";
import { projectAtomFamily } from "~/common/state/atoms/projects.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { workspaceSetupStatusAtomFamily } from "~/common/state/atoms/workspaceSetupStatus.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { SetupStatusCard } from "./SetupStatusCard.tsx";

const GIT_DEFAULT = "git fetch origin 2>/dev/null || true";
const JJ_DEFAULT = "jj git fetch --remote origin 2>/dev/null || true";

// Each workspace kind's default setup command comes from the backend.
vi.mock("~/api", async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  getWorkspaceSetupCommandDefaults: vi.fn(async () => ({
    data: {
      defaultSetupCommandByInitializationStrategy: {
        IN_PLACE: null,
        CLONE: GIT_DEFAULT,
        WORKTREE: GIT_DEFAULT,
        JJ_WORKSPACE: JJ_DEFAULT,
      },
    },
  })),
}));

const renderFinishedSetup = (inputs: {
  kind: WorkspaceInitializationStrategy;
  commandThatRan: string;
  projectCommand: string | null;
}): void => {
  const store = createStore();
  store.set(workspaceAtomFamily("w1"), {
    objectId: "w1",
    projectId: "p1",
    initializationStrategy: inputs.kind,
    setupCommand: inputs.commandThatRan,
  } as Workspace);
  store.set(projectAtomFamily("p1"), { objectId: "p1", workspaceSetupCommand: inputs.projectCommand } as Project);
  store.set(workspaceSetupStatusAtomFamily("w1"), { status: "succeeded", runId: "run-1", startedAt: 1, finishedAt: 2 });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  renderWithProviders(
    <QueryClientProvider client={queryClient}>
      <SetupStatusCard workspaceId="w1" />
    </QueryClientProvider>,
    { store },
  );
};

afterEach(() => {
  cleanup();
});

describe("SetupStatusCard", () => {
  it.each([
    { kind: WorkspaceInitializationStrategy.WORKTREE, commandThatRan: GIT_DEFAULT },
    { kind: WorkspaceInitializationStrategy.JJ_WORKSPACE, commandThatRan: JJ_DEFAULT },
  ])("says nothing changed when a $kind workspace ran its own kind's default", async ({ kind, commandThatRan }) => {
    renderFinishedSetup({ kind, commandThatRan, projectCommand: null });

    expect(await screen.findByTestId("setup-rerun-button")).toHaveAttribute("data-command-changed", "false");
  });

  it("says the command changed when a jj workspace ran the git default", async () => {
    renderFinishedSetup({
      kind: WorkspaceInitializationStrategy.JJ_WORKSPACE,
      commandThatRan: GIT_DEFAULT,
      projectCommand: null,
    });

    expect(await screen.findByTestId("setup-rerun-button")).toHaveAttribute("data-command-changed", "true");
  });

  it("compares against the project's own command when it has one", async () => {
    renderFinishedSetup({
      kind: WorkspaceInitializationStrategy.JJ_WORKSPACE,
      commandThatRan: JJ_DEFAULT,
      projectCommand: "make setup",
    });

    expect(await screen.findByTestId("setup-rerun-button")).toHaveAttribute("data-command-changed", "true");
  });
});
