import { readFile, writeFile } from "node:fs/promises";
import os from "node:os";

import { getOrm } from "~/db/orm";
import { getWorkspace, setWorkspaceDiffStatus } from "~/db/repositories";
import { eventBus } from "~/events";
import type {
  AgentRow,
  WorkspaceInitializationStrategy,
  WorkspaceRow,
} from "~/db/schema";
import {
  artifactsPath,
  statePath,
  workingDirectory,
} from "~/environment/paths";
import { FAKE_CLAUDE_MODEL_NAMES } from "~/harness/claude/constants";
import type { ClaudeHarnessEnvironment } from "~/harness/claude/harness";
import type { PiHarnessEnvironment } from "~/harness/pi/harness";
import { createHarnessResolver } from "~/harness/registry";
import { getCurrentUserConfig } from "~/config/user_config";
import { localPathFromRepo } from "~/services/project";
import { getRepo } from "~/db/repositories";
import { resolveBinaryPath } from "~/services/dependencies";
import { resolveEnv } from "~/services/env_injection/env";
import { projectionCache } from "~/projection/cache";
import { AgentRunner } from "~/runner/runner";

// The shared, fully-wired AgentRunner singleton the API routes drive. index.ts'
// bootstrap runner was a stub (harnessFor -> undefined); this wires the harness
// registry (Task 5.6) + per-agent environment so a created agent actually
// launches. Env-var injection precedence (Task 7.6) and pinned pi extensions
// are layered on later; until then the harness deps pass the basics.

function workspaceForAgent(agent: AgentRow): WorkspaceRow | undefined {
  return agent.workspaceId === null
    ? undefined
    : getWorkspace(getOrm(), agent.workspaceId);
}

function workingDirForWorkspace(workspace: WorkspaceRow | undefined): string {
  if (workspace === undefined || workspace.environmentId === null) {
    return "";
  }
  const repo = getRepo(getOrm(), workspace.projectId);
  const repoHostPath =
    repo !== undefined ? (localPathFromRepo(repo) ?? undefined) : undefined;
  return workingDirectory(
    workspace.environmentId,
    workspace.initializationStrategy,
    repoHostPath,
  );
}

function repoLocalPathForAgent(agent: AgentRow): string | null {
  const workspace = workspaceForAgent(agent);
  if (workspace === undefined) {
    return null;
  }
  const repo = getRepo(getOrm(), workspace.projectId);
  return repo === undefined ? null : localPathFromRepo(repo);
}

function strategyForAgent(agent: AgentRow): WorkspaceInitializationStrategy {
  return workspaceForAgent(agent)?.initializationStrategy ?? "IN_PLACE";
}

// Test-only: when a fake-claude model is selected and the integration harness
// has injected the script + interpreter paths, launch `fake_claude.py` instead
// of the real `claude` binary (mirrors process_manager's `_is_fake_claude`).
// Returns null in production (env vars unset), so real models are unaffected.
function resolveFakeClaudeCommand(
  modelName: string | null,
): { python: string; script: string } | null {
  if (modelName === null || !FAKE_CLAUDE_MODEL_NAMES.has(modelName)) {
    return null;
  }
  const script = process.env.SCULPTOR_FAKE_CLAUDE_SCRIPT;
  const python = process.env.SCULPTOR_FAKE_CLAUDE_PYTHON;
  if (script === undefined || python === undefined) {
    return null;
  }
  return { python, script };
}

// A file-changing tool (Write/Edit/...) ran for this agent: bump the workspace's
// diff marker and publish a workspace change so the frontend invalidates its
// git-derived queries (the file tree + diff) and re-fetches (the `diffUpdatedAt`
// cascade). Without this, files an agent creates never appear in the browser.
function markWorkspaceDiffChanged(agent: AgentRow): void {
  const workspace = workspaceForAgent(agent);
  if (workspace === undefined) {
    return;
  }
  setWorkspaceDiffStatus(getOrm(), workspace.objectId, "READY");
  eventBus.publish({
    kind: "data_model_change",
    changedEntities: [{ type: "workspace", id: workspace.objectId }],
  });
}

function claudeEnvironmentFor(agent: AgentRow): ClaudeHarnessEnvironment {
  const workspace = workspaceForAgent(agent);
  const root = workspace?.environmentId ?? "";
  const workDir = workingDirForWorkspace(workspace);
  return {
    getUserHomeDirectory: () => os.homedir(),
    getWorkingDirectory: () => workDir,
    getStatePath: (agentId) => statePath(root, agentId),
    getArtifactsPath: (agentId) => artifactsPath(root, agentId),
    writeFile: (filePath, content) => writeFile(filePath, content),
    readTextFile: (filePath) => readFile(filePath, "utf8"),
  };
}

function piEnvironmentFor(agent: AgentRow): PiHarnessEnvironment {
  const workspace = workspaceForAgent(agent);
  const root = workspace?.environmentId ?? "";
  const workDir = workingDirForWorkspace(workspace);
  return {
    getWorkingDirectory: () => workDir,
    getStatePath: (agentId) => statePath(root, agentId),
    writeFile: (filePath, content) => writeFile(filePath, content),
    readTextFile: (filePath) => readFile(filePath, "utf8"),
  };
}

let runner: AgentRunner | undefined;

// Drop the cached runner so the next getAgentRunner() rebinds to the current
// orm. Tests close/reopen the DB per case, which would otherwise leave the
// runner holding a closed connection.
export function resetAgentRunnerForTests(): void {
  runner = undefined;
}

export function getAgentRunner(): AgentRunner {
  if (runner === undefined) {
    const config = getCurrentUserConfig();
    const harnessFor = createHarnessResolver({
      claude: {
        resolveBinaryPath: () => resolveBinaryPath("CLAUDE") ?? undefined,
        resolveFakeClaudeCommand,
        environmentFor: claudeEnvironmentFor,
        initializationStrategyFor: strategyForAgent,
        enableEntityMentions: config.enable_entity_mentions,
        onDiffNeeded: markWorkspaceDiffChanged,
      },
      pi: {
        resolveBinaryPath: () => resolveBinaryPath("PI") ?? undefined,
        environmentFor: piEnvironmentFor,
        initializationStrategyFor: strategyForAgent,
        apiKeyEnvVarNames: config.pi.api_key_env_var_names as readonly string[],
      },
    });
    runner = new AgentRunner({
      orm: getOrm(),
      harnessFor,
      workingDirectoryFor: (agent) =>
        workingDirForWorkspace(workspaceForAgent(agent)),
      envFor: (agent) => resolveEnv(repoLocalPathForAgent(agent)),
      cache: projectionCache,
    });
  }
  return runner;
}
