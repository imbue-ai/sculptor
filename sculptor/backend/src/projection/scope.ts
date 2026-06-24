import type { Orm } from "~/db/orm";
import { listActiveRepos, listAgentsByWorkspace, listWorkspacesByRepo } from "~/db/repositories";
import type { SnapshotScope } from "~/projection/snapshot";
import { emptyUserUpdate, type StreamingUpdate } from "~/projection/streaming_update_types";

// The streaming scope, parsed from the ?scope= query param and used to narrow a
// StreamingUpdate. Ports the Scope union + parse_scope_query_param +
// project_for_scope from web/streams.py (L221-450).
export type Scope =
  | { kind: "all" }
  | { kind: "project"; projectId: string }
  | { kind: "workspace"; workspaceId: string }
  | { kind: "agent"; agentId: string };

export class ScopeParseError extends Error {}

// "all"/empty -> ScopeAll; "project:<id>" / "workspace:<id>" / "agent:<id>" ->
// the scoped variants. Mirrors parse_scope_query_param (streams.py L243).
export function parseScope(value: string | null | undefined): Scope {
  if (value === undefined || value === null || value === "" || value === "all") {
    return { kind: "all" };
  }
  const separator = value.indexOf(":");
  if (separator <= 0 || separator === value.length - 1) {
    throw new ScopeParseError(`invalid scope: '${value}'`);
  }
  const kind = value.slice(0, separator);
  const remainder = value.slice(separator + 1);
  if (kind === "project") {
    return { kind: "project", projectId: remainder };
  }
  if (kind === "workspace") {
    return { kind: "workspace", workspaceId: remainder };
  }
  if (kind === "agent") {
    return { kind: "agent", agentId: remainder };
  }
  throw new ScopeParseError(`invalid scope: '${value}'`);
}

export function toSnapshotScope(scope: Scope): SnapshotScope {
  return { kind: scope.kind };
}

export interface ScopeContext {
  // Workspace ids whose keyed entries survive narrowing (a project's workspaces,
  // the single workspace, or empty for ScopeAgent).
  scopedWorkspaceIds: Set<string>;
  // agent id -> its workspace id, for narrowing the agent-keyed task dicts.
  agentWorkspaceById: Map<string, string | null>;
}

// Resolves the scope's workspace set + agent->workspace map from current state.
// For ScopeProject the workspace set is computed once at connect (matching the
// Python snapshot of project_workspace_ids, streams.py L467-473).
export function buildScopeContext(orm: Orm, scope: Scope): ScopeContext {
  const scopedWorkspaceIds = new Set<string>();
  const agentWorkspaceById = new Map<string, string | null>();
  for (const repo of listActiveRepos(orm)) {
    for (const workspace of listWorkspacesByRepo(orm, repo.objectId)) {
      if (scope.kind === "project" && workspace.projectId === scope.projectId) {
        scopedWorkspaceIds.add(workspace.objectId);
      } else if (scope.kind === "workspace" && workspace.objectId === scope.workspaceId) {
        scopedWorkspaceIds.add(workspace.objectId);
      }
      for (const agent of listAgentsByWorkspace(orm, workspace.objectId)) {
        agentWorkspaceById.set(agent.objectId, workspace.objectId);
      }
    }
  }
  return { scopedWorkspaceIds, agentWorkspaceById };
}

function filterRecord<T>(record: Record<string, T>, keep: (key: string) => boolean): Record<string, T> {
  const out: Record<string, T> = {};
  for (const [key, value] of Object.entries(record)) {
    if (keep(key)) {
      out[key] = value;
    }
  }
  return out;
}

// Narrows a StreamingUpdate to the data a scope permits, porting
// project_for_scope (streams.py L400-450): agent-keyed dicts filter on the
// agent's workspace being in scope (or the agent id for ScopeAgent),
// workspace-keyed dicts filter on the scoped workspace set, and
// user_update / finished_request_ids / dependencies_status / btw_update are
// dropped (ScopeAll-only).
export function narrowToScope(update: StreamingUpdate, scope: Scope, ctx: ScopeContext): StreamingUpdate {
  if (scope.kind === "all") {
    return update;
  }
  const keepWorkspace = (workspaceId: string): boolean => ctx.scopedWorkspaceIds.has(workspaceId);
  const keepAgent = (agentId: string): boolean => {
    if (scope.kind === "agent") {
      return agentId === scope.agentId;
    }
    const workspaceId = ctx.agentWorkspaceById.get(agentId);
    return workspaceId !== undefined && workspaceId !== null && ctx.scopedWorkspaceIds.has(workspaceId);
  };

  const views = filterRecord(update.task_views_by_task_id, keepAgent);
  return {
    task_update_by_task_id: filterRecord(update.task_update_by_task_id, (key) => key in views),
    task_views_by_task_id: views,
    user_update: emptyUserUpdate(),
    workspace_branch_by_workspace_id: filterRecord(update.workspace_branch_by_workspace_id, keepWorkspace),
    workspace_remote_branches_by_workspace_id: filterRecord(
      update.workspace_remote_branches_by_workspace_id,
      keepWorkspace,
    ),
    pr_status_by_workspace_id: filterRecord(update.pr_status_by_workspace_id, keepWorkspace),
    finished_request_ids: [],
    dependencies_status: null,
    workspace_setup_status_by_workspace_id: filterRecord(update.workspace_setup_status_by_workspace_id, keepWorkspace),
    workspace_setup_output_by_workspace_id: filterRecord(update.workspace_setup_output_by_workspace_id, keepWorkspace),
    btw_update: null,
    ui_open_file_by_workspace_id: filterRecord(update.ui_open_file_by_workspace_id, keepWorkspace),
    ui_webview_command_by_workspace_id: filterRecord(update.ui_webview_command_by_workspace_id, keepWorkspace),
  };
}

export function isEmptyUpdate(update: StreamingUpdate): boolean {
  const u = update.user_update;
  const userEmpty =
    u.user_settings === null &&
    u.settings === null &&
    u.projects.length === 0 &&
    u.workspaces.length === 0 &&
    u.notifications.length === 0;
  return (
    userEmpty &&
    update.finished_request_ids.length === 0 &&
    update.dependencies_status === null &&
    update.btw_update === null &&
    Object.keys(update.task_update_by_task_id).length === 0 &&
    Object.keys(update.task_views_by_task_id).length === 0 &&
    Object.keys(update.workspace_branch_by_workspace_id).length === 0 &&
    Object.keys(update.workspace_remote_branches_by_workspace_id).length === 0 &&
    Object.keys(update.pr_status_by_workspace_id).length === 0 &&
    Object.keys(update.workspace_setup_status_by_workspace_id).length === 0 &&
    Object.keys(update.workspace_setup_output_by_workspace_id).length === 0 &&
    Object.keys(update.ui_open_file_by_workspace_id).length === 0 &&
    Object.keys(update.ui_webview_command_by_workspace_id).length === 0
  );
}
