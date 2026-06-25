import type { Meta, StoryObj } from "@storybook/react-vite";
import { createStore, Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";

import type {
  CodingAgentTaskView,
  LlmModel,
  Project,
  PrStatusInfo,
  TaskInterface,
  TaskState,
  TaskStatus,
  Workspace,
  WorkspaceBranchInfo,
} from "~/api";
import { WorkspacePeekAgentStatus } from "~/api";
import { projectAtomFamily, projectIdsAtom } from "~/common/state/atoms/projects";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus";
import { taskAtomFamily, taskIdsAtom } from "~/common/state/atoms/tasks";
import { workspaceBranchAtomFamily } from "~/common/state/atoms/workspaceBranch";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces";
import { WorkspacePeekPopover } from "~/pages/workspace/components/WorkspacePeekPopover";

const WORKSPACE_ID = "ws-1";

const PROJECT_ID = "project-1";

const BASE_PROJECT: Project = {
  objectId: PROJECT_ID,
  organizationReference: "org-1",
  name: "sculptor",
};

const SECOND_PROJECT: Project = {
  objectId: "project-2",
  organizationReference: "org-1",
  name: "other-repo",
};

const BASE_WORKSPACE: Workspace = {
  objectId: WORKSPACE_ID,
  projectId: PROJECT_ID,
  organizationReference: "org-1",
  description: "auth-rewrite",
  initializationStrategy: "CLONE" as Workspace["initializationStrategy"],
};

const BRANCH_INFO: WorkspaceBranchInfo = {
  currentBranch: "rewrite/auth-v2",
  workspaceId: WORKSPACE_ID,
};

const BRANCH_INFO_NO_CHANGES: WorkspaceBranchInfo = {
  currentBranch: "main",
  workspaceId: WORKSPACE_ID,
};

function makeTask(overrides: Partial<CodingAgentTaskView> & { id: string }): CodingAgentTaskView {
  const { id, ...rest } = overrides;
  return {
    objectType: "CodingAgentTask",
    id,
    projectId: "project-1",
    createdAt: "2026-03-05T01:00:00Z",
    taskStatus: "RUNNING" as TaskState,
    isAutoCompacting: false,
    acceptsAutomatedPrompts: false,
    artifactNames: [],
    updatedAt: "2026-03-05T01:30:00Z",
    initialPrompt: "Do something",
    titleOrSomethingLikeIt: "Task",
    interface: "TERMINAL" as TaskInterface,
    systemPrompt: null,
    model: "CLAUDE-4-OPUS" as LlmModel,
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
    availableModels: [],
    selectedModelId: null,
    sourcesBackendModels: false,
    isSmoothStreamingSupported: false,
    fastMode: false,
    effort: null,
    isDeleted: false,
    lastReadAt: null,
    title: "Agent 1",
    status: "RUNNING" as TaskStatus,
    goal: "Do something",
    isDev: false,
    workspaceId: WORKSPACE_ID,
    workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
    currentActivity: "Editing auth/middleware.ts",
    lastActivity: null,
    taskCompleted: 1,
    taskTotal: 3,
    currentTaskSubject: "Rewrite auth middleware",
    waitingDetail: null,
    errorDetail: null,
    ...rest,
  };
}

function createPopoverStore(
  workspace: Workspace,
  tasks: Array<CodingAgentTaskView>,
  branch: WorkspaceBranchInfo,
  project: Project = BASE_PROJECT,
  prStatus: PrStatusInfo | null = null,
): ReturnType<typeof createStore> {
  const store = createStore();
  store.set(workspaceAtomFamily(workspace.objectId), workspace);
  store.set(projectAtomFamily(project.objectId), project);
  store.set(projectAtomFamily(SECOND_PROJECT.objectId), SECOND_PROJECT);
  store.set(projectIdsAtom, [project.objectId, SECOND_PROJECT.objectId]);
  store.set(workspaceBranchAtomFamily(workspace.objectId), branch);
  store.set(
    taskIdsAtom,
    tasks.map((t) => t.id),
  );
  for (const task of tasks) {
    store.set(taskAtomFamily(task.id), task);
  }

  if (prStatus) {
    store.set(prStatusAtomFamily(workspace.objectId), prStatus);
  }
  return store;
}

const handleNavigate = (workspaceId: string, agentId?: string): void => {
  console.log("Navigate to workspace:", workspaceId, agentId ? `agent: ${agentId}` : "");
};

type StoryProps = {
  workspace: Workspace;
  tasks: Array<CodingAgentTaskView>;
  branch: WorkspaceBranchInfo;
  prStatus?: PrStatusInfo | null;
};

const Wrapper = ({ workspace, tasks, branch, prStatus = null }: StoryProps): ReactElement => {
  const store = createPopoverStore(workspace, tasks, branch, BASE_PROJECT, prStatus);
  return (
    <JotaiProvider store={store}>
      <div style={{ width: 320, padding: 20 }}>
        <div
          style={{
            background: "var(--color-panel-solid)",
            border: "1px solid var(--gray-a5)",
            borderRadius: "var(--radius-4)",
            boxShadow: "none",
            overflow: "hidden",
          }}
        >
          <WorkspacePeekPopover workspaceId={workspace.objectId} onNavigate={handleNavigate} />
        </div>
      </div>
    </JotaiProvider>
  );
};

const meta = {
  title: "Custom/WorkspacePeekPopover",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Working1Agent: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "auth-rewrite" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Editing auth/middleware.ts",
        taskCompleted: 1,
        taskTotal: 3,
        currentTaskSubject: "Rewrite auth middleware",
      }),
    ],
    branch: BRANCH_INFO,
  },
};

