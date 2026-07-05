import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage, CodingAgentTaskView, HarnessCapabilities } from "~/api";
import { LlmModel, TaskStatus } from "~/api";
import { agentDetailStateAtomFamily, getEmptyAgentDetailState } from "~/common/state/atoms/agentDetails.ts";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents.ts";
import { commitPromptSendFailedToastAtom, terminalPromptRejectedToastAtom } from "~/common/state/atoms/toasts.ts";
import { workspaceLayoutFamily } from "~/pages/workspace/layout/atoms/section.ts";
import type { WorkspaceLayoutState } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { makeAgentPanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";

import {
  activeAgentIdAtomFamily,
  activeChatAgentIdAtomFamily,
  canCommitAtomFamily,
  commitActionAtomFamily,
  lastFocusedChatAgentAtomFamily,
} from "./workspaceAgentActions.ts";

// sendWorkspaceAgentMessages and postAgentTerminalInput hit the backend; stub
// them so the commit action's payload and routing can be asserted
// deterministically.
const { sendMessagesMock, terminalInputMock } = vi.hoisted(() => ({
  sendMessagesMock: vi.fn(),
  terminalInputMock: vi.fn(),
}));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, sendWorkspaceAgentMessages: sendMessagesMock, postAgentTerminalInput: terminalInputMock };
});

const WS = "ws-test";
const WS_OTHER = "ws-test-other";

const DEFAULT_HARNESS_CAPABILITIES: HarnessCapabilities = {
  supportsChatInterface: true,
  supportsInteractiveBackchannel: true,
  supportsSkills: true,
  supportsSubAgents: true,
  supportsImageInput: true,
  supportsFastMode: true,
  supportsContextReset: true,
  supportsCompaction: true,
  supportsBackgroundTasks: true,
  supportsSessionResume: true,
  supportsToolUseRendering: true,
  supportsFileAttachments: true,
  supportsInterruption: true,
  supportsFileReferences: true,
  supportsModelSelection: true,
};

// A partial harnessCapabilities override is merged over the all-true default, so a
// terminal agent can flip one capability (e.g. supportsChatInterface) without
// restating the whole shape. Typing the default as HarnessCapabilities also forces
// this fixture to be updated when a new capability field is added.
type MockAgentOverrides = Partial<Omit<CodingAgentTaskView, "harnessCapabilities">> & {
  harnessCapabilities?: Partial<HarnessCapabilities>;
};

const createMockAgent = ({ harnessCapabilities, ...overrides }: MockAgentOverrides = {}): CodingAgentTaskView =>
  ({
    id: "task-1",
    projectId: "proj-1",
    createdAt: "2024-01-01T00:00:00Z",
    updatedAt: "2024-01-01T00:00:00Z",
    status: TaskStatus.RUNNING,
    isAutoCompacting: false,
    artifactNames: [],
    initialPrompt: "Test prompt",
    titleOrSomethingLikeIt: "Test task",
    interface: "API",
    model: LlmModel.CLAUDE_4_SONNET,
    harnessCapabilities: { ...DEFAULT_HARNESS_CAPABILITIES, ...harnessCapabilities },
    isDeleted: false,
    workspaceId: WS,
    ...overrides,
  }) as unknown as CodingAgentTaskView;

type StoreType = ReturnType<typeof createStore>;

const seedAgent = (store: StoreType, agent: CodingAgentTaskView): void => {
  store.set(agentAtomFamily(agent.id), agent);
  store.set(agentIdsAtom, [...(store.get(agentIdsAtom) ?? []), agent.id]);
};

const seedLayout = (store: StoreType, layout: Partial<WorkspaceLayoutState>, workspaceId: string = WS): void => {
  store.set(workspaceLayoutFamily(workspaceId), { ...EMPTY_WORKSPACE_LAYOUT, ...layout });
};

