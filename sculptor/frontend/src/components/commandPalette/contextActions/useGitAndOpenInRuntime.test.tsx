import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView, UserConfig, Workspace } from "~/api";
import { LlmModel, TaskStatus, WorkspaceInitializationStrategy } from "~/api";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents.ts";
import { chatActionsAtom } from "~/common/state/atoms/chatActions.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { workspaceLayoutFamily } from "~/pages/workspace/layout/atoms/section.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { makeAgentPanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";

import { useGitAndOpenInRuntime } from "./useGitAndOpenInRuntime.ts";

// The send APIs hit the backend; stub them so the prompt's destination can be
// asserted deterministically.
const { sendMessagesMock, terminalInputMock } = vi.hoisted(() => ({
  sendMessagesMock: vi.fn(),
  terminalInputMock: vi.fn(),
}));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, sendWorkspaceAgentMessages: sendMessagesMock, postAgentTerminalInput: terminalInputMock };
});

const VIEWED_WS = "ws-viewed";
const CLICKED_WS = "ws-clicked";
const COMMIT_PROMPT = "Commit everything";
const PR_PROMPT = "Open a pull request";

type StoreType = ReturnType<typeof createStore>;

const makeWorkspace = (objectId: string, targetBranch: string | null): Workspace => ({
  objectId,
  createdAt: "2024-01-01T00:00:00Z",
  updatedAt: "2024-01-01T00:00:00Z",
  projectId: "proj-1",
  organizationReference: "org-1",
  description: objectId,
  initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
  sourceBranch: "main",
  sourceGitHash: null,
  targetBranch,
  isDeleted: false,
});

type AgentHarness = "chat" | "prompt-capable-terminal";

const makeAgent = (inputs: { id: string; workspaceId: string; harness: AgentHarness }): CodingAgentTaskView =>
  ({
    id: inputs.id,
    workspaceId: inputs.workspaceId,
    projectId: "proj-1",
    createdAt: "2024-01-01T00:00:00Z",
    updatedAt: "2024-01-01T00:00:00Z",
    status: TaskStatus.READY,
    model: LlmModel.CLAUDE_4_SONNET,
    harnessCapabilities: { supportsChatInterface: inputs.harness === "chat" },
    acceptsAutomatedPrompts: inputs.harness === "prompt-capable-terminal",
    isDeleted: false,
  }) as unknown as CodingAgentTaskView;

// Seeds an agent as the visible center tab of its workspace.
const seedVisibleAgent = (store: StoreType, agent: CodingAgentTaskView, workspaceId: string): void => {
  store.set(agentAtomFamily(agent.id), agent);
  store.set(agentIdsAtom, [...(store.get(agentIdsAtom) ?? []), agent.id]);
  store.set(workspaceLayoutFamily(workspaceId), {
    ...EMPTY_WORKSPACE_LAYOUT,
    placement: { [makeAgentPanelId(agent.id)]: "center" },
    order: { center: [makeAgentPanelId(agent.id)] },
    activePanel: { center: makeAgentPanelId(agent.id) },
  });
};

// The user is viewing VIEWED_WS, whose mounted chat has registered its send
// closure, and right-clicks CLICKED_WS in the sidebar.
const setUpViewedAndClickedWorkspaces = (
  store: StoreType,
  clickedAgent: CodingAgentTaskView,
): ReturnType<typeof vi.fn> => {
  store.set(userConfigAtom, { commitPrompt: COMMIT_PROMPT, prCreationPrompt: PR_PROMPT } as unknown as UserConfig);
  seedVisibleAgent(store, makeAgent({ id: "agent-viewed", workspaceId: VIEWED_WS, harness: "chat" }), VIEWED_WS);
  seedVisibleAgent(store, clickedAgent, CLICKED_WS);
  const viewedChatSend = vi.fn();
  store.set(chatActionsAtom, { appendText: null, insertSkill: null, sendMessage: viewedChatSend, isDisabled: false });
  return viewedChatSend;
};

const renderRuntime = (store: StoreType): ReturnType<typeof useGitAndOpenInRuntime> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  return renderHook(() => useGitAndOpenInRuntime(), { wrapper }).result.current;
};

afterEach(() => {
  sendMessagesMock.mockReset();
  terminalInputMock.mockReset();
  localStorage.clear();
});

describe("useGitAndOpenInRuntime", () => {
  it("sends the commit prompt to the clicked workspace's agent, not the viewed workspace's chat", () => {
    const store = createStore();
    const viewedChatSend = setUpViewedAndClickedWorkspaces(
      store,
      makeAgent({ id: "agent-clicked", workspaceId: CLICKED_WS, harness: "chat" }),
    );

    renderRuntime(store).commitChanges(makeWorkspace(CLICKED_WS, "main"));

    expect(sendMessagesMock).toHaveBeenCalledTimes(1);
    expect(sendMessagesMock).toHaveBeenCalledWith({
      path: { workspace_id: CLICKED_WS, agent_id: "agent-clicked" },
      body: { message: COMMIT_PROMPT, model: LlmModel.CLAUDE_4_SONNET },
    });
    expect(viewedChatSend).not.toHaveBeenCalled();
  });

  it("sends the pull request prompt, with the target branch, to the clicked workspace's agent", () => {
    const store = createStore();
    const viewedChatSend = setUpViewedAndClickedWorkspaces(
      store,
      makeAgent({ id: "agent-clicked", workspaceId: CLICKED_WS, harness: "chat" }),
    );

    renderRuntime(store).createMergeRequest(makeWorkspace(CLICKED_WS, "release"));

    expect(sendMessagesMock).toHaveBeenCalledTimes(1);
    expect(sendMessagesMock).toHaveBeenCalledWith({
      path: { workspace_id: CLICKED_WS, agent_id: "agent-clicked" },
      body: {
        message: `${PR_PROMPT}\n\nTarget the pull request against \`release\`.`,
        model: LlmModel.CLAUDE_4_SONNET,
      },
    });
    expect(viewedChatSend).not.toHaveBeenCalled();
  });

  it("types the pull request prompt into the clicked workspace's prompt-capable terminal agent", () => {
    const store = createStore();
    const viewedChatSend = setUpViewedAndClickedWorkspaces(
      store,
      makeAgent({ id: "terminal-clicked", workspaceId: CLICKED_WS, harness: "prompt-capable-terminal" }),
    );

    renderRuntime(store).createMergeRequest(makeWorkspace(CLICKED_WS, null));

    expect(terminalInputMock).toHaveBeenCalledTimes(1);
    expect(terminalInputMock).toHaveBeenCalledWith({
      path: { agent_id: "terminal-clicked" },
      body: { text: PR_PROMPT, submit: true },
    });
    expect(sendMessagesMock).not.toHaveBeenCalled();
    expect(viewedChatSend).not.toHaveBeenCalled();
  });
});