export const Working3Agents: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "frontend-perf" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Editing ProductList.tsx",
        taskCompleted: 3,
        taskTotal: 5,
        currentTaskSubject: "Memoize ProductList computations",
      }),
      makeTask({
        id: "t2",
        title: "Agent 2",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Editing CartProvider.tsx",
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: "Optimize context provider splitting",
      }),
      makeTask({
        id: "t3",
        title: "Agent 3",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Running jest --coverage",
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: "Add test coverage for perf changes",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "perf/reduce-rerenders" },
  },
};

export const JustStarted: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "dark-mode" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Reading styles/tokens.css",
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: null,
      }),
    ],
    branch: { ...BRANCH_INFO_NO_CHANGES, currentBranch: "feat/dark-mode" },
  },
};

export const WaitingQuestion: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "api-refactor" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.WAITING,
        currentActivity: null,
        taskCompleted: 3,
        taskTotal: 6,
        currentTaskSubject: "Implement auth middleware",
        waitingDetail: "Which auth strategy should I use — JWT or session cookies?",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "refactor/api-v2" },
  },
};

export const WaitingMixed: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "api-refactor" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.WAITING,
        currentActivity: null,
        taskCompleted: 2,
        taskTotal: 4,
        currentTaskSubject: "Implement auth middleware",
        waitingDetail: "Which auth strategy should I use — JWT or session cookies?",
      }),
      makeTask({
        id: "t2",
        title: "Agent 2",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Editing routes/v2.py",
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: "Add rate limiting to new endpoints",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "refactor/api-v2" },
  },
};

export const WaitingPlanApproval: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "new-feature" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.WAITING,
        currentActivity: null,
        taskCompleted: 0,
        taskTotal: 5,
        currentTaskSubject: null,
        waitingDetail: "Waiting for plan approval",
      }),
    ],
    branch: { ...BRANCH_INFO_NO_CHANGES, currentBranch: "feat/dark-mode" },
  },
};

export const Error1Agent: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "deploy-fix" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.ERROR,
        currentActivity: null,
        taskCompleted: 1,
        taskTotal: 3,
        currentTaskSubject: "Fix deployment dependencies",
        errorDetail: "Build failed: npm ERR! 404 Not Found: @sculptor/utils@^2.0.0",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "fix/deploy-deps" },
  },
};

