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
import { getAgent, getWorkspace } from "~/db/repositories";
import { getTerminalManager } from "~/terminal/instance";
import type { PtyProcess } from "~/terminal/pty";
import { getWorkspaceWorkingDirectory } from "~/services/workspace";
import { localPathFromRepo } from "~/services/project";
import { getRepo } from "~/db/repositories";
import { workingDirectory } from "~/environment/paths";
import { resolveEnv } from "~/services/env_injection/env";

// Terminal WebSocket channels (web/app.py). The xterm contract (RW-API-2):
//   server -> client: raw PTY output as BINARY frames.
//   client -> server: BINARY frames are keystrokes (written to the PTY);
//                     TEXT frames are JSON {type:"resize", cols, rows}.
const TERMINAL_NOT_FOUND_CLOSE_CODE = 4404;

function firstHeaderValue(
  value: string | string[] | undefined,
): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function authorize(
  socket: WebSocket,
  request: FastifyRequest,
  searchParams: URLSearchParams,
): boolean {
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
    socket.close(
      WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE,
      "Invalid or missing session token",
    );
    return false;
  }
  return true;
}

// Bridge a PTY to the socket: stream output as binary, forward keystrokes, and
// apply resize JSON. (PtyProcess.onData has no unsubscribe; the readyState
// guard drops writes after the socket closes.)
function bridge(socket: WebSocket, pty: PtyProcess): void {
  pty.onData((data) => {
    if (socket.readyState === socket.OPEN) {
      socket.send(Buffer.from(data, "utf8"), { binary: true });
    }
  });
  socket.on("message", (data: Buffer, isBinary: boolean) => {
    if (isBinary) {
      pty.write(data.toString("utf8"));
      return;
    }
    try {
      const message = JSON.parse(data.toString("utf8")) as {
        type?: string;
        cols?: number;
        rows?: number;
      };
      if (
        message.type === "resize" &&
        typeof message.cols === "number" &&
        typeof message.rows === "number"
      ) {
        pty.resize(message.cols, message.rows);
      }
    } catch {
      // Ignore malformed control frames.
    }
  });
}

function workspaceWorkingDirOrNull(workspaceId: string): string | null {
  try {
    return getWorkspaceWorkingDirectory(workspaceId);
  } catch {
    return null;
  }
}

// The `.env`-injected environment for a workspace's repo (Task 7.6, per-repo
// over global), merged into the terminal subprocess.
function repoEnvForWorkspace(workspaceId: string): Record<string, string> {
  const workspace = getWorkspace(getOrm(), workspaceId);
  const repo =
    workspace === undefined
      ? undefined
      : getRepo(getOrm(), workspace.projectId);
  return resolveEnv(repo !== undefined ? localPathFromRepo(repo) : null);
}

export async function registerTerminalWsRoutes(
  app: FastifyInstance,
): Promise<void> {
  app.get(
    "/api/v1/workspaces/:workspace_id/terminal/:index/ws",
    { websocket: true },
    (socket: WebSocket, request: FastifyRequest) => {
      const url = new URL(request.url, "http://localhost");
      if (!authorize(socket, request, url.searchParams)) {
        return;
      }
      const { workspace_id: workspaceId, index } = request.params as {
        workspace_id: string;
        index: string;
      };
      const cwd = workspaceWorkingDirOrNull(workspaceId);
      if (cwd === null) {
        socket.close(
          TERMINAL_NOT_FOUND_CLOSE_CODE,
          `Workspace ${workspaceId} not found`,
        );
        return;
      }
      const pty = getTerminalManager().getOrCreateTerminal(
        Number.parseInt(index, 10),
        { cwd, extraEnv: repoEnvForWorkspace(workspaceId) },
      );
      bridge(socket, pty);
    },
  );

  app.get(
    "/api/v1/agents/:agent_id/terminal/ws",
    { websocket: true },
    (socket: WebSocket, request: FastifyRequest) => {
      const url = new URL(request.url, "http://localhost");
      if (!authorize(socket, request, url.searchParams)) {
        return;
      }
      const { agent_id: agentId } = request.params as { agent_id: string };
      const orm = getOrm();
      const agent = getAgent(orm, agentId);
      if (agent === undefined || agent.isDeleted) {
        socket.close(
          TERMINAL_NOT_FOUND_CLOSE_CODE,
          `Agent ${agentId} not found`,
        );
        return;
      }
      const workspace =
        agent.workspaceId === null
          ? undefined
          : getWorkspace(orm, agent.workspaceId);
      const repo =
        workspace === undefined ? undefined : getRepo(orm, workspace.projectId);
      const cwd =
        workspace?.environmentId == null
          ? process.cwd()
          : workingDirectory(
              workspace.environmentId,
              workspace.initializationStrategy,
              repo !== undefined
                ? (localPathFromRepo(repo) ?? undefined)
                : undefined,
            );
      const pty = getTerminalManager().getOrCreateAgentTerminal(agentId, {
        cwd,
        extraEnv: resolveEnv(
          repo !== undefined ? localPathFromRepo(repo) : null,
        ),
      });
      bridge(socket, pty);
    },
  );
}
