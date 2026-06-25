// buildSnapshot — the full `StreamingUpdate` connect snapshot.
//
// Ported from the connect-snapshot path in sculptor/sculptor/web/streams.py
// (the initial dump assembled at L571-596, plus `_convert_to_user_update`
// L872-909 for the initial `user_update`). On connect the client MUST receive a
// full snapshot before any delta (REQ-NFR-001); this reads current state
// (non-deleted repos -> workspaces -> agents) and serves each agent's
// view + chat from the warm cache (Task 4.4) so the whole message log is never
// re-folded synchronously on the hot path.
//
// Scope: `buildSnapshot` takes a Scope, but the actual narrowing of
// `user_update` / `dependencies_status` (ScopeAll-only — project_for_scope,
// streams.py L400/L427/L436) and the per-workspace dicts is Task 4.5. Here we
// build the full ScopeAll snapshot; the dependencies_status / btw / setup
// fields the producing services maintain (Phase 7) are left empty until those
// services exist, exactly as Python emits nothing for them pre-population.

import type { Orm } from "~/db/orm";
import type { AgentRow } from "~/db/schema/agent";
import type { NotificationRow } from "~/db/schema/notification";
import type { RepoRow } from "~/db/schema/repo";
import type { WorkspaceRow } from "~/db/schema/workspace";
import {
  getUserSettings,
  listActiveRepos,
  listAgentsByWorkspace,
  listNotifications,
  listWorkspacesByRepo,
} from "~/db/repositories";
import { ProjectionCache, projectionCache } from "~/projection/cache";
import { foldStateToTaskUpdate } from "~/projection/task_update";
import {
  type DependenciesStatus,
  emptyStreamingUpdate,
  type StreamingUpdate,
  type UserUpdate,
  type WireNotification,
  type WireProject,
  type WireServerSettings,
  type WireUserSettings,
  type WireWorkspace,
} from "~/projection/streaming_update_types";
import { getPrStatusByWorkspaceId } from "~/services/pr_polling/store";

// Minimal scope marker. The full Scope union (ScopeAll/Project/Workspace/Agent)
// and its narrowing live in Task 4.5; here we only need to know whether this is
// the ScopeAll connection (which alone receives user_update /
// dependencies_status — streams.py L484-487).
export interface SnapshotScope {
  kind: "all" | "project" | "workspace" | "agent";
}

export const SCOPE_ALL: SnapshotScope = { kind: "all" };

export interface BuildSnapshotOptions {
  cache?: ProjectionCache;
  // Server settings (SculptorSettings) carried on user_update. The config
  // service (Phase 6) owns its shape; the snapshot just passes it through.
  serverSettings?: WireServerSettings | null;
  // Live dependency status (Phase 6/7 dependency service). ScopeAll-only.
  dependenciesStatus?: DependenciesStatus | null;
}

// --- Wire-row projection helpers -------------------------------------------
//
// Map the internal current-state rows to their wire shapes (repo -> project on
// the wire; see repo.ts). _convert_to_user_update (streams.py L903-909) builds
// the same payload from the equivalent Python models.

export function repoRowToWireProject(row: RepoRow): WireProject {
  return {
    object_id: row.objectId,
    name: row.name,
    user_git_repo_url: row.userGitRepoUrl ?? null,
    is_path_accessible: row.isPathAccessible,
    is_deleted: row.isDeleted,
    default_system_prompt: row.defaultSystemPrompt ?? null,
    workspace_setup_command: row.workspaceSetupCommand ?? null,
    naming_pattern: row.namingPattern ?? null,
  };
}

