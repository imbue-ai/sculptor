import { Theme } from "@radix-ui/themes";
import { act, cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { CodingAgentTaskView, Project, Workspace } from "~/api";
import { projectAtomFamily, projectIdsAtom } from "~/common/state/atoms/projects";
import { taskAtomFamily, taskIdsAtom } from "~/common/state/atoms/tasks";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces";

import { AgentDetailPane } from "./AgentDetailPane";
import { RepositoryDetailPane } from "./RepositoryDetailPane";
import { WorkspaceDetailPane } from "./WorkspaceDetailPane";

type Store = ReturnType<typeof createStore>;

const makeTask = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
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
    description: "Alpha workspace",
    createdAt: "2024-01-01T00:00:00Z",
    isDeleted: false,
    isOpen: true,
    ...overrides,
  }) as unknown as Workspace;

const makeProject = (overrides: Partial<Project> = {}): Project =>
  ({
    objectId: "proj-1",
    organizationReference: "org",
    name: "Core repo",
    userGitRepoUrl: "git@example.com:core/repo.git",
    ...overrides,
  }) as unknown as Project;

const seedTask = (store: Store, task: CodingAgentTaskView): void => {
  store.set(taskAtomFamily(task.id), task);
  store.set(taskIdsAtom, [...(store.get(taskIdsAtom) ?? []), task.id]);
};

const seedWorkspace = (store: Store, workspace: Workspace): void => {
  store.set(workspaceAtomFamily(workspace.objectId), workspace);
  store.set(workspaceIdsAtom, [...(store.get(workspaceIdsAtom) ?? []), workspace.objectId]);
};

const seedProject = (store: Store, project: Project): void => {
  store.set(projectAtomFamily(project.objectId), project);
  store.set(projectIdsAtom, [...store.get(projectIdsAtom), project.objectId]);
};

const renderWithStore = (store: Store, node: ReactNode): { store: Store; container: HTMLElement } => {
  const { container } = render(
    <Provider store={store}>
      <Theme>{node as ReactElement}</Theme>
    </Provider>,
  );
  return { store, container };
};

afterEach(() => {
  cleanup();
});

describe("AgentDetailPane", () => {
  it("renders title, goal, and workspace description when populated", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", description: "Parent WS" }));
    seedTask(
      store,
      makeTask({
        id: "task-1",
        title: "Ship the refactor",
        status: "READY",
        goal: "Finish the plan",
        workspaceId: "ws-1",
      }),
    );

    renderWithStore(store, <AgentDetailPane agentId="task-1" entityDisplayName="fallback" />);

    expect(screen.getByText("Ship the refactor")).toBeTruthy();
    expect(screen.getByText("Finish the plan")).toBeTruthy();
    expect(screen.getByText("in Parent WS")).toBeTruthy();
    // Status badge was retired from this pane — task status is shown elsewhere.
    expect(screen.queryByText("READY")).toBeNull();
  });

  it("falls back to entityDisplayName when the agent is deleted", () => {
    const store = createStore();
    renderWithStore(store, <AgentDetailPane agentId="missing" entityDisplayName="Build flow" />);

    expect(screen.getByText("Build flow")).toBeTruthy();
    expect(screen.getByText("Agent no longer exists")).toBeTruthy();
  });

  it("omits the goal line when the task has no goal", () => {
    const store = createStore();
    seedTask(store, makeTask({ id: "task-1", title: "Ship it", goal: "", workspaceId: null }));

    const { container } = renderWithStore(store, <AgentDetailPane agentId="task-1" entityDisplayName="fallback" />);

    expect(screen.getByText("Ship it")).toBeTruthy();
    // No "in {description}" body line because goal is empty and workspace is missing.
    expect(container.textContent).not.toContain("in ");
  });

  it("omits the workspace row when the task has no workspace", () => {
    const store = createStore();
    seedTask(store, makeTask({ id: "task-1", title: "Standalone", workspaceId: null }));
    const { container } = renderWithStore(store, <AgentDetailPane agentId="task-1" entityDisplayName="fallback" />);
    expect(container.textContent).not.toContain("in ");
  });

  it("uses goal as the title when the task has no title", () => {
    const store = createStore();
    seedTask(store, makeTask({ id: "task-1", title: null, goal: "First goal line\nsecond line", workspaceId: null }));

    renderWithStore(store, <AgentDetailPane agentId="task-1" entityDisplayName="fallback" />);

    expect(screen.getByText("First goal line")).toBeTruthy();
  });
});

