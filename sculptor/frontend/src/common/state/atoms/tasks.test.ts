import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { CodingAgentTaskView, HarnessCapabilities } from "../../../api";
import {
  optimisticDeleteTaskAtom,
  rollbackDeleteTaskAtom,
  taskAtomFamily,
  taskIdsAtom,
  tasksArrayAtom,
  taskSupportsBackgroundTasksAtomFamily,
  taskSupportsCompactionAtomFamily,
  taskSupportsContextResetAtomFamily,
  taskSupportsInteractiveBackchannelAtomFamily,
  taskSupportsSessionResumeAtomFamily,
  taskSupportsToolUseRenderingAtomFamily,
  updateTasksAtom,
} from "./tasks";

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

describe("optimisticDeleteTaskAtom", () => {
  it("returns snapshot and removes task from taskAtomFamily and taskIdsAtom", () => {
    const store = createStore();
    const task = createMockTask({ id: "task-1" });
    store.set(taskAtomFamily("task-1"), task);
    store.set(taskIdsAtom, ["task-1"]);

    const snapshot = store.set(optimisticDeleteTaskAtom, "task-1");

    expect(snapshot).toEqual(task);
    expect(store.get(taskAtomFamily("task-1"))).toBeNull();
    expect(store.get(taskIdsAtom)).toEqual([]);
  });

  it("returns null when task is already deleted", () => {
    const store = createStore();
    store.set(taskIdsAtom, ["task-1"]);

    const snapshot = store.set(optimisticDeleteTaskAtom, "task-1");

    expect(snapshot).toBeNull();
    expect(store.get(taskIdsAtom)).toEqual(["task-1"]);
  });

  it("handles undefined taskIdsAtom gracefully", () => {
    const store = createStore();
    const task = createMockTask({ id: "task-1" });
    store.set(taskAtomFamily("task-1"), task);

    const snapshot = store.set(optimisticDeleteTaskAtom, "task-1");

    expect(snapshot).toEqual(task);
    expect(store.get(taskAtomFamily("task-1"))).toBeNull();
    expect(store.get(taskIdsAtom)).toEqual([]);
  });
});

describe("rollbackDeleteTaskAtom", () => {
  it("restores task to taskAtomFamily and taskIdsAtom after optimistic delete", () => {
    const store = createStore();
    const task = createMockTask({ id: "task-1" });
    store.set(taskAtomFamily("task-1"), task);
    store.set(taskIdsAtom, ["task-1"]);

    const snapshot = store.set(optimisticDeleteTaskAtom, "task-1");
    expect(snapshot).not.toBeNull();

    store.set(rollbackDeleteTaskAtom, { taskId: "task-1", snapshot: snapshot! });

    expect(store.get(taskAtomFamily("task-1"))).toEqual(task);
    expect(store.get(taskIdsAtom)).toContain("task-1");
  });

  it("does not create duplicate entries in taskIdsAtom", () => {
    const store = createStore();
    const task = createMockTask({ id: "task-1" });
    store.set(taskAtomFamily("task-1"), task);
    store.set(taskIdsAtom, ["task-1"]);

    store.set(rollbackDeleteTaskAtom, { taskId: "task-1", snapshot: task });

    const ids = store.get(taskIdsAtom)!;
    expect(ids.filter((id) => id === "task-1")).toHaveLength(1);
  });
});

