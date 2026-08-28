import type { Meta, StoryObj } from "@storybook/react-vite";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";

import type { CodingAgentTaskView, Project, Workspace } from "~/api";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents";
import { projectAtomFamily, projectIdsAtom } from "~/common/state/atoms/projects";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces";
import { AgentDetailPane } from "~/components/mentionDetailPanes/AgentDetailPane";
import { RepositoryDetailPane } from "~/components/mentionDetailPanes/RepositoryDetailPane";
import { WorkspaceDetailPane } from "~/components/mentionDetailPanes/WorkspaceDetailPane";

// Story-level fixtures — each story seeds its own store so each variant is
// independent. The panes read from atoms, so we wrap each story in a jotai
// `<Provider>` with a fresh store.

const makeAgent = (overrides: Partial<CodingAgentTaskView>): CodingAgentTaskView =>
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
    title: null,
    status: "RUNNING",
    goal: null,
    workspaceId: null,
    ...overrides,
  }) as CodingAgentTaskView;

const makeWorkspace = (overrides: Partial<Workspace>): Workspace =>
  ({
    objectId: "ws-1",
    projectId: "proj-1",
    organizationReference: "org",
    description: "",
    createdAt: "2024-01-01T00:00:00Z",
    isDeleted: false,
    isOpen: true,
    ...overrides,
  }) as unknown as Workspace;

const makeProject = (overrides: Partial<Project>): Project =>
  ({
    objectId: "proj-1",
    organizationReference: "org",
    name: "",
    userGitRepoUrl: null,
    ...overrides,
  }) as unknown as Project;

type Store = ReturnType<typeof createStore>;

const seed = (
  store: Store,
  {
    projects = [],
    workspaces = [],
    agents = [],
  }: {
    projects?: ReadonlyArray<Project>;
    workspaces?: ReadonlyArray<Workspace>;
    agents?: ReadonlyArray<CodingAgentTaskView>;
  },
): void => {
  for (const p of projects) {
    store.set(projectAtomFamily(p.objectId), p);
  }
  store.set(
    projectIdsAtom,
    projects.map((p) => p.objectId),
  );
  for (const w of workspaces) {
    store.set(workspaceAtomFamily(w.objectId), w);
  }
  store.set(
    workspaceIdsAtom,
    workspaces.map((w) => w.objectId),
  );
  for (const agent of agents) {
    store.set(agentAtomFamily(agent.id), agent);
  }
  store.set(
    agentIdsAtom,
    agents.map((agent) => agent.id),
  );
};

const withStore = (store: Store, node: ReactNode): ReactElement => (
  <Provider store={store}>
    <div style={{ padding: "var(--space-4)", maxWidth: 360 }}>{node}</div>
  </Provider>
);

const AgentPaneMeta = {
  title: "Custom/MentionDetailPanes/AgentDetailPane",
  component: AgentDetailPane,
} satisfies Meta<typeof AgentDetailPane>;

// eslint-disable-next-line import/no-default-export
export default AgentPaneMeta;

type AgentStory = StoryObj<typeof AgentPaneMeta>;

const STUB_AGENT_ARGS = { agentId: "stub", entityDisplayName: "stub" };
const STUB_WORKSPACE_ARGS = { workspaceId: "stub", entityDisplayName: "stub" };
const STUB_REPOSITORY_ARGS = { projectId: "stub", entityDisplayName: "stub" };

export const AgentPopulated: AgentStory = {
  args: STUB_AGENT_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    seed(store, {
      projects: [makeProject({ objectId: "proj-1", name: "Core" })],
      workspaces: [makeWorkspace({ objectId: "ws-1", description: "Workflow overhaul", projectId: "proj-1" })],
      agents: [
        makeAgent({
          id: "task-1",
          title: "Ship the entity mention refactor",
          goal: "Unify the three chip systems",
          status: "READY",
          workspaceId: "ws-1",
        }),
      ],
    });
    return withStore(store, <AgentDetailPane agentId="task-1" entityDisplayName="Ship the entity mention refactor" />);
  },
};

