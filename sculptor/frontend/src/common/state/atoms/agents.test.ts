import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { CodingAgentTaskView, HarnessCapabilities } from "../../../api";
import {
  agentAtomFamily,
  agentAvailableModelsAtomFamily,
  agentIdsAtom,
  agentsArrayAtom,
  agentSupportsBackgroundTasksAtomFamily,
  agentSupportsCompactionAtomFamily,
  agentSupportsContextResetAtomFamily,
  agentSupportsInteractiveBackchannelAtomFamily,
  agentSupportsSessionResumeAtomFamily,
  agentSupportsToolUseRenderingAtomFamily,
  optimisticDeleteAgentAtom,
  rollbackDeleteAgentAtom,
  updateAgentsAtom,
} from "./agents";

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

describe("optimisticDeleteAgentAtom", () => {
  it("returns snapshot and removes agent from agentAtomFamily and agentIdsAtom", () => {
    const store = createStore();
    const agent = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), agent);
    store.set(agentIdsAtom, ["task-1"]);

    const snapshot = store.set(optimisticDeleteAgentAtom, "task-1");

    expect(snapshot).toEqual(agent);
    expect(store.get(agentAtomFamily("task-1"))).toBeNull();
    expect(store.get(agentIdsAtom)).toEqual([]);
  });

  it("returns null when agent is already deleted", () => {
    const store = createStore();
    store.set(agentIdsAtom, ["task-1"]);

    const snapshot = store.set(optimisticDeleteAgentAtom, "task-1");

    expect(snapshot).toBeNull();
    expect(store.get(agentIdsAtom)).toEqual(["task-1"]);
  });

  it("handles undefined agentIdsAtom gracefully", () => {
    const store = createStore();
    const agent = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), agent);

    const snapshot = store.set(optimisticDeleteAgentAtom, "task-1");

    expect(snapshot).toEqual(agent);
    expect(store.get(agentAtomFamily("task-1"))).toBeNull();
    expect(store.get(agentIdsAtom)).toEqual([]);
  });
});

describe("rollbackDeleteAgentAtom", () => {
  it("restores agent to agentAtomFamily and agentIdsAtom after optimistic delete", () => {
    const store = createStore();
    const agent = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), agent);
    store.set(agentIdsAtom, ["task-1"]);

    const snapshot = store.set(optimisticDeleteAgentAtom, "task-1");
    expect(snapshot).not.toBeNull();

    store.set(rollbackDeleteAgentAtom, { agentId: "task-1", snapshot: snapshot! });

    expect(store.get(agentAtomFamily("task-1"))).toEqual(agent);
    expect(store.get(agentIdsAtom)).toContain("task-1");
  });

  it("does not create duplicate entries in agentIdsAtom", () => {
    const store = createStore();
    const agent = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), agent);
    store.set(agentIdsAtom, ["task-1"]);

    store.set(rollbackDeleteAgentAtom, { agentId: "task-1", snapshot: agent });

    const ids = store.get(agentIdsAtom)!;
    expect(ids.filter((id) => id === "task-1")).toHaveLength(1);
  });
});

describe("agentSupportsInteractiveBackchannelAtomFamily", () => {
  it("returns undefined when no agent has been written for the id", () => {
    const store = createStore();

    expect(store.get(agentSupportsInteractiveBackchannelAtomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the agent's supports_interactive_backchannel value when true", () => {
    const store = createStore();
    const agent = createMockAgent({
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
        supportsModelSelection: true,
      },
    });
    store.set(agentAtomFamily("task-1"), agent);

    expect(store.get(agentSupportsInteractiveBackchannelAtomFamily("task-1"))).toBe(true);
  });

  it("returns the agent's supports_interactive_backchannel value when false", () => {
    const store = createStore();
    const agent = createMockAgent({
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
        supportsModelSelection: false,
      },
    });
    store.set(agentAtomFamily("task-1"), agent);

    expect(store.get(agentSupportsInteractiveBackchannelAtomFamily("task-1"))).toBe(false);
  });

  it("does not notify subscribers when an unrelated agent field changes", () => {
    const store = createStore();
    const agent = createMockAgent({
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
        supportsModelSelection: true,
      },
    });
    store.set(agentAtomFamily("task-1"), agent);

    let notificationCount = 0;
    const unsubscribe = store.sub(agentSupportsInteractiveBackchannelAtomFamily("task-1"), () => {
      notificationCount += 1;
    });

    store.set(agentAtomFamily("task-1"), { ...agent, status: "WAITING" } as CodingAgentTaskView);
    expect(notificationCount).toBe(0);

    unsubscribe();
  });

  it("does not notify availableModels subscribers on unrelated agent updates (stable empty list)", () => {
    const store = createStore();
    // No backend catalog (Claude): availableModels is undefined, so the derived
    // atom must yield a stable empty array rather than a fresh one each recompute.
    const agent = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), agent);

    let notificationCount = 0;
    const unsubscribe = store.sub(agentAvailableModelsAtomFamily("task-1"), () => {
      notificationCount += 1;
    });

    store.set(agentAtomFamily("task-1"), { ...agent, status: "WAITING" } as CodingAgentTaskView);
    expect(notificationCount).toBe(0);

    unsubscribe();
  });

  it("notifies subscribers when supports_interactive_backchannel changes", () => {
    const store = createStore();
    const agent = createMockAgent({
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
        supportsModelSelection: true,
      },
    });
    store.set(agentAtomFamily("task-1"), agent);

    let notificationCount = 0;
    const unsubscribe = store.sub(agentSupportsInteractiveBackchannelAtomFamily("task-1"), () => {
      notificationCount += 1;
    });

    store.set(agentAtomFamily("task-1"), {
      ...agent,
      harnessCapabilities: { ...agent.harnessCapabilities, supportsInteractiveBackchannel: false },
    } as CodingAgentTaskView);
    expect(notificationCount).toBe(1);
    expect(store.get(agentSupportsInteractiveBackchannelAtomFamily("task-1"))).toBe(false);

    unsubscribe();
  });
});