describe("taskSupportsInteractiveBackchannelAtomFamily", () => {
  it("returns undefined when no task has been written for the id", () => {
    const store = createStore();

    expect(store.get(taskSupportsInteractiveBackchannelAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the task's supports_interactive_backchannel value when true", () => {
    const store = createStore();
    const task = createMockTask({
      id: "task-1",
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
    });
    store.set(taskAtomFamily("task-1"), task);

    expect(store.get(taskSupportsInteractiveBackchannelAtomFamily("task-1"))).toBe(true);
  });

  it("returns the task's supports_interactive_backchannel value when false", () => {
    const store = createStore();
    const task = createMockTask({
      id: "task-1",
      harnessCapabilities: {
        supportsChatInterface: true,
        supportsInteractiveBackchannel: false,
        supportsSkills: false,
        supportsSubAgents: false,
        supportsImageInput: false,
        supportsFastMode: false,
        supportsContextReset: false,
        supportsCompaction: false,
        supportsBackgroundTasks: false,
        supportsSessionResume: false,
        supportsToolUseRendering: false,
        supportsFileAttachments: false,
        supportsInterruption: false,
        supportsFileReferences: false,
      },
    });
    store.set(taskAtomFamily("task-1"), task);

    expect(store.get(taskSupportsInteractiveBackchannelAtomFamily("task-1"))).toBe(false);
  });

  it("does not notify subscribers when an unrelated task field changes", () => {
    const store = createStore();
    const task = createMockTask({
      id: "task-1",
      status: "RUNNING",
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
    });
    store.set(taskAtomFamily("task-1"), task);

    let notificationCount = 0;
    const unsubscribe = store.sub(taskSupportsInteractiveBackchannelAtomFamily("task-1"), () => {
      notificationCount += 1;
    });

    store.set(taskAtomFamily("task-1"), { ...task, status: "WAITING" } as CodingAgentTaskView);
    expect(notificationCount).toBe(0);

    unsubscribe();
  });

  it("notifies subscribers when supports_interactive_backchannel changes", () => {
    const store = createStore();
    const task = createMockTask({
      id: "task-1",
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
    });
    store.set(taskAtomFamily("task-1"), task);

    let notificationCount = 0;
    const unsubscribe = store.sub(taskSupportsInteractiveBackchannelAtomFamily("task-1"), () => {
      notificationCount += 1;
    });

    store.set(taskAtomFamily("task-1"), {
      ...task,
      harnessCapabilities: { ...task.harnessCapabilities, supportsInteractiveBackchannel: false },
    } as CodingAgentTaskView);
    expect(notificationCount).toBe(1);
    expect(store.get(taskSupportsInteractiveBackchannelAtomFamily("task-1"))).toBe(false);

    unsubscribe();
  });
});

describe("stream convergence after optimistic delete", () => {
  it("remains correctly deleted when stream confirms deletion", () => {
    const store = createStore();
    const task = createMockTask({ id: "task-1" });
    store.set(taskAtomFamily("task-1"), task);
    store.set(taskIdsAtom, ["task-1"]);

    store.set(optimisticDeleteTaskAtom, "task-1");
    expect(store.get(taskAtomFamily("task-1"))).toBeNull();
    expect(store.get(taskIdsAtom)).toEqual([]);

    store.set(updateTasksAtom, { "task-1": { ...task, isDeleted: true } as CodingAgentTaskView });

    expect(store.get(taskAtomFamily("task-1"))).toBeNull();
    const ids = store.get(taskIdsAtom)!;
    expect(ids).not.toContain("task-1");
    expect(store.get(tasksArrayAtom)).toEqual([]);
  });
});

// Build a task whose harness advertises a single capability flag at the
// given value, leaving every other flag at the all-true default.
const buildTaskWithCapability = (field: keyof HarnessCapabilities, value: boolean): CodingAgentTaskView => {
  const base = createMockTask({ id: "task-1" });
  return { ...base, harnessCapabilities: { ...base.harnessCapabilities, [field]: value } } as CodingAgentTaskView;
};

// Every narrow capability atom family shares one read shape: an
// optional-chained read of one twin field, yielding `boolean | undefined`.
const CAPABILITY_ATOM_CASES: ReadonlyArray<{
  atomFamily: typeof taskSupportsContextResetAtomFamily;
  field: keyof HarnessCapabilities;
}> = [
  { atomFamily: taskSupportsContextResetAtomFamily, field: "supportsContextReset" },
  { atomFamily: taskSupportsCompactionAtomFamily, field: "supportsCompaction" },
  { atomFamily: taskSupportsBackgroundTasksAtomFamily, field: "supportsBackgroundTasks" },
  { atomFamily: taskSupportsSessionResumeAtomFamily, field: "supportsSessionResume" },
  { atomFamily: taskSupportsToolUseRenderingAtomFamily, field: "supportsToolUseRendering" },
];

describe.each(CAPABILITY_ATOM_CASES)("$field capability atom family", ({ atomFamily, field }) => {
  it("returns undefined when no task has been written for the id", () => {
    const store = createStore();

    expect(store.get(atomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the capability value when true", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), buildTaskWithCapability(field, true));

    expect(store.get(atomFamily("task-1"))).toBe(true);
  });

  it("returns the capability value when false", () => {
    const store = createStore();
    store.set(taskAtomFamily("task-1"), buildTaskWithCapability(field, false));

    expect(store.get(atomFamily("task-1"))).toBe(false);
  });
});