export const ErrorMixed: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "ci-pipeline" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.ERROR,
        currentActivity: null,
        taskCompleted: 3,
        taskTotal: 5,
        currentTaskSubject: "Fix CI pipeline config",
        errorDetail: "Test failed: TypeError: Cannot read property 'map' of undefined",
      }),
      makeTask({
        id: "t2",
        title: "Agent 2",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Reading pipeline.config.ts",
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: "Update deployment scripts",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "fix/ci-pipeline" },
  },
};

export const MixedStatuses: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "full-stack-rewrite" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Editing api/routes.py",
        taskCompleted: 4,
        taskTotal: 7,
        currentTaskSubject: "Refactor API endpoints",
      }),
      makeTask({
        id: "t2",
        title: "Agent 2",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 3,
        taskTotal: 3,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
      }),
      makeTask({
        id: "t3",
        title: "Agent 3",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 5,
        taskTotal: 5,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
      }),
      makeTask({
        id: "t4",
        title: "Agent 4",
        workspacePeekStatus: WorkspacePeekAgentStatus.IDLE,
        currentActivity: null,
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      }),
      makeTask({
        id: "t5",
        title: "Agent 5",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Running pytest",
        taskCompleted: 2,
        taskTotal: 4,
        currentTaskSubject: "Add test coverage",
      }),
      makeTask({
        id: "t6",
        title: "Agent 6",
        workspacePeekStatus: WorkspacePeekAgentStatus.IDLE,
        currentActivity: "Edited models.py",
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
      }),
      makeTask({
        id: "t7",
        title: "Agent 7",
        workspacePeekStatus: WorkspacePeekAgentStatus.WAITING,
        currentActivity: null,
        taskCompleted: 1,
        taskTotal: 3,
        currentTaskSubject: "Migrate database schema",
        waitingDetail: "Which migration strategy — incremental or full rebuild?",
      }),
      makeTask({
        id: "t8",
        title: "Agent 8",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 2,
        taskTotal: 2,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "refactor/full-stack" },
  },
};

export const MultipleNeedHelp: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "full-stack-rewrite" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.ERROR,
        currentActivity: null,
        taskCompleted: 2,
        taskTotal: 5,
        currentTaskSubject: "Fix CI pipeline config",
        errorDetail: "Build failed: npm ERR! 404 Not Found",
      }),
      makeTask({
        id: "t2",
        title: "Agent 2",
        workspacePeekStatus: WorkspacePeekAgentStatus.WAITING,
        currentActivity: null,
        taskCompleted: 1,
        taskTotal: 3,
        currentTaskSubject: "Migrate database schema",
        waitingDetail: "Which migration strategy — incremental or full rebuild?",
      }),
      makeTask({
        id: "t3",
        title: "Agent 3",
        workspacePeekStatus: WorkspacePeekAgentStatus.WAITING,
        currentActivity: null,
        taskCompleted: 0,
        taskTotal: 4,
        currentTaskSubject: null,
        waitingDetail: "Waiting for plan approval",
      }),
      makeTask({
        id: "t4",
        title: "Agent 4",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Editing api/routes.py",
        taskCompleted: 4,
        taskTotal: 7,
        currentTaskSubject: "Refactor API endpoints",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "refactor/full-stack" },
  },
};

export const Completed: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "docs-update" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 3,
        taskTotal: 3,
        currentTaskSubject: null,
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "docs/update-readme" },
  },
};

export const Idle: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "scratch-pad" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Agent 1",
        workspacePeekStatus: WorkspacePeekAgentStatus.IDLE,
        currentActivity: null,
        taskCompleted: 0,
        taskTotal: 0,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 23 * 60 * 1000).toISOString(),
      }),
    ],
    branch: BRANCH_INFO_NO_CHANGES,
  },
};

export const IdleEmpty: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "new-workspace" },
    tasks: [],
    branch: BRANCH_INFO_NO_CHANGES,
  },
};