afterEach(() => {
  sendMessagesMock.mockReset();
  terminalInputMock.mockReset();
  // Each test runs against a fresh jotai store, so atom values never leak; these
  // removals only drop the module-level memoized atom instances. workspaceLayoutFamily
  // is deliberately left in place: its initial value is read from the persistence
  // adapter, whose writes flush on a debounce that can land after this hook, so
  // re-creating the atom would re-hydrate a later test from that stale snapshot.
  for (const workspaceId of [WS, WS_OTHER]) {
    activeAgentIdAtomFamily.remove(workspaceId);
    activeChatAgentIdAtomFamily.remove(workspaceId);
    canCommitAtomFamily.remove(workspaceId);
    commitActionAtomFamily.remove(workspaceId);
    lastFocusedChatAgentAtomFamily.remove(workspaceId);
  }
  localStorage.clear();
});

describe("activeChatAgentIdAtomFamily", () => {
  it("prefers the agent panel that is its sub-section's active tab", () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "agent-a" }));
    seedAgent(store, createMockAgent({ id: "agent-b" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center", [makeAgentPanelId("agent-b")]: "right" },
      order: { center: [makeAgentPanelId("agent-a")], right: [makeAgentPanelId("agent-b")] },
      // The right-hand chat is the visible one; center shows a static panel.
      activePanel: { center: "changes", right: makeAgentPanelId("agent-b") },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("agent-b");
  });

  it("falls back to an open but inactive agent panel when no chat is the active tab", () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "agent-a" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center", changes: "center" },
      order: { center: [makeAgentPanelId("agent-a"), "changes"] },
      // The Changes panel is the active center tab — the chat is unmounted.
      activePanel: { center: "changes" },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("agent-a");
  });

  it("skips terminal agents: composer-targeted features address the chat hidden behind them", () => {
    const store = createStore();
    seedAgent(
      store,
      createMockAgent({
        id: "terminal-agent",
        harnessCapabilities: { supportsChatInterface: false },
      }),
    );
    seedAgent(store, createMockAgent({ id: "chat-agent" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("terminal-agent")]: "center", [makeAgentPanelId("chat-agent")]: "center" },
      order: { center: [makeAgentPanelId("terminal-agent"), makeAgentPanelId("chat-agent")] },
      activePanel: { center: makeAgentPanelId("terminal-agent") },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("chat-agent");
  });

  it("ignores stale layout entries for unloaded agents and falls back to the workspace's agents", () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "live-agent" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("deleted-agent")]: "center" },
      order: { center: [makeAgentPanelId("deleted-agent")] },
      activePanel: { center: makeAgentPanelId("deleted-agent") },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("live-agent");
  });

  it("does not resolve agents from a different workspace", () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "other-ws-agent", workspaceId: WS_OTHER }));
    seedLayout(store, {});

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBeUndefined();
  });
});

// Two chats visible at once: agent-a is the active center tab, agent-b the
// active right tab. Center-first resolution alone picks agent-a.
const seedTwoVisibleChats = (store: StoreType): void => {
  seedAgent(store, createMockAgent({ id: "agent-a" }));
  seedAgent(store, createMockAgent({ id: "agent-b" }));
  seedLayout(store, {
    placement: { [makeAgentPanelId("agent-a")]: "center", [makeAgentPanelId("agent-b")]: "right" },
    order: { center: [makeAgentPanelId("agent-a")], right: [makeAgentPanelId("agent-b")] },
    activePanel: { center: makeAgentPanelId("agent-a"), right: makeAgentPanelId("agent-b") },
  });
};

