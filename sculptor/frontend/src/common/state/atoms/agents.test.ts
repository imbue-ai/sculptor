import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "../../../api";
import {
  agentAcceptsAutomatedPromptsAtomFamily,
  agentAtomFamily,
  agentModelAtomFamily,
  agentStatusAtomFamily,
  agentSupportsChatInterfaceAtomFamily,
} from "./agents";

// The surviving selector families back Jotai atom graphs only
// (workspaceAgentActions.ts, mentionDetails.ts); React components read these
// fields through the useAgentHelpers hooks instead (see useAgentHelpers.test.ts
// for the fine-grained-subscription coverage).

const createMockAgent = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: "task-1",
    projectId: "proj-1",
    createdAt: "2024-01-01T00:00:00Z",
    updatedAt: "2024-01-01T00:00:00Z",
    agentStatus: "RUNNING",
    isAutoCompacting: false,
    artifactNames: [],
    initialPrompt: "Test prompt",
    titleOrSomethingLikeIt: "Test task",
    interface: "API",
    systemPrompt: null,
    model: "CLAUDE_4_SONNET",
    acceptsAutomatedPrompts: false,
    harnessCapabilities: {
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
    },
    isSmoothStreamingSupported: true,
    isArchived: false,
    isDeleted: false,
    title: "Test task",
    status: "RUNNING",
    goal: "Test goal",
    workspaceId: null,
    ...overrides,
  }) as CodingAgentTaskView;

describe("agentStatusAtomFamily", () => {
  it("returns undefined when no agent has been written for the id", () => {
    const store = createStore();

    expect(store.get(agentStatusAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the agent's status", () => {
    const store = createStore();
    store.set(agentAtomFamily("task-1"), createMockAgent({ id: "task-1", status: "WAITING" }));

    expect(store.get(agentStatusAtomFamily("task-1"))).toBe("WAITING");
  });

  it("does not notify subscribers when an unrelated agent field changes", () => {
    const store = createStore();
    const agent = createMockAgent({ id: "task-1", status: "RUNNING" });
    store.set(agentAtomFamily("task-1"), agent);

    let notificationCount = 0;
    const unsubscribe = store.sub(agentStatusAtomFamily("task-1"), () => {
      notificationCount += 1;
    });

    store.set(agentAtomFamily("task-1"), { ...agent, goal: "changed" } as CodingAgentTaskView);
    expect(notificationCount).toBe(0);

    unsubscribe();
  });
});

describe("agentModelAtomFamily", () => {
  it("returns undefined when no agent has been written for the id", () => {
    const store = createStore();

    expect(store.get(agentModelAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("maps a null model to undefined (terminal agents carry no model)", () => {
    const store = createStore();
    store.set(agentAtomFamily("task-1"), createMockAgent({ id: "task-1", model: null }));

    expect(store.get(agentModelAtomFamily("task-1"))).toBeUndefined();
  });
});

describe("agentSupportsChatInterfaceAtomFamily", () => {
  it("returns undefined when no agent has been written for the id", () => {
    const store = createStore();

    expect(store.get(agentSupportsChatInterfaceAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the capability value when true", () => {
    const store = createStore();
    const base = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), {
      ...base,
      harnessCapabilities: { ...base.harnessCapabilities, supportsChatInterface: true },
    } as CodingAgentTaskView);

    expect(store.get(agentSupportsChatInterfaceAtomFamily("task-1"))).toBe(true);
  });

  it("returns the capability value when false", () => {
    const store = createStore();
    const base = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), {
      ...base,
      harnessCapabilities: { ...base.harnessCapabilities, supportsChatInterface: false },
    } as CodingAgentTaskView);

    expect(store.get(agentSupportsChatInterfaceAtomFamily("task-1"))).toBe(false);
  });
});

describe("agentAcceptsAutomatedPromptsAtomFamily", () => {
  it("returns undefined when no agent has been written for the id", () => {
    const store = createStore();

    expect(store.get(agentAcceptsAutomatedPromptsAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the agent's accepts_automated_prompts value", () => {
    const store = createStore();
    store.set(agentAtomFamily("task-1"), createMockAgent({ id: "task-1", acceptsAutomatedPrompts: true }));

    expect(store.get(agentAcceptsAutomatedPromptsAtomFamily("task-1"))).toBe(true);
  });
});
