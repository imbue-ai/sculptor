import { spawn } from "node:child_process";

import { getOrm } from "~/db/orm";
import { getAgent, getWorkspace } from "~/db/repositories";
import type { AgentRow } from "~/db/schema";
import { eventBus } from "~/events";
import { getRepo } from "~/db/repositories";
import { workingDirectory } from "~/environment/paths";
import { localPathFromRepo } from "~/services/project";
import { resolveBinaryPath } from "~/services/dependencies";

// `/btw` ("by the way") service (services/btw_service + claude_code_sdk/
// btw_process_manager.py). A read-only side-question against an agent's Claude
// session: it forks the session (no persistence), runs a single Haiku turn with
// a tools-disabled, read-only system prompt, and streams the answer back as
// BtwUpdate events. It NEVER persists a message or touches the agent's
// run_state, so the main turn is undisturbed. A second /btw for the same agent
// aborts the first (the popup's "replace" guarantee).

const BTW_SYSTEM_PROMPT =
  "You are a read-only assistant. You cannot run any tools. Answer the user's question about the conversation above.";

export type BtwState = "running" | "done" | "error" | "aborted";

export interface BtwUpdate extends Record<string, unknown> {
  workspace_id: string;
  agent_id: string;
  request_id: string;
  state: BtwState;
  answer: string;
  error_message: string | null;
}

// Runs one forked-session Claude turn and resolves the answer text. Injected so
// tests don't spawn a real claude. `signal` aborts the in-flight subprocess.
export type BtwRunner = (args: {
  binaryPath: string;
  sessionId: string;
  question: string;
  cwd: string;
  signal: AbortSignal;
}) => Promise<string>;

function buildBtwArgs(sessionId: string, question: string): string[] {
  return [
    "--resume",
    sessionId,
    "--fork-session",
    "--no-session-persistence",
    "-p",
    question,
    "--model",
    "haiku",
    "--tools",
    "",
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--append-system-prompt",
    BTW_SYSTEM_PROMPT,
    "--output-format=stream-json",
    "--include-partial-messages",
    "--verbose",
    "--dangerously-skip-permissions",
  ];
}

// Default runner: spawn claude and accumulate the assistant text from the
// stream-json output. Read-only — no session is persisted (--no-session-
// persistence + --fork-session).
const defaultBtwRunner: BtwRunner = ({
  binaryPath,
  sessionId,
  question,
  cwd,
  signal,
}) =>
  new Promise<string>((resolve, reject) => {
    const child = spawn(binaryPath, buildBtwArgs(sessionId, question), {
      cwd,
      env: { ...process.env, IS_SANDBOX: "1" },
      signal,
    });
    let answer = "";
    let buffer = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      buffer += chunk;
      let newline: number;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line === "") {
          continue;
        }
        try {
          const event = JSON.parse(line) as {
            type?: string;
            message?: { content?: Array<{ type?: string; text?: string }> };
          };
          if (
            event.type === "assistant" &&
            Array.isArray(event.message?.content)
          ) {
            for (const block of event.message.content) {
              if (block.type === "text" && typeof block.text === "string") {
                answer += block.text;
              }
            }
          }
        } catch {
          // Non-JSON line (verbose noise) — ignore.
        }
      }
    });
    child.on("error", reject);
    child.on("close", () => resolve(answer));
  });

function workingDirForAgent(agent: AgentRow): string | null {
  if (agent.workspaceId === null) {
    return null;
  }
  const workspace = getWorkspace(getOrm(), agent.workspaceId);
  if (workspace === undefined || workspace.environmentId === null) {
    return null;
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

// Resolves the per-agent btw launch context (the Claude session to fork, the
// binary, and the working directory). Injected so tests can supply a context
// without an installed claude binary.
export interface BtwContext {
  sessionId: string;
  binaryPath: string;
  cwd: string;
}

export type BtwContextResolver = (agentId: string) => BtwContext | null;

const defaultContextResolver: BtwContextResolver = (agentId) => {
  const agent = getAgent(getOrm(), agentId);
  const sessionId = agent?.claudeSessionId ?? null;
  const binaryPath = resolveBinaryPath("CLAUDE") ?? undefined;
  const cwd = agent !== undefined ? workingDirForAgent(agent) : null;
  if (sessionId === null || binaryPath === undefined || cwd === null) {
    return null;
  }
  return { sessionId, binaryPath, cwd };
};

export interface BtwServiceDeps {
  runner: BtwRunner;
  resolveContext: BtwContextResolver;
}

export class BtwService {
  private readonly inFlight = new Map<string, AbortController>();
  private readonly runner: BtwRunner;
  private readonly resolveContext: BtwContextResolver;

  constructor(deps: Partial<BtwServiceDeps> = {}) {
    this.runner = deps.runner ?? defaultBtwRunner;
    this.resolveContext = deps.resolveContext ?? defaultContextResolver;
  }

  private publish(update: BtwUpdate): void {
    eventBus.publish({
      kind: "btw_update",
      agentId: update.agent_id,
      workspaceId: update.workspace_id,
      update,
    });
  }

  // Kick off a read-only side-question. Fire-and-forget: the answer streams via
  // btw_update events. Never mutates the agent's messages or run_state.
  runBtwForAgent(
    workspaceId: string,
    agentId: string,
    requestId: string,
    question: string,
  ): void {
    const base = (
      state: BtwState,
      answer: string,
      errorMessage: string | null,
    ): BtwUpdate => ({
      workspace_id: workspaceId,
      agent_id: agentId,
      request_id: requestId,
      state,
      answer,
      error_message: errorMessage,
    });

    const context = this.resolveContext(agentId);
    if (context === null) {
      this.publish(
        base("error", "", "No active Claude session for this agent"),
      );
      return;
    }

    // Second /btw for the same agent replaces the first.
    const previous = this.inFlight.get(agentId);
    if (previous !== undefined) {
      previous.abort();
    }
    const controller = new AbortController();
    this.inFlight.set(agentId, controller);

    this.publish(base("running", "", null));
    void this.runner({
      binaryPath: context.binaryPath,
      sessionId: context.sessionId,
      question,
      cwd: context.cwd,
      signal: controller.signal,
    })
      .then((answer) => {
        if (this.inFlight.get(agentId) === controller) {
          this.inFlight.delete(agentId);
        }
        this.publish(base("done", answer, null));
      })
      .catch((error: unknown) => {
        if (this.inFlight.get(agentId) === controller) {
          this.inFlight.delete(agentId);
        }
        const aborted = error instanceof Error && error.name === "AbortError";
        this.publish(
          base(
            aborted ? "aborted" : "error",
            "",
            aborted
              ? null
              : error instanceof Error
                ? error.message
                : String(error),
          ),
        );
      });
  }
}

let singleton: BtwService | undefined;

export function getBtwService(): BtwService {
  if (singleton === undefined) {
    singleton = new BtwService();
  }
  return singleton;
}

export function resetBtwServiceForTests(): void {
  singleton = undefined;
}
