import type { FastifyInstance, FastifyRequest } from "fastify";
import type { WebSocket } from "ws";

import {
  getExpectedSessionToken,
  hasValidToken,
  parseCookies,
  SESSION_TOKEN_HEADER_NAME,
  WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE,
} from "~/auth/session_token";
import { getSculptorFolder } from "~/config/sculptor_folder";
import { resolvePort } from "~/config/port";
import { getOrm } from "~/db/orm";
import { getAgent, getWorkspace } from "~/db/repositories";
import { getTerminalManager } from "~/terminal/instance";
import type { PtyProcess } from "~/terminal/pty";
import { getWorkspaceWorkingDirectory } from "~/services/workspace";
import { localPathFromRepo } from "~/services/project";
import { getRepo } from "~/db/repositories";
import { workingDirectory } from "~/environment/paths";
import { resolveEnv } from "~/services/env_injection/env";
import {
  getRegistrationsDir,
  renderTerminalCommand,
} from "~/services/terminal_agent_registry/registry";

// A registered terminal agent runs its registration's launch command (or resume
// command, when the program reported a session id) in the freshly-spawned shell;
// plain terminal agents get a bare shell. Ports run_terminal_agent
// launch_command_for_start + write_launch_command.
function launchCommandForAgentTerminal(
  agentConfig: Record<string, unknown>,
  terminalSessionId: string | null,
): string | null {
  if (agentConfig["object_type"] !== "RegisteredTerminalAgentConfig") {
    return null;
  }
  const context = {
    sculptorDirectory: getSculptorFolder(),
    terminalAgentsDirectory: getRegistrationsDir(),
    sessionId: terminalSessionId ?? undefined,
  };
  const resumeTemplate = agentConfig["resume_command_template"];
  if (terminalSessionId !== null && typeof resumeTemplate === "string") {
    return renderTerminalCommand(resumeTemplate, context);
  }
  const launchCommand = agentConfig["launch_command"];
  if (typeof launchCommand !== "string") {
    return null;
  }
  return renderTerminalCommand(launchCommand, context);
}

// Terminal WebSocket channels (web/app.py). The xterm contract:
//   server -> client: raw PTY output as BINARY frames.
//   client -> server: BINARY frames are keystrokes (written to the PTY);
//                     TEXT frames are JSON {type:"resize", cols, rows}.
const TERMINAL_NOT_FOUND_CLOSE_CODE = 4404;

// A terminal `:index` is a non-negative integer. Reject anything else rather
// than letting Number.parseInt coerce it to NaN (which would collapse every
// malformed request onto one shared NaN-keyed terminal).
function parseTerminalIndex(index: string): number | null {
  return /^\d+$/.test(index) ? Number.parseInt(index, 10) : null;
}

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

// Bridge a PTY to the socket: replay the session so far, stream new output as
// binary, forward keystrokes, apply resize JSON, and close the socket when the
// shell exits (so the frontend renders the "[Process exited]" notice the PTY
// emitted just before). The PTY stays alive across a disconnect, so a reopen
// replays the buffer and shows the prior prompt.
// node-pty's onExit registers a listener with no removal handle, and a PTY
// outlives the individual sockets that attach to it (it stays alive across a
// disconnect so a reconnect can replay the buffer). So the exit->close bridge is
// installed once per PTY, with the currently-attached socket tracked separately
// — re-registering an exit listener on every connect would leak one per
// reconnect on a reused PTY.
const activeSocketByPty = new WeakMap<PtyProcess, WebSocket>();
const exitBridgedPtys = new WeakSet<PtyProcess>();

function bridge(socket: WebSocket, pty: PtyProcess): void {
  const sendOutput = (data: string): void => {
    if (socket.readyState === socket.OPEN) {
      socket.send(Buffer.from(data, "utf8"), { binary: true });
    }
  };
  const { buffered, unsubscribe } = pty.subscribe(sendOutput);
  if (buffered) {
    sendOutput(buffered);
  }
  activeSocketByPty.set(pty, socket);
  socket.on("close", () => {
    unsubscribe();
    if (activeSocketByPty.get(pty) === socket) {
      activeSocketByPty.delete(pty);
    }
  });
  if (!exitBridgedPtys.has(pty)) {
    exitBridgedPtys.add(pty);
    // The shell exits at most once; close whichever socket is attached at that
    // point so the frontend renders the "[Process exited]" notice the PTY
    // emitted just before.
    pty.onExit(() => {
      const attached = activeSocketByPty.get(pty);
      if (
        attached !== undefined &&
        (attached.readyState === attached.OPEN ||
          attached.readyState === attached.CONNECTING)
      ) {
        attached.close();
      }
    });
  }
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

// The `.env`-injected environment for a workspace's repo (per-repo over
// global), merged into the terminal subprocess.
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
      const terminalIndex = parseTerminalIndex(index);
      if (terminalIndex === null) {
        socket.close(
          TERMINAL_NOT_FOUND_CLOSE_CODE,
          `Terminal ${index} not found`,
        );
        return;
      }
      const cwd = workspaceWorkingDirOrNull(workspaceId);
      if (cwd === null) {
        socket.close(
          TERMINAL_NOT_FOUND_CLOSE_CODE,
          `Workspace ${workspaceId} not found`,
        );
        return;
      }
      const pty = getTerminalManager().getOrCreateTerminal(
        terminalIndex,
        { cwd, extraEnv: repoEnvForWorkspace(workspaceId) },
        workspaceId,
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
      const manager = getTerminalManager();
      const isNewTerminal = manager.getAgentTerminal(agentId) === undefined;
      // The SCULPT_* identity vars so a bare `sculpt signal …` inside the agent's
      // terminal reaches this backend and targets this agent (build.py
      // sculpt_identity_env; agent-scoped, so it includes SCULPT_AGENT_ID).
      const sculptEnv: Record<string, string> = {
        SCULPT_API_PORT: String(resolvePort()),
        SCULPT_AGENT_ID: agentId,
      };
      if (workspace !== undefined) {
        sculptEnv["SCULPT_WORKSPACE_ID"] = workspace.objectId;
        sculptEnv["SCULPT_PROJECT_ID"] = workspace.projectId;
      }
      const pty = manager.getOrCreateAgentTerminal(agentId, {
        cwd,
        extraEnv: {
          ...resolveEnv(repo !== undefined ? localPathFromRepo(repo) : null),
          ...sculptEnv,
        },
      });
      if (isNewTerminal) {
        const launchCommand = launchCommandForAgentTerminal(
          agent.agentConfig,
          agent.terminalSessionId ?? null,
        );
        if (launchCommand !== null) {
          pty.write(`${launchCommand}\n`);
        }
      }
      bridge(socket, pty);
    },
  );
}