describe("WorkspaceDetailPane", () => {
  it("renders description, project badge, and agent count", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1", name: "Core" }));
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", description: "Main line", projectId: "proj-1" }));
    seedTask(store, makeTask({ id: "t1", title: "Rebuild tabs", workspaceId: "ws-1" }));
    seedTask(store, makeTask({ id: "t2", title: "Upgrade router", workspaceId: "ws-1" }));

    renderWithStore(store, <WorkspaceDetailPane workspaceId="ws-1" entityDisplayName="fallback" />);

    expect(screen.getByText("Main line")).toBeTruthy();
    expect(screen.getByText("Core")).toBeTruthy();
    expect(screen.getByText("2 agents")).toBeTruthy();
    // Per-agent titles were retired from this pane — only the count is shown.
    expect(screen.queryByText("Rebuild tabs")).toBeNull();
    expect(screen.queryByText("Upgrade router")).toBeNull();
  });

  it("renders 'No agents yet' when the workspace has no non-deleted tasks", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", description: "Empty" }));

    renderWithStore(store, <WorkspaceDetailPane workspaceId="ws-1" entityDisplayName="fallback" />);

    expect(screen.getByText("No agents yet")).toBeTruthy();
  });

  it("falls back to entityDisplayName when the workspace is deleted", () => {
    const store = createStore();
    renderWithStore(store, <WorkspaceDetailPane workspaceId="missing" entityDisplayName="Deleted WS" />);

    expect(screen.getByText("Deleted WS")).toBeTruthy();
    expect(screen.getByText("Workspace no longer exists")).toBeTruthy();
  });

  it("reacts when a new agent is added to the workspace", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1" }));
    renderWithStore(store, <WorkspaceDetailPane workspaceId="ws-1" entityDisplayName="fallback" />);
    expect(screen.getByText("No agents yet")).toBeTruthy();

    act(() => {
      seedTask(store, makeTask({ id: "t1", title: "Fresh agent", workspaceId: "ws-1" }));
    });
    expect(screen.getByText("1 agent")).toBeTruthy();
  });

  it("uses the entityDisplayName when the workspace description is empty", () => {
    const store = createStore();
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", description: "" }));
    renderWithStore(store, <WorkspaceDetailPane workspaceId="ws-1" entityDisplayName="Fallback name" />);
    expect(screen.getByText("Fallback name")).toBeTruthy();
  });
});

describe("RepositoryDetailPane", () => {
  it("renders name, git URL, and attached workspace descriptions", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1", name: "Core", userGitRepoUrl: "git@example.com:a/b.git" }));
    seedWorkspace(store, makeWorkspace({ objectId: "ws-1", description: "Alpha", projectId: "proj-1" }));
    seedWorkspace(store, makeWorkspace({ objectId: "ws-2", description: "Bravo", projectId: "proj-1" }));

    renderWithStore(store, <RepositoryDetailPane projectId="proj-1" entityDisplayName="fallback" />);

    expect(screen.getByText("Core")).toBeTruthy();
    expect(screen.getByText("git@example.com:a/b.git")).toBeTruthy();
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.getByText("Bravo")).toBeTruthy();
    expect(screen.getByText("2 workspaces")).toBeTruthy();
  });

  it("renders 'No workspaces yet' when nothing references the project", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1" }));
    renderWithStore(store, <RepositoryDetailPane projectId="proj-1" entityDisplayName="fallback" />);
    expect(screen.getByText("No workspaces yet")).toBeTruthy();
  });

  it("falls back to entityDisplayName when the project is deleted", () => {
    const store = createStore();
    renderWithStore(store, <RepositoryDetailPane projectId="missing" entityDisplayName="Old repo" />);

    expect(screen.getByText("Old repo")).toBeTruthy();
    expect(screen.getByText("Repository no longer exists")).toBeTruthy();
  });

  it("omits the git URL line when the project has none", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1", userGitRepoUrl: null }));
    const { container } = renderWithStore(
      store,
      <RepositoryDetailPane projectId="proj-1" entityDisplayName="fallback" />,
    );
    // No monospaced git-url row rendered.
    expect(container.textContent).not.toContain("@example.com");
  });

  it("reacts when a new workspace is added to the project", () => {
    const store = createStore();
    seedProject(store, makeProject({ objectId: "proj-1" }));
    renderWithStore(store, <RepositoryDetailPane projectId="proj-1" entityDisplayName="fallback" />);
    expect(screen.getByText("No workspaces yet")).toBeTruthy();

    act(() => {
      seedWorkspace(store, makeWorkspace({ objectId: "ws-1", description: "New", projectId: "proj-1" }));
    });
    expect(screen.getByText("1 workspace")).toBeTruthy();
    expect(screen.getByText("New")).toBeTruthy();
  });
});
