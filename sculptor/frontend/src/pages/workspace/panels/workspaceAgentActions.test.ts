import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage, CodingAgentTaskView } from "~/api";
import { LlmModel } from "~/api";
import { getEmptyTaskDetailState, taskDetailAtomFamily } from "~/common/state/atoms/taskDetails.ts";
import { taskAtomFamily, taskIdsAtom } from "~/common/state/atoms/tasks.ts";
import type { WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/components/sections/persistence/types.ts";
import { makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { workspaceLayoutFamily } from "~/components/sections/sectionAtoms.ts";

import {
  activeChatAgentIdAtomFamily,
  canCommitAtomFamily,
  commitActionAtomFamily,
  lastFocusedChatAgentAtomFamily,
} from "./workspaceAgentActions.ts";

// sendWorkspaceAgentMessages hits the backend; stub it so the commit action's
// payload can be asserted deterministically.
const { sendMessagesMock } = vi.hoisted(() => ({ sendMessagesMock: vi.fn() }));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, sendWorkspaceAgentMessages: sendMessagesMock };
});

const WS = "ws-test";
const WS_OTHER = "ws-test-other";

const createMockTask = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: "task-1",
    projectId: "proj-1",
    createdAt: "2024-01-01T00:00:00Z",
    updatedAt: "2024-01-01T00:00:00Z",
    taskStatus: "RUNNING",
    isAutoCompacting: false,
    artifactNames: [],
    initialPrompt: "Test prompt",
    titleOrSomethingLikeIt: "Test task",
    interface: "API",
    model: LlmModel.CLAUDE_4_SONNET,
    harnessCapabilities: { supportsChatInterface: true },
    isDeleted: false,
    workspaceId: WS,
    ...overrides,
  }) as CodingAgentTaskView;

type StoreType = ReturnType<typeof createStore>;

const seedTask = (store: StoreType, task: CodingAgentTaskView): void => {
  store.set(taskAtomFamily(task.id), task);
  store.set(taskIdsAtom, [...(store.get(taskIdsAtom) ?? []), task.id]);
};

const seedLayout = (store: StoreType, layout: Partial<WorkspaceLayoutState>, workspaceId: string = WS): void => {
  store.set(workspaceLayoutFamily(workspaceId), { ...EMPTY_WORKSPACE_LAYOUT, ...layout });
};

afterEach(() => {
  sendMessagesMock.mockReset();
  // atomFamily entries are module-level; drop per-test keys so state doesn't
  // leak across tests (the jotai store itself is fresh per test).
  for (const workspaceId of [WS, WS_OTHER]) {
    workspaceLayoutFamily.remove(workspaceId);
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
    seedTask(store, createMockTask({ id: "agent-a" }));
    seedTask(store, createMockTask({ id: "agent-b" }));
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
    seedTask(store, createMockTask({ id: "agent-a" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center", changes: "center" },
      order: { center: [makeAgentPanelId("agent-a"), "changes"] },
      // The Changes panel is the active center tab — the chat is unmounted.
      activePanel: { center: "changes" },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("agent-a");
  });

  it("skips agents whose harness has no chat interface (terminal agents)", () => {
    const store = createStore();
    seedTask(
      store,
      createMockTask({
        id: "terminal-agent",
        harnessCapabilities: { supportsChatInterface: false },
      } as Partial<CodingAgentTaskView>),
    );
    seedTask(store, createMockTask({ id: "chat-agent" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("terminal-agent")]: "center", [makeAgentPanelId("chat-agent")]: "center" },
      order: { center: [makeAgentPanelId("terminal-agent"), makeAgentPanelId("chat-agent")] },
      activePanel: { center: makeAgentPanelId("terminal-agent") },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("chat-agent");
  });

  it("ignores stale layout entries for unloaded agents and falls back to the workspace's tasks", () => {
    const store = createStore();
    seedTask(store, createMockTask({ id: "live-agent" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("deleted-agent")]: "center" },
      order: { center: [makeAgentPanelId("deleted-agent")] },
      activePanel: { center: makeAgentPanelId("deleted-agent") },
    });

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBe("live-agent");
  });

  it("does not resolve tasks from a different workspace", () => {
    const store = createStore();
    seedTask(store, createMockTask({ id: "other-ws-agent", workspaceId: "ws-other" }));
    seedLayout(store, {});

    expect(store.get(activeChatAgentIdAtomFamily(WS))).toBeUndefined();
  });
});

// Two chats visible at once: agent-a is the active center tab, agent-b the
// active right tab. Center-first resolution alone picks agent-a.
const seedTwoVisibleChats = (store: StoreType): void => {
  seedTask(store, createMockTask({ id: "agent-a" }));
  seedTask(store, createMockTask({ id: "agent-b" }));
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

  it("falls back to the layout resolution when the focused agent's task is deleted", () => {
    const store = createStore();
    seedTask(store, createMockTask({ id: "agent-a" }));
    // agent-b's panel is still in the (stale) layout, but its task never loads.
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
    seedTask(store, createMockTask({ id: "agent-c", workspaceId: WS_OTHER }));
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
    seedTask(store, createMockTask({ id: "agent-a" }));
    seedLayout(store, {
      placement: { [makeAgentPanelId("agent-a")]: "center" },
      activePanel: { center: makeAgentPanelId("agent-a") },
    });
    store.set(taskDetailAtomFamily("agent-a"), {
      ...getEmptyTaskDetailState(),
      queuedChatMessages: [{ id: "queued-1" } as ChatMessage],
    });

    expect(store.get(canCommitAtomFamily(WS))).toBe(false);
    taskDetailAtomFamily.remove("agent-a");
  });

  it("is true when a target agent resolves and nothing is queued", () => {
    const store = createStore();
    seedTask(store, createMockTask({ id: "agent-a" }));
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
    seedTask(store, createMockTask({ id: "agent-a", model: LlmModel.CLAUDE_4_SONNET }));
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
});
