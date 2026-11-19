import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView, UserConfig, Workspace } from "~/api";
import { LlmModel, WorkspaceInitializationStrategy } from "~/api";
import type * as NavigationModule from "~/common/hooks/navigation.ts";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents.ts";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { ChangesPill } from "./ChangesPill.tsx";

const WS = "ws-mobile";

// What is under test is the "+ PR" control, so the route and the diff data the
// pill summarises are stubbed at their module seams: one changed file, so the
// pill shows. The send API is stubbed so the prompt's destination can be asserted.
vi.mock("~/common/hooks/navigation.ts", async (importOriginal) => ({
  ...(await importOriginal<typeof NavigationModule>()),
  useWorkspacePageParams: (): unknown => ({ workspaceID: WS }),
}));
vi.mock("~/pages/workspace/panels/fileBrowser/fileDiffMaps.ts", () => ({
  useFileStatusMap: (): Map<string, string> => new Map([["a.txt", "modified"]]),
  usePerFileDiffMap: (): Map<string, unknown> => new Map([["a.txt", { addedLines: 1, removedLines: 0 }]]),
}));
vi.mock("~/pages/workspace/panels/fileBrowser/useFileTree.ts", () => ({
  useFileTree: (): unknown => ({ tree: [] }),
}));
const { sendMessagesMock } = vi.hoisted(() => ({ sendMessagesMock: vi.fn() }));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, sendWorkspaceAgentMessages: sendMessagesMock };
});

const renderPill = (inputs: { hasAgent: boolean }): void => {
  const store = createStore();
  store.set(workspaceAtomFamily(WS), {
    objectId: WS,
    projectId: "proj-1",
    initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
    targetBranch: "origin/main",
  } as Workspace);
  store.set(prStatusAtomFamily(WS), { workspaceId: WS, prState: "none" });
  store.set(userConfigAtom, { prCreationPrompt: "Open a pull request" } as UserConfig);
  if (inputs.hasAgent) {
    // The mobile shell shows one agent without seeding the panel layout.
    store.set(agentAtomFamily("agent-1"), {
      id: "agent-1",
      workspaceId: WS,
      isDeleted: false,
      model: LlmModel.CLAUDE_4_SONNET,
      harnessCapabilities: { supportsChatInterface: true },
    } as unknown as CodingAgentTaskView);
    store.set(agentIdsAtom, ["agent-1"]);
  }
  renderWithProviders(<ChangesPill onReviewAll={vi.fn()} />, { store });
};

afterEach(() => {
  cleanup();
  sendMessagesMock.mockReset();
  localStorage.clear();
});

describe("ChangesPill's + PR control", () => {
  it("is disabled, as the desktop Create PR is, while no agent can take the prompt", () => {
    renderPill({ hasAgent: false });

    expect(screen.getByRole("button", { name: "PR" })).toBeDisabled();
  });

  it("sends the pull request prompt when the shared rule allows it", async () => {
    renderPill({ hasAgent: true });

    const createPr = screen.getByRole("button", { name: "PR" });
    expect(createPr).toBeEnabled();
    fireEvent.click(createPr);

    await waitFor(() => expect(sendMessagesMock).toHaveBeenCalledTimes(1));
    expect(sendMessagesMock.mock.calls[0]?.[0]).toMatchObject({
      path: { workspace_id: WS, agent_id: "agent-1" },
      body: { message: "Open a pull request\n\nTarget the pull request against `origin/main`." },
    });
  });
});
