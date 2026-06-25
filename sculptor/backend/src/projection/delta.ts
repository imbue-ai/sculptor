// eventToDelta — maps a single bus event (Task 4.1) to the minimal
// `StreamingUpdate` patch the client merges.
//
// Ported from `_convert_to_streaming_update` in
// sculptor/sculptor/web/streams.py L757-869 (the per-event dispatch that folds
// source events into an incremental StreamingUpdate), plus:
//   - the data-model-change -> user_update + finished_request_ids fold
//     (`_convert_to_user_update` L872-909, `_process_completed_transaction`
//     L939-946),
//   - the dependencies_status DEDUP (L606 / L646-649): only emit when changed,
//   - the btw_update fold (L826-827).
//
// The dedup is per-connection state in Python (the `last_yielded_deps_status`
// local in `stream_everything`); here it lives on `DeltaBuilder`, one per
// /stream/ws connection (Task 4.5). The pure `eventToDelta` covers the
// stateless cases; the deps dedup MUST go through a builder.

import type { Orm } from "~/db/orm";
import {
  getNotification,
  getRepo,
  getUserSettings,
  getWorkspace,
} from "~/db/repositories";
import { ProjectionCache, projectionCache } from "~/projection/cache";
import type { BusEvent, DataModelChangeEvent } from "~/events/types";
import { foldStateToTaskUpdate } from "~/projection/task_update";
import {
  type BtwUpdate,
  type DependenciesStatus,
  emptyStreamingUpdate,
  type OpenFileUiAction,
  type StreamingUpdate,
  type UserUpdate,
  type WebviewCommandUiAction,
  type WireServerSettings,
} from "~/projection/streaming_update_types";
import {
  notificationRowToWire,
  repoRowToWireProject,
  workspaceRowToWire,
} from "~/projection/snapshot";

export interface DeltaContext {
  orm: Orm;
  cache?: ProjectionCache;
  // Server settings carried on a user_update delta (the config service owns its
  // shape, Phase 6). Only emitted when a data_model_change touches settings.
  serverSettings?: WireServerSettings | null;
}

// Fold a data_model_change event into a user_update + finished_request_ids
// delta. Mirrors _convert_to_user_update (streams.py L872-909): the changed
// entity refs are resolved to their current rows and grouped by kind; the
// originating request id (if any) becomes a finished_request_id. Deleted
// entities are still sent (with is_deleted=true) so the client drops them.
function dataModelChangeToDelta(
  event: DataModelChangeEvent,
  ctx: DeltaContext,
): StreamingUpdate {
  const delta = emptyStreamingUpdate();
  const user: UserUpdate = delta.user_update;
  const projectsById = new Map<
    string,
    ReturnType<typeof repoRowToWireProject>
  >();
  const workspacesById = new Map<
    string,
    ReturnType<typeof workspaceRowToWire>
  >();
  const notifications: ReturnType<typeof notificationRowToWire>[] = [];

  for (const ref of event.changedEntities ?? []) {
    switch (ref.type) {
      case "repo": {
        const row = getRepo(ctx.orm, ref.id);
        if (row !== undefined) {
          projectsById.set(row.objectId, repoRowToWireProject(row));
        }
        break;
      }
      case "workspace": {
        const row = getWorkspace(ctx.orm, ref.id);
        if (row !== undefined) {
          workspacesById.set(row.objectId, workspaceRowToWire(row));
        }
        break;
      }
      case "notification": {
        const row = getNotification(ctx.orm, ref.id);
        if (row !== undefined) {
          notifications.push(notificationRowToWire(row));
        }
        break;
      }
      case "user_settings": {
        const row = getUserSettings(ctx.orm);
        if (row !== undefined) {
          user.user_settings = { object_id: row.objectId };
        }
        break;
      }
      case "agent":
        // Agent changes flow through the agent_status / agent_message events,
        // not user_update (streams.py keeps tasks out of _convert_to_user_update).
        break;
    }
  }

  user.projects = [...projectsById.values()];
  user.workspaces = [...workspacesById.values()];
  user.notifications = notifications;
  // SculptorSettings is carried on user_update whenever it accompanies the
  // change (streams.py L802-803 appends it to user_update_sources).
  if (ctx.serverSettings !== undefined) {
    user.settings = ctx.serverSettings;
  }

  // _process_completed_transaction (streams.py L944-945): a non-null request id
  // becomes a finished_request_id.
  if (event.requestId !== undefined && event.requestId !== null) {
    delta.finished_request_ids = [event.requestId];
  }
  return delta;
}

// Per-connection delta builder. Holds the dependencies_status dedup state
// (streams.py's `last_yielded_deps_status` local). One instance per /stream/ws
// connection (Task 4.5 owns wiring this to a subscription).
export class DeltaBuilder {
  private lastDependenciesStatus: DependenciesStatus | null = null;
  private readonly ctx: DeltaContext;
  private readonly cache: ProjectionCache;