describe("updateAgentsAtom", () => {
  it("marks the agent list as loaded (undefined -> []) on an empty update", () => {
    const store = createStore();
    expect(store.get(agentsArrayAtom)).toBeUndefined();

    // A zero-agent instance streams frames whose task-view map is empty; the
    // first frame must still flip the list from "loading" to "loaded, empty".
    store.set(updateAgentsAtom, {});

    expect(store.get(agentIdsAtom)).toEqual([]);
    expect(store.get(agentsArrayAtom)).toEqual([]);
  });

  it("keeps the ids reference stable across empty updates once loaded", () => {
    const store = createStore();
    store.set(updateAgentsAtom, {});
    const loadedIds = store.get(agentIdsAtom);

    store.set(updateAgentsAtom, {});

    expect(store.get(agentIdsAtom)).toBe(loadedIds);
  });
});

describe("stream convergence after optimistic delete", () => {
  it("remains correctly deleted when stream confirms deletion", () => {
    const store = createStore();
    const agent = createMockAgent({ id: "task-1" });
    store.set(agentAtomFamily("task-1"), agent);
    store.set(agentIdsAtom, ["task-1"]);

    store.set(optimisticDeleteAgentAtom, "task-1");
    expect(store.get(agentAtomFamily("task-1"))).toBeNull();
    expect(store.get(agentIdsAtom)).toEqual([]);

    store.set(updateAgentsAtom, { "task-1": { ...agent, isDeleted: true } as CodingAgentTaskView });

    expect(store.get(agentAtomFamily("task-1"))).toBeNull();
    const ids = store.get(agentIdsAtom)!;
    expect(ids).not.toContain("task-1");
    expect(store.get(agentsArrayAtom)).toEqual([]);
  });
});

// Build an agent whose harness advertises a single capability flag at the
// given value, leaving every other flag at the all-true default.
const buildAgentWithCapability = (field: keyof HarnessCapabilities, value: boolean): CodingAgentTaskView => {
  const base = createMockAgent({ id: "task-1" });
  return { ...base, harnessCapabilities: { ...base.harnessCapabilities, [field]: value } } as CodingAgentTaskView;
};

// Every narrow capability atom family shares one read shape: an
// optional-chained read of one twin field, yielding `boolean | undefined`.
const CAPABILITY_ATOM_CASES: ReadonlyArray<{
  atomFamily: typeof agentSupportsContextResetAtomFamily;
  field: keyof HarnessCapabilities;
}> = [
  { atomFamily: agentSupportsContextResetAtomFamily, field: "supportsContextReset" },
  { atomFamily: agentSupportsCompactionAtomFamily, field: "supportsCompaction" },
  { atomFamily: agentSupportsBackgroundTasksAtomFamily, field: "supportsBackgroundTasks" },
  { atomFamily: agentSupportsSessionResumeAtomFamily, field: "supportsSessionResume" },
  { atomFamily: agentSupportsToolUseRenderingAtomFamily, field: "supportsToolUseRendering" },
];

describe.each(CAPABILITY_ATOM_CASES)("$field capability atom family", ({ atomFamily, field }) => {
  it("returns undefined when no agent has been written for the id", () => {
    const store = createStore();

    expect(store.get(atomFamily("unknown-task"))).toBeUndefined();
  });

  it("returns the capability value when true", () => {
    const store = createStore();
    store.set(agentAtomFamily("task-1"), buildAgentWithCapability(field, true));

    expect(store.get(atomFamily("task-1"))).toBe(true);
  });

  it("returns the capability value when false", () => {
    const store = createStore();
    store.set(agentAtomFamily("task-1"), buildAgentWithCapability(field, false));

    expect(store.get(atomFamily("task-1"))).toBe(false);
  });
});