describe("lastFocusedChatAgentAtomFamily resolution", () => {
  it("prefers the last-focused chat agent over the center chat when both are visible", () => {
    const store = createStore();
    seedTwoVisibleChats(store);

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("agent-a");
    store.set(lastFocusedChatAgentAtomFamily(WS), "agent-b");
    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("agent-b");
  });

  it("falls back to the layout resolution when the focused agent's panel is closed", () => {
    const store = createStore();
    seedTwoVisibleChats(store);
    store.set(lastFocusedChatAgentAtomFamily(WS), "agent-b");

    // Closing agent-b's panel removes it from the layout's placement.
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center" },
      order: { center: [makeAgentPanelId("agent-a")] },
      activePanel: { center: makeAgentPanelId("agent-a") },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("agent-a");
  });

  it("falls back to the layout resolution when the focused agent is deleted", () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "agent-a" }));
    // agent-b's panel is still in the (stale) layout, but its agent never loads.
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center", [makeAgentPanelId("agent-b")]: "right" },
      activePanel: { center: makeAgentPanelId("agent-a"), right: makeAgentPanelId("agent-b") },
    });
    store.set(lastFocusedChatAgentAtomFamily(WS), "agent-b");

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("agent-a");
  });

  it("keeps focus tracking isolated per workspace", () => {
    const store = createStore();
    seedTwoVisibleChats(store);
    seedAgent(store, createMockAgent({ id: "agent-c", workspaceId: WS_OTHER }));
    seedLayout(
      store,
      {
        placement: { [makeAgentPanelId("agent-c")]: "center" },
        activePanel: { center: makeAgentPanelId("agent-c") },
      },
      WS_OTHER,
    );

    store.set(lastFocusedChatAgentAtomFamily(WS), "agent-b");

    expect(store.get(lastFocusedChatAgentAtomFamily(WS_OTHER))).toBeUndefined();
    expect(store.get(activeChatAgentIdAtomFamily(WS_OTHER))).toBe("agent-c");
  });
});

describe("canCommitAtomFamily", () => {
  it("is false when no chat agent resolves", () => {
    const store = createStore();
    seedLayout(store, {});
    expect(store.get(canCommitAtomFamily(WS))).toBe(false);
  });

  it("is false while the target agent has a queued message", () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "agent-a" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center" },
      activePanel: { center: makeAgentPanelId("agent-a") },
    });
    store.set(agentDetailStateAtomFamily("agent-a"), {
      ...getEmptyAgentDetailState(),
      queuedChatMessages: [{ id: "queued-1" } as ChatMessage],
    });

    expect(store.get(canCommitAtomFamily(WS))).toBe(false);
  });

  it("is true when a target agent resolves and nothing is queued", () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "agent-a" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center" },
      activePanel: { center: makeAgentPanelId("agent-a") },
    });

    expect(store.get(canCommitAtomFamily(WS))).toBe(true);
  });
});

describe("commitActionAtomFamily", () => {
  it("sends the message to the resolved agent with its model", async () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "agent-a", model: LlmModel.CLAUDE_4_SONNET }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center" },
      activePanel: { center: makeAgentPanelId("agent-a") },
    });

    await store.set(commitActionAtomFamily(WS), "Please commit my changes");

    expect(sendMessagesMock).toHaveBeenCalledTimes(1);
    expect(sendMessagesMock).toHaveBeenCalledWith({
      path: { workspace_id: WS, agent_id: "agent-a" },
      body: { message: "Please commit my changes", model: LlmModel.CLAUDE_4_SONNET },
    });
  });

  it("no-ops when no chat agent resolves", async () => {
    const store = createStore();
    seedLayout(store, {});

    await store.set(commitActionAtomFamily(WS), "Please commit my changes");

    expect(sendMessagesMock).not.toHaveBeenCalled();
  });

  it("targets the last-focused agent when several chats are visible", async () => {
    const store = createStore();
    seedTwoVisibleChats(store);
    store.set(lastFocusedChatAgentAtomFamily(WS), "agent-b");

    await store.set(commitActionAtomFamily(WS), "Please commit my changes");

    expect(sendMessagesMock).toHaveBeenCalledTimes(1);
    expect(sendMessagesMock).toHaveBeenCalledWith({
      path: { workspace_id: WS, agent_id: "agent-b" },
      body: { message: "Please commit my changes", model: LlmModel.CLAUDE_4_SONNET },
    });
  });

  it("surfaces a toast when the chat-route send fails", async () => {
    const store = createStore();
    seedAgent(store, createMockAgent({ id: "agent-a" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center" },
      activePanel: { center: makeAgentPanelId("agent-a") },
    });
    sendMessagesMock.mockRejectedValueOnce(new Error("network down"));

    await store.set(commitActionAtomFamily(WS), "Please commit my changes");

    expect(store.get(commitPromptSendFailedToastAtom)).toMatchObject({
      title: "Couldn't send commit request",
    });
  });
});