const BASE_PR_STATUS: PrStatusInfo = {
  workspaceId: WORKSPACE_ID,
  prState: "open",
  prIid: 342,
  prTitle: "Migrate v1 endpoints to v2 schema",
  prWebUrl: "https://github.com/project/repo/pull/342",
  pipelineStatus: "passed",
  approvals: [{ name: "Alice", approved: true }],
  unresolvedComments: [],
};

export const MrPipelinePassedApproved: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "api-migration" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Migration Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 8,
        taskTotal: 8,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 20 * 60 * 1000).toISOString(),
      }),
      makeTask({
        id: "t2",
        title: "Test Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 4,
        taskTotal: 4,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "feat/api-v2-migration" },
    prStatus: {
      ...BASE_PR_STATUS,
      pipelineStatus: "passed",
      approvals: [
        { name: "Alice", approved: true },
        { name: "Bob", approved: true },
      ],
    },
  },
};

export const MrPipelineRunning: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "logging-overhaul" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Logger Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Refactoring logger initialization",
        taskCompleted: 3,
        taskTotal: 5,
        currentTaskSubject: "Replace custom logger with structlog",
      }),
      makeTask({
        id: "t2",
        title: "Test Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 3,
        taskTotal: 3,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "refactor/structlog" },
    prStatus: {
      ...BASE_PR_STATUS,
      prIid: 298,
      prTitle: "Replace custom logger with structlog",
      pipelineStatus: "running",
      approvals: [{ name: "Alice", approved: false }],
    },
  },
};

export const MrPipelineFailed: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "data-pipeline" },
    tasks: [
      makeTask({
        id: "t1",
        title: "ETL Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.WAITING,
        currentActivity: null,
        taskCompleted: 2,
        taskTotal: 6,
        currentTaskSubject: "Implement ETL pipeline",
        waitingDetail: "Waiting for approval on migration plan",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "feat/data-pipeline-v3" },
    prStatus: {
      ...BASE_PR_STATUS,
      prIid: 311,
      prTitle: "Add ETL pipeline for user events",
      pipelineStatus: "failed",
      approvals: [{ name: "Alice", approved: false }],
    },
  },
};

export const MrChangesRequested: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "monorepo-split" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Build Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.ERROR,
        currentActivity: null,
        taskCompleted: 5,
        taskTotal: 12,
        currentTaskSubject: "Fix build configuration",
        errorDetail: "TypeError: Cannot read properties of undefined",
      }),
      makeTask({
        id: "t2",
        title: "Config Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.WORKING,
        currentActivity: "Updating shared tsconfig paths",
        taskCompleted: 2,
        taskTotal: 4,
        currentTaskSubject: "Update build config",
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "refactor/monorepo-split" },
    prStatus: {
      ...BASE_PR_STATUS,
      prIid: 405,
      prTitle: "Split monorepo into service packages",
      pipelineStatus: "failed",
      approvals: [
        { name: "Alice", approved: true },
        { name: "Bob", approved: false },
      ],
      unresolvedComments: [
        {
          author: "Bob",
          filePath: "packages/core/tsconfig.json",
          line: 12,
          body: "This path alias will break downstream",
        },
        { author: "Bob", filePath: "packages/api/src/index.ts", line: 45, body: "Missing re-export for shared types" },
      ],
    },
  },
};

export const MrMerged: Story = {
  args: {
    workspace: { ...BASE_WORKSPACE, description: "config-cleanup" },
    tasks: [
      makeTask({
        id: "t1",
        title: "Cleanup Agent",
        workspacePeekStatus: WorkspacePeekAgentStatus.COMPLETED,
        currentActivity: null,
        taskCompleted: 6,
        taskTotal: 6,
        currentTaskSubject: null,
        updatedAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      }),
    ],
    branch: { ...BRANCH_INFO, currentBranch: "chore/config-cleanup" },
    prStatus: {
      ...BASE_PR_STATUS,
      prState: "merged",
      prIid: 287,
      prTitle: "Remove deprecated config flags",
      pipelineStatus: "passed",
      approvals: [{ name: "Alice", approved: true }],
    },
  },
};