export function workspaceRowToWire(row: WorkspaceRow): WireWorkspace {
  return {
    object_id: row.objectId,
    project_id: row.projectId,
    description: row.description,
    initialization_strategy: row.initializationStrategy,
    source_branch: row.sourceBranch ?? null,
    target_branch: row.targetBranch ?? null,
    environment_id: row.environmentId ?? null,
    source_git_hash: row.sourceGitHash ?? null,
    is_deleted: row.isDeleted,
    is_open: row.isOpen,
    setup_command_triggered: row.setupCommandTriggered,
    setup_status: row.setupStatus,
    setup_run_id: row.setupRunId ?? null,
    setup_command: row.setupCommand ?? null,
    setup_exit_code: row.setupExitCode ?? null,
    setup_started_at: row.setupStartedAt ?? null,
    setup_finished_at: row.setupFinishedAt ?? null,
    setup_log_path: row.setupLogPath ?? null,
    setup_log_truncated: row.setupLogTruncated,
    diff_status: row.diffStatus,
    diff_updated_at: row.diffUpdatedAt ?? null,
    requested_branch_name: row.requestedBranchName ?? null,
  };
}

export function notificationRowToWire(row: NotificationRow): WireNotification {
  return {
    object_id: row.objectId,
    message: row.message,
    importance: row.importance,
    task_id: row.agentId ?? null,
    project_id: row.projectId ?? null,
  };
}

function userSettingsRowToWire(objectId: string): WireUserSettings {
  return { object_id: objectId };
}

// Build the initial `user_update` from current state: all non-deleted
// projects/workspaces + all current notifications + user_settings + server
// settings. Mirrors the initial dump (streams.py L571-593) folded through
// _convert_to_user_update (L872-909). ScopeAll-only.
function buildInitialUserUpdate(
  orm: Orm,
  repos: RepoRow[],
  workspaces: WorkspaceRow[],
  serverSettings: WireServerSettings | null,
): UserUpdate {
  const notifications: NotificationRow[] = listNotifications(orm);
  const settingsRow = getUserSettings(orm);
  return {
    user_settings: settingsRow === undefined ? null : userSettingsRowToWire(settingsRow.objectId),
    projects: repos.map(repoRowToWireProject),
    workspaces: workspaces.map(workspaceRowToWire),
    settings: serverSettings,
    notifications: notifications.map(notificationRowToWire),
  };
}

// Read current state into a full StreamingUpdate. Reads are indexed
// current-state queries; per-agent chat/view come from the warm cache (folded
// once, lazily). The producing-service fields (branch / PR / setup / btw / deps)
// are left empty until Phase 7 services populate them, just as Python emits
// nothing for them before the relevant observer pushes.
export function buildSnapshot(
  orm: Orm,
  scope: SnapshotScope = SCOPE_ALL,
  options: BuildSnapshotOptions = {},
): StreamingUpdate {
  const cache = options.cache ?? projectionCache;
  const update = emptyStreamingUpdate();

  const repos: RepoRow[] = listActiveRepos(orm);
  const workspaces: WorkspaceRow[] = [];
  const agents: AgentRow[] = [];
  for (const repo of repos) {
    for (const ws of listWorkspacesByRepo(orm, repo.objectId)) {
      workspaces.push(ws);
      for (const agent of listAgentsByWorkspace(orm, ws.objectId)) {
        agents.push(agent);
      }
    }
  }

  for (const agent of agents) {
    const entry = cache.ensure(orm, agent.objectId);
    if (entry === undefined) {
      continue;
    }
    update.task_views_by_task_id[agent.objectId] = entry.view;
    update.task_update_by_task_id[agent.objectId] = foldStateToTaskUpdate(
      agent.objectId,
      entry.foldState,
    );
  }

  // The PR/CI poller publishes pr_status as live deltas; a fresh client also
  // needs the current value in its initial snapshot (else the PR badge is blank
  // until the next poll). Scope narrowing (scope.ts) filters this per-workspace.
  update.pr_status_by_workspace_id = getPrStatusByWorkspaceId();

  // user_update + dependencies_status are ScopeAll-only (streams.py L484-487 /
  // L427/L436). Task 4.5 narrowing drops them for scoped connections; here we
  // populate them only for the ScopeAll snapshot.
  if (scope.kind === "all") {
    update.user_update = buildInitialUserUpdate(
      orm,
      repos,
      workspaces,
      options.serverSettings ?? null,
    );
    update.dependencies_status = options.dependenciesStatus ?? null;
  }

  return update;
}
