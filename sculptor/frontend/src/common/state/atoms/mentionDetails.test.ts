import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { CodingAgentTaskView, Project, Workspace } from "../../../api";
import { agentAtomFamily, agentIdsAtom } from "./agents";
import { agentDetailAtomFamily, repositoryDetailAtomFamily, workspaceDetailAtomFamily } from "./mentionDetails";
import { projectAtomFamily, projectIdsAtom } from "./projects";
import { workspaceAtomFamily, workspaceIdsAtom } from "./workspaces";

const makeAgent = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
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
    isSmoothStreamingSupported: true,
    isArchived: false,
    isDeleted: false,
    title: "Test task",
    status: "RUNNING",
    goal: "Test goal",
    workspaceId: "ws-1",
    ...overrides,
  }) as CodingAgentTaskView;

const makeWorkspace = (overrides: Partial<Workspace> = {}): Workspace =>
  ({
    objectId: "ws-1",
    projectId: "proj-1",
    organizationReference: "org",
    description: "Test workspace",
    createdAt: "2024-01-01T00:00:00Z",
    isDeleted: false,
    isOpen: true,
    ...overrides,
  }) as unknown as Workspace;

const makeProject = (overrides: Partial<Project> = {}): Project =>
  ({
    objectId: "proj-1",
    organizationReference: "org",
    name: "Test project",
    userGitRepoUrl: "git@example.com:test/repo.git",
    ...overrides,
  }) as unknown as Project;

// Seed an agent into its atom family AND into the agent-ids list so the derived
// `agentsArrayAtom` picks it up.
const seedAgent = (store: ReturnType<typeof createStore>, agent: CodingAgentTaskView): void => {
  store.set(agentAtomFamily(agent.id), agent);
  store.set(agentIdsAtom, [...(store.get(agentIdsAtom) ?? []), agent.id]);
};

const seedWorkspace = (store: ReturnType<typeof createStore>, workspace: Workspace): void => {
  store.set(workspaceAtomFamily(workspace.objectId), workspace);
  store.set(workspaceIdsAtom, [...(store.get(workspaceIdsAtom) ?? []), workspace.objectId]);
};

const seedProject = (store: ReturnType<typeof createStore>, project: Project): void => {
  store.set(projectAtomFamily(project.objectId), project);
  store.set(projectIdsAtom, [...store.get(projectIdsAtom), project.objectId]);
};

describe("agentDetailAtomFamily", () => {
  it("returns null when no agent is registered for the id", () => {
    const store = createStore();
    expect(store.get(agentDetailAtomFamily("unknown-id"))).toBeNull();
  });

  it("returns null when the agent atom is explicitly null (deleted)", () => {
    const store = createStore();
    store.set(agentAtomFamily("task-1"), null);
    expect(store.get(agentDetailAtomFamily("task-1"))).toBeNull();
  });

  it("composes agent, status, and parent workspace into a single shape", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", description: "Parent WS" }));
    seedAgent(store, makeAgent({ id: "task-1", status: "READY", workspaceId: "ws-1" }));

    const detail = store.get(agentDetailAtomFamily("task-1"));
    expect(detail).not.toBeNull();
    expect(detail?.agent.id).toBe("task-1");
    expect(detail?.status).toBe("READY");
    expect(detail?.workspace?.description).toBe("Parent WS");
  });

  it("handles an agent with no workspaceId (workspace field is null)", () => {
    const store = createStore();
    seedAgent(store, makeAgent({ id: "task-1", workspaceId: null }));

    const detail = store.get(agentDetailAtomFamily("task-1"));
    expect(detail?.workspace).toBeNull();
  });

  it("reacts to status changes on the agent atom", () => {
    const store = createStore();
    seedAgent(store, makeAgent({ id: "task-1", status: "RUNNING" }));
    expect(store.get(agentDetailAtomFamily("task-1"))?.status).toBe("RUNNING");

    store.set(agentAtomFamily("task-1"), makeAgent({ id: "task-1", status: "READY" }));
    expect(store.get(agentDetailAtomFamily("task-1"))?.status).toBe("READY");
  });
});

describe("workspaceDetailAtomFamily", () => {
  it("returns null when the workspace atom is null", () => {
    const store = createStore();
    expect(store.get(workspaceDetailAtomFamily("unknown"))).toBeNull();
  });

  it("counts non-deleted agents whose workspaceId matches", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1" }));
    seedAgent(store, makeAgent({ id: "t1", workspaceId: "ws-1" }));
    seedAgent(store, makeAgent({ id: "t2", workspaceId: "ws-1" }));
    seedAgent(store, makeAgent({ id: "t3", workspaceId: "ws-2" }));

    const detail = store.get(workspaceDetailAtomFamily("ws-1"));
    expect(detail?.agentCount).toBe(2);
    expect(detail?.agents.map((agent) => agent.id).sort()).toEqual(["t1", "t2"]);
  });

  it("caps the agents preview at 3 but reports the full count", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1" }));
    for (let i = 0; i < 5; i++) {
      seedAgent(store, makeAgent({ id: `t${i}`, workspaceId: "ws-1" }));
    }

    const detail = store.get(workspaceDetailAtomFamily("ws-1"));
    expect(detail?.agentCount).toBe(5);
    expect(detail?.agents.length).toBe(3);
  });

  it("includes the parent project resolved via workspace.projectId", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1", name: "Core" }));
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", projectId: "proj-1" }));

    const detail = store.get(workspaceDetailAtomFamily("ws-1"));
    expect(detail?.project?.name).toBe("Core");
  });

  it("reacts when a new agent is added to the workspace", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1" }));
    expect(store.get(workspaceDetailAtomFamily("ws-1"))?.agentCount).toBe(0);

    seedAgent(store, makeAgent({ id: "t1", workspaceId: "ws-1" }));
    expect(store.get(workspaceDetailAtomFamily("ws-1"))?.agentCount).toBe(1);
  });
});

describe("repositoryDetailAtomFamily", () => {
  it("returns null when the project atom is null", () => {
    const store = createStore();
    expect(store.get(repositoryDetailAtomFamily("unknown"))).toBeNull();
  });

  it("counts non-deleted workspaces whose projectId matches", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1" }));
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", projectId: "proj-1" }));
    seedWorkspace(store, makeWorkspace({ objectId: "ws-2", projectId: "proj-1" }));
    seedWorkspace(store, makeWorkspace({ objectId: "ws-3", projectId: "proj-2" }));

    const detail = store.get(repositoryDetailAtomFamily("proj-1"));
    expect(detail?.workspaceCount).toBe(2);
    expect(detail?.workspaces.map((ws) => ws.objectId).sort()).toEqual(["ws-1", "ws-2"]);
  });

  it("caps the workspaces preview at 3 but reports the full count", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1" }));
    for (let i = 0; i < 5; i++) {
      seedWorkspace(store, makeWorkspace({ objectId: `ws-${i}`, projectId: "proj-1" }));
    }

    const detail = store.get(repositoryDetailAtomFamily("proj-1"));
    expect(detail?.workspaceCount).toBe(5);
    expect(detail?.workspaces.length).toBe(3);
  });

  it("reacts when a new workspace is added to the project", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1" }));
    expect(store.get(repositoryDetailAtomFamily("proj-1"))?.workspaceCount).toBe(0);

    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", projectId: "proj-1" }));
    expect(store.get(repositoryDetailAtomFamily("proj-1"))?.workspaceCount).toBe(1);
  });
});
