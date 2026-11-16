import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView, UserConfig, Workspace } from "~/api";
import { ElementIds, LlmModel, WorkspaceInitializationStrategy } from "~/api";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { activeWorkspaceIdAtom } from "~/pages/workspace/layout/atoms/section.ts";

import { CommitButton } from "./CommitButton.tsx";

// The commit prompt is sent over HTTP; stub only that call so the request's target can be asserted.
const { sendMessagesMock } = vi.hoisted(() => ({ sendMessagesMock: vi.fn() }));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, sendWorkspaceAgentMessages: sendMessagesMock };
});

// Settings navigation is a route change; the menu only needs to ask for the right page.
const { mockOpenSettings } = vi.hoisted(() => ({ mockOpenSettings: vi.fn() }));
vi.mock("~/common/state/hooks/useOpenSettings.ts", () => ({
  useOpenSettings: (): unknown => mockOpenSettings,
}));

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
  mockOpenSettings.mockReset();
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

  describe("its Edit prompt menu", () => {
    const seedJjWorkspace = (store: StoreType, jjCommitPrompt: string | null): void => {
      seedChatAgent(store, { agentId: "agent-shown", workspaceId: WS });
      store.set(workspaceAtomFamily(WS), {
        objectId: WS,
        projectId: "proj-1",
        initializationStrategy: WorkspaceInitializationStrategy.JJ_WORKSPACE,
        targetBranch: "main@origin",
      } as Workspace);
      store.set(userConfigAtom, { commitPrompt: "Commit it all", jjCommitPrompt } as UserConfig);
    };

    it("leads a jj workspace to its jj commit prompt on the Jujutsu page", () => {
      const store = createStore();
      seedJjWorkspace(store, "Commit with jj");
      renderCommitButton(store, WS);

      fireEvent.contextMenu(screen.getByTestId(ElementIds.CHANGES_COMMIT_BUTTON));
      fireEvent.click(screen.getByRole("menuitem", { name: "Edit jj prompt..." }));

      expect(mockOpenSettings).toHaveBeenCalledWith("JJ", "commit");
    });

    it("says a jj workspace with no jj prompt is sent the git prompt, and where to set a jj one", () => {
      const store = createStore();
      seedJjWorkspace(store, null);
      renderCommitButton(store, WS);

      fireEvent.contextMenu(screen.getByTestId(ElementIds.CHANGES_COMMIT_BUTTON));
      fireEvent.click(screen.getByRole("menuitem", { name: "Edit prompt..." }));
      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByRole("textbox")).toHaveValue("Commit it all");
      expect(dialog).toHaveTextContent("No jj commit prompt is set, so this jj workspace is sent this git prompt");
      fireEvent.click(within(dialog).getByRole("link", { name: "Set a jj commit prompt" }));

      expect(mockOpenSettings).toHaveBeenCalledWith("JJ", "commit");
    });

    it("edits a git workspace's git prompt with no word of jj", () => {
      const store = createStore();
      seedChatAgent(store, { agentId: "agent-shown", workspaceId: WS });
      store.set(userConfigAtom, { commitPrompt: "Commit it all" } as UserConfig);
      renderCommitButton(store, WS);

      fireEvent.contextMenu(screen.getByTestId(ElementIds.CHANGES_COMMIT_BUTTON));
      fireEvent.click(screen.getByRole("menuitem", { name: "Edit prompt..." }));

      expect(within(screen.getByRole("dialog")).getByRole("textbox")).toHaveValue("Commit it all");
      expect(screen.getByRole("dialog")).not.toHaveTextContent("jj");
    });
  });
});
