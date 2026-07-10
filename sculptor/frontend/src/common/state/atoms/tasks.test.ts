import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { CodingAgentTaskView } from "../../../api";
import {
  taskAcceptsAutomatedPromptsAtomFamily,
  taskAtomFamily,
  taskModelAtomFamily,
  taskStatusAtomFamily,
  taskSupportsChatInterfaceAtomFamily,
} from "./tasks";

// The surviving selector families back Jotai atom graphs only
// (workspaceAgentActions.ts, mentionDetails.ts); React components read these
// fields through the useTaskHelpers hooks instead (see useTaskHelpers.test.ts
// for the fine-grained-subscription coverage).

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

describe("taskStatusAtomFamily", () => {
  it("returns undefined when no task has been written for the id", () => {
    const store = createStore();

    expect(store.get(taskStatusAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the task's status", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), createMockTask({ id: "task-1", status: "WAITING" }));

    expect(store.get(taskStatusAtomFamily("task-1"))).toBe("WAITING");
  });

  it("does not notify subscribers when an unrelated task field changes", () => {
    const store = createStore();
    const task = createMockTask({ id: "task-1", status: "RUNNING" });
    store.set(taskAtomFamily("task-1"), task);

    let notificationCount = 0;
    const unsubscribe = store.sub(taskStatusAtomFamily("task-1"), () => {
      notificationCount += 1;
    });

    store.set(taskAtomFamily("task-1"), { ...task, goal: "changed" } as CodingAgentTaskView);
    expect(notificationCount).toBe(0);

    unsubscribe();
  });
});

describe("taskModelAtomFamily", () => {
  it("returns undefined when no task has been written for the id", () => {
    const store = createStore();

    expect(store.get(taskModelAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("maps a null model to undefined (terminal agents carry no model)", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), createMockTask({ id: "task-1", model: null }));

    expect(store.get(taskModelAtomFamily("task-1"))).toBeUndefined();
  });
});

describe("taskSupportsChatInterfaceAtomFamily", () => {
  it("returns undefined when no task has been written for the id", () => {
    const store = createStore();

    expect(store.get(taskSupportsChatInterfaceAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the capability value when true", () => {
    const store = createStore();
    const base = createMockTask({ id: "task-1" });
    store.set(taskAtomFamily("task-1"), {
      ...base,
      harnessCapabilities: { ...base.harnessCapabilities, supportsChatInterface: true },
    } as CodingAgentTaskView);

    expect(store.get(taskSupportsChatInterfaceAtomFamily("task-1"))).toBe(true);
  });

  it("returns the capability value when false", () => {
    const store = createStore();
    const base = createMockTask({ id: "task-1" });
    store.set(taskAtomFamily("task-1"), {
      ...base,
      harnessCapabilities: { ...base.harnessCapabilities, supportsChatInterface: false },
    } as CodingAgentTaskView);

    expect(store.get(taskSupportsChatInterfaceAtomFamily("task-1"))).toBe(false);
  });
});

describe("taskAcceptsAutomatedPromptsAtomFamily", () => {
  it("returns undefined when no task has been written for the id", () => {
    const store = createStore();

    expect(store.get(taskAcceptsAutomatedPromptsAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the task's accepts_automated_prompts value", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), createMockTask({ id: "task-1", acceptsAutomatedPrompts: true }));

    expect(store.get(taskAcceptsAutomatedPromptsAtomFamily("task-1"))).toBe(true);
  });
});