  constructor(ctx: DeltaContext) {
    this.ctx = ctx;
    this.cache = ctx.cache ?? projectionCache;
  }

  // Map an event to its StreamingUpdate patch, or null if the event produces no
  // visible change (e.g. a duplicate dependencies_status — streams.py L646-647).
  eventToDelta(event: BusEvent): StreamingUpdate | null {
    switch (event.kind) {
      case "agent_message": {
        // The runner (MessageWriter / recordUserMessage) is the SOLE applier of
        // the message to the warm cache; the delta path only READS the
        // already-folded entry (cache.ts: "the runner pushes messages in,
        // snapshot/delta reads them out"). Re-applying here would double-fold the
        // message on the process-wide cache — harmless for plain text (the fold
        // dedups by id) but it corrupts the streaming start-index advancement,
        // duplicating every streamed tool/text segment across a multi-turn reply.
        const entry = this.cache.ensure(this.ctx.orm, event.agentId);
        if (entry === undefined) {
          return null;
        }
        const delta = emptyStreamingUpdate();
        delta.task_update_by_task_id[event.agentId] = foldStateToTaskUpdate(
          event.agentId,
          entry.foldState,
        );
        delta.task_views_by_task_id[event.agentId] = entry.view;
        return delta;
      }
      case "agent_status": {
        const entry = this.cache.refreshAgent(this.ctx.orm, event.agentId);
        if (entry === undefined) {
          // Agent was deleted; nothing to add to task_views (the client drops
          // it via the user_update / scope-close path).
          return null;
        }
        const delta = emptyStreamingUpdate();
        delta.task_views_by_task_id[event.agentId] = entry.view;
        return delta;
      }
      case "data_model_change":
        return dataModelChangeToDelta(event, this.ctx);
      case "dependencies_status": {
        const status = event.status as DependenciesStatus | null;
        // Dedup (streams.py L646-649): suppress an identical re-emit.
        if (deepEqual(status, this.lastDependenciesStatus)) {
          return null;
        }
        this.lastDependenciesStatus = status;
        const delta = emptyStreamingUpdate();
        delta.dependencies_status = status;
        return delta;
      }
      case "btw_update": {
        const delta = emptyStreamingUpdate();
        delta.btw_update = event.update as unknown as BtwUpdate;
        return delta;
      }
      case "workspace_branch": {
        const delta = emptyStreamingUpdate();
        delta.workspace_branch_by_workspace_id[event.workspaceId] =
          (event.status as StreamingUpdate["workspace_branch_by_workspace_id"][string]) ??
          null;
        return delta;
      }
      case "workspace_remote_branches": {
        const delta = emptyStreamingUpdate();
        delta.workspace_remote_branches_by_workspace_id[event.workspaceId] =
          (event.status as StreamingUpdate["workspace_remote_branches_by_workspace_id"][string]) ??
          null;
        return delta;
      }
      case "pr_status": {
        const delta = emptyStreamingUpdate();
        delta.pr_status_by_workspace_id[event.workspaceId] =
          (event.status as StreamingUpdate["pr_status_by_workspace_id"][string]) ??
          null;
        return delta;
      }
      case "workspace_setup_status": {
        const delta = emptyStreamingUpdate();
        delta.workspace_setup_status_by_workspace_id[event.workspaceId] =
          event.status as unknown as StreamingUpdate["workspace_setup_status_by_workspace_id"][string];
        return delta;
      }
      case "workspace_setup_output": {
        const delta = emptyStreamingUpdate();
        delta.workspace_setup_output_by_workspace_id[event.workspaceId] = [
          event.chunk as unknown as StreamingUpdate["workspace_setup_output_by_workspace_id"][string][number],
        ];
        return delta;
      }
      case "ui_open_file": {
        const delta = emptyStreamingUpdate();
        delta.ui_open_file_by_workspace_id[event.workspaceId] =
          event.action as unknown as OpenFileUiAction;
        return delta;
      }
      case "ui_webview_command": {
        const delta = emptyStreamingUpdate();
        delta.ui_webview_command_by_workspace_id[event.workspaceId] =
          event.command as unknown as WebviewCommandUiAction;
        return delta;
      }
    }
  }
}

// Convenience for stateless callers / tests: builds a fresh DeltaBuilder per
// call, so the dependencies_status dedup does NOT carry across calls. Use a
// long-lived DeltaBuilder for a real connection.
export function eventToDelta(
  event: BusEvent,
  ctx: DeltaContext,
): StreamingUpdate | null {
  return new DeltaBuilder(ctx).eventToDelta(event);
}

// Structural equality for the dependencies_status dedup (Python compares full
// Pydantic models for equality; JSON value compare is faithful for this shape).
function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
