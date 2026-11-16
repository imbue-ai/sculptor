import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView, Workspace } from "~/api";
import { ElementIds, LlmModel, WorkspaceInitializationStrategy } from "~/api";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { activeWorkspaceIdAtom } from "~/pages/workspace/layout/atoms/section.ts";

import { CommitButton } from "./CommitButton.tsx";

// The commit prompt is sent over HTTP; stub only that call so the request's target can be asserted.
const { sendMessagesMock } = vi.hoisted(() => ({ sendMessagesMock: vi.fn() }));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, sendWorkspaceAgentMessages: sendMessagesMock };
});

const WS = "ws-shown";
const WS_OTHER = "ws-other";

type StoreType = ReturnType<typeof createStore>;

const seedChatAgent = (store: StoreType, inputs: { agentId: string; workspaceId: string }): void => {
  store.set(workspaceAtomFamily(inputs.workspaceId), {
    objectId: inputs.workspaceId,
    projectId: "proj-1",
    initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
    targetBranch: "origin/main",
  } as Workspace);
  const agent = {
    id: inputs.agentId,
    workspaceId: inputs.workspaceId,
    isDeleted: false,
    model: LlmModel.CLAUDE_4_SONNET,
    harnessCapabilities: { supportsChatInterface: true },
  } as unknown as CodingAgentTaskView;
  store.set(agentAtomFamily(agent.id), agent);
  store.set(agentIdsAtom, [...(store.get(agentIdsAtom) ?? []), agent.id]);
};

const renderCommitButton = (store: StoreType, workspaceId: string): void => {
  render(
    <Provider store={store}>
      <Theme>
        <CommitButton workspaceId={workspaceId} changesCount={2} />
      </Theme>
    </Provider>,
  );
};

afterEach(() => {
  cleanup();
  sendMessagesMock.mockReset();
  localStorage.clear();
});

describe("CommitButton", () => {
  it("is enabled for its workspace's agent when no desktop shell has set the active workspace", () => {
    const store = createStore();
    seedChatAgent(store, { agentId: "agent-shown", workspaceId: WS });

    renderCommitButton(store, WS);

    expect(screen.getByTestId(ElementIds.CHANGES_COMMIT_BUTTON)).toBeEnabled();
  });

  it("sends the commit prompt to its workspace's agent, not the active workspace's", async () => {
    const store = createStore();
    seedChatAgent(store, { agentId: "agent-shown", workspaceId: WS });
    seedChatAgent(store, { agentId: "agent-other", workspaceId: WS_OTHER });
    store.set(activeWorkspaceIdAtom, WS_OTHER);

    renderCommitButton(store, WS);
    await userEvent.click(screen.getByTestId(ElementIds.CHANGES_COMMIT_BUTTON));

    await waitFor(() => expect(sendMessagesMock).toHaveBeenCalledTimes(1));
    expect(sendMessagesMock.mock.calls[0]?.[0]).toMatchObject({
      path: { workspace_id: WS, agent_id: "agent-shown" },
    });
  });
});