export const AgentRunning: AgentStory = {
  args: STUB_AGENT_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    seed(store, {
      workspaces: [makeWorkspace({ objectId: "ws-1", description: "Live build" })],
      agents: [makeAgent({ id: "task-1", title: "Sweep flaky tests", status: "RUNNING", workspaceId: "ws-1" })],
    });
    return withStore(store, <AgentDetailPane agentId="task-1" entityDisplayName="Sweep flaky tests" />);
  },
};

export const AgentNoWorkspace: AgentStory = {
  args: STUB_AGENT_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    seed(store, {
      agents: [makeAgent({ id: "task-1", title: "Standalone agent", status: "READY" })],
    });
    return withStore(store, <AgentDetailPane agentId="task-1" entityDisplayName="Standalone agent" />);
  },
};

export const AgentDeleted: AgentStory = {
  args: STUB_AGENT_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    return withStore(store, <AgentDetailPane agentId="missing" entityDisplayName="Retired agent" />);
  },
};

export const WorkspacePopulated: StoryObj<typeof WorkspaceDetailPane> = {
  args: STUB_WORKSPACE_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    seed(store, {
      projects: [makeProject({ objectId: "proj-1", name: "Core" })],
      workspaces: [makeWorkspace({ objectId: "ws-1", description: "Prompt navigator", projectId: "proj-1" })],
      agents: [
        makeAgent({ id: "t1", title: "Arrow rail", workspaceId: "ws-1" }),
        makeAgent({ id: "t2", title: "Jump-to-bottom button", workspaceId: "ws-1" }),
        makeAgent({ id: "t3", title: "Scroll lock-in", workspaceId: "ws-1" }),
      ],
    });
    return withStore(store, <WorkspaceDetailPane workspaceId="ws-1" entityDisplayName="Prompt navigator" />);
  },
};

export const WorkspaceEmpty: StoryObj<typeof WorkspaceDetailPane> = {
  args: STUB_WORKSPACE_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    seed(store, {
      projects: [makeProject({ objectId: "proj-1", name: "Core" })],
      workspaces: [makeWorkspace({ objectId: "ws-1", description: "Fresh branch", projectId: "proj-1" })],
    });
    return withStore(store, <WorkspaceDetailPane workspaceId="ws-1" entityDisplayName="Fresh branch" />);
  },
};

export const WorkspaceDeleted: StoryObj<typeof WorkspaceDetailPane> = {
  args: STUB_WORKSPACE_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    return withStore(store, <WorkspaceDetailPane workspaceId="missing" entityDisplayName="Archived workspace" />);
  },
};

export const RepositoryPopulated: StoryObj<typeof RepositoryDetailPane> = {
  args: STUB_REPOSITORY_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    seed(store, {
      projects: [
        makeProject({ objectId: "proj-1", name: "Sculptor", userGitRepoUrl: "git@gitlab.com:imbue/sculptor.git" }),
      ],
      workspaces: [
        makeWorkspace({ objectId: "ws-1", description: "Main", projectId: "proj-1" }),
        makeWorkspace({ objectId: "ws-2", description: "Prompt navigator", projectId: "proj-1" }),
        makeWorkspace({ objectId: "ws-3", description: "Chip redesign", projectId: "proj-1" }),
      ],
    });
    return withStore(store, <RepositoryDetailPane projectId="proj-1" entityDisplayName="Sculptor" />);
  },
};

export const RepositoryNoWorkspaces: StoryObj<typeof RepositoryDetailPane> = {
  args: STUB_REPOSITORY_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    seed(store, {
      projects: [makeProject({ objectId: "proj-1", name: "Minimal", userGitRepoUrl: "git@example.com:m/r.git" })],
    });
    return withStore(store, <RepositoryDetailPane projectId="proj-1" entityDisplayName="Minimal" />);
  },
};

export const RepositoryDeleted: StoryObj<typeof RepositoryDetailPane> = {
  args: STUB_REPOSITORY_ARGS,
  render: (): ReactElement => {
    const store = createStore();
    return withStore(store, <RepositoryDetailPane projectId="missing" entityDisplayName="Archived repo" />);
  },
};