// The terminal-routing premise: a registered terminal agent is the visible
// center tab with a chat agent open (but hidden) behind it. Whether the
// terminal can take automated prompts is per-registration
// (`accepts_automated_prompts`), so each test picks its own capability/status.
const seedVisibleTerminalWithHiddenChat = (store: StoreType, terminalOverrides: MockAgentOverrides): void => {
  seedAgent(store, createMockAgent({ id: "chat-agent" }));
  seedAgent(
    store,
    createMockAgent({
      id: "terminal-agent",
      harnessCapabilities: { supportsChatInterface: false },
      status: TaskStatus.READY,
      ...terminalOverrides,
    }),
  );
  seedLayout(store, {
    placement: { [makeAgentPanelId("chat-agent")]: "center", [makeAgentPanelId("terminal-agent")]: "center" },
    order: { center: [makeAgentPanelId("chat-agent"), makeAgentPanelId("terminal-agent")] },
    activePanel: { center: makeAgentPanelId("terminal-agent") },
  });
};

describe("activeAgentIdAtomFamily", () => {
  it("resolves the visible terminal agent rather than the chat hidden behind it", () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: true });

    expect(store.get(activeAgentIdAtomFamily(WS))).toBe("terminal-agent");
  });

  it("ignores a last-focused chat that is no longer its sub-section's active tab", () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: true });
    store.set(lastFocusedChatAgentAtomFamily(WS), "chat-agent");

    expect(store.get(activeAgentIdAtomFamily(WS))).toBe("terminal-agent");
  });

  it("resolves a prompt-incapable terminal when visible (the action disables instead of re-routing)", () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: false });

    expect(store.get(activeAgentIdAtomFamily(WS))).toBe("terminal-agent");
  });

  it("falls back to a hidden chat-capable panel, never a hidden terminal, when no agent tab is visible", () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: true });
    // The Changes panel takes over the center tab: both agents are hidden.
    seedLayout(store, {
      placement: {
        [makeAgentPanelId("chat-agent")]: "center",
        [makeAgentPanelId("terminal-agent")]: "center",
        changes: "center",
      },
      order: { center: [makeAgentPanelId("terminal-agent"), makeAgentPanelId("chat-agent"), "changes"] },
      activePanel: { center: "changes" },
    });

    expect(store.get(activeAgentIdAtomFamily(WS))).toBe("chat-agent");
  });
});

describe("canCommitAtomFamily for terminal agents", () => {
  it("is true for a prompt-capable terminal at its prompt", () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: true, status: TaskStatus.READY });

    expect(store.get(canCommitAtomFamily(WS))).toBe(true);
  });

  it("is false once the prompt-capable terminal goes busy", () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: true, status: TaskStatus.RUNNING });

    expect(store.get(canCommitAtomFamily(WS))).toBe(false);
  });

  it("is false for a non-opt-in terminal even when idle with a chat open behind it", () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: false, status: TaskStatus.READY });

    expect(store.get(canCommitAtomFamily(WS))).toBe(false);
  });
});

describe("commitActionAtomFamily terminal routing", () => {
  it("types and submits the prompt through the terminal-input endpoint", async () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: true });

    await store.set(commitActionAtomFamily(WS), "Stage every changed file");

    expect(terminalInputMock).toHaveBeenCalledTimes(1);
    expect(terminalInputMock).toHaveBeenCalledWith({
      path: { agent_id: "terminal-agent" },
      body: { text: "Stage every changed file", submit: true },
    });
    expect(sendMessagesMock).not.toHaveBeenCalled();
  });

  it("no-ops for a non-opt-in terminal instead of re-routing to the hidden chat", async () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: false });

    await store.set(commitActionAtomFamily(WS), "Stage every changed file");

    expect(terminalInputMock).not.toHaveBeenCalled();
    expect(sendMessagesMock).not.toHaveBeenCalled();
  });

  it("surfaces the busy toast when the terminal-input endpoint rejects", async () => {
    const store = createStore();
    seedVisibleTerminalWithHiddenChat(store, { acceptsAutomatedPrompts: true });
    terminalInputMock.mockRejectedValueOnce(new Error("409 agent busy"));

    await store.set(commitActionAtomFamily(WS), "Stage every changed file");

    expect(store.get(terminalPromptRejectedToastAtom)).toMatchObject({ title: "Agent is busy" });
  });
});
