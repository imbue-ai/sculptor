import type { FastifyInstance, FastifyRequest } from "fastify";
import type { WebSocket } from "ws";

import {
  getExpectedSessionToken,
  hasValidToken,
  parseCookies,
  SESSION_TOKEN_HEADER_NAME,
  WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE,
} from "~/auth/session_token";
import { getOrm } from "~/db/orm";
import { eventBus } from "~/events";
import type { BusEvent } from "~/events/types";
import { DeltaBuilder } from "~/projection/delta";
import { buildScopeContext, isEmptyUpdate, narrowToScope, parseScope, type Scope, ScopeParseError, toSnapshotScope } from "~/projection/scope";
import { buildSnapshot } from "~/projection/snapshot";
import { streamingUpdateToWire } from "~/projection/to_wire";

const INVALID_SCOPE_CLOSE_CODE = 1008;

function firstHeaderValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

// Enforces the session token at the WS handshake (the global guard skips WS
// upgrades). Accept-then-close 4401 on failure so the browser sees a real close
// frame (Task 1.3 / web/auth.py). Returns true when authorized.
function authorize(socket: WebSocket, request: FastifyRequest, searchParams: URLSearchParams): boolean {
  const expected = getExpectedSessionToken();
  if (expected === undefined) {
    return true;
  }
  const presented = {
    header: firstHeaderValue(request.headers[SESSION_TOKEN_HEADER_NAME]),
    query: searchParams.get(SESSION_TOKEN_HEADER_NAME) ?? undefined,
    cookie: parseCookies(request.headers.cookie)[SESSION_TOKEN_HEADER_NAME],
  };
  if (!hasValidToken(presented, expected)) {
    socket.close(WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE, "Invalid or missing session token");
    return false;
  }
  return true;
}

// GET /api/v1/stream/ws: on connect, send a full snapshot then scope-narrowed
// deltas from the event bus until close. Replaces the Python per-task queue
// fan-out with a single bus subscription (Task 4.1) + narrowing (project_for_scope).
export async function registerStreamWsRoutes(app: FastifyInstance): Promise<void> {
  app.get("/api/v1/stream/ws", { websocket: true }, (socket: WebSocket, request: FastifyRequest) => {
    const url = new URL(request.url, "http://localhost");
    if (!authorize(socket, request, url.searchParams)) {
      return;
    }

    let scope: Scope;
    try {
      scope = parseScope(url.searchParams.get("scope"));
    } catch (error) {
      if (error instanceof ScopeParseError) {
        socket.close(INVALID_SCOPE_CLOSE_CODE, error.message);
        return;
      }
      throw error;
    }

    const orm = getOrm();
    const context = buildScopeContext(orm, scope);

    // Snapshot MUST precede any delta (REQ-NFR-001). Always build the full
    // (ScopeAll) snapshot then narrow uniformly for this connection.
    const snapshot = narrowToScope(buildSnapshot(orm, toSnapshotScope({ kind: "all" })), scope, context);
    socket.send(JSON.stringify(streamingUpdateToWire(snapshot)));

    const builder = new DeltaBuilder({ orm });
    const unsubscribe = eventBus.subscribe((event: BusEvent) => {
      // Keep the agent->workspace map fresh from agent-carrying events so newly
      // created agents narrow correctly without a re-query.
      const agentId = (event as { agentId?: string }).agentId;
      const workspaceId = (event as { workspaceId?: string }).workspaceId;
      if (agentId !== undefined && workspaceId !== undefined) {
        context.agentWorkspaceById.set(agentId, workspaceId);
      }
      const delta = builder.eventToDelta(event);
      if (delta === null) {
        return;
      }
      const narrowed = narrowToScope(delta, scope, context);
      if (isEmptyUpdate(narrowed)) {
        return;
      }
      socket.send(JSON.stringify(streamingUpdateToWire(narrowed)));
    });

    socket.on("close", unsubscribe);
    socket.on("error", unsubscribe);
  });
}
