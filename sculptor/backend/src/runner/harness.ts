import type { AgentRow } from "~/db/schema";

// The Harness contract the AgentSupervisor (Task 5.1) drives. The concrete
// Claude / Pi harnesses (Tasks 5.3-5.5) implement it; the registry (Task 5.6)
// resolves an agent to its harness. Decoupling the supervisor from the harness
// keeps the orchestrator (this phase) independent of the CLI-launch specifics.

export interface HarnessLaunchContext {
  agent: AgentRow;
  // The workspace working directory (Task 3.1) the CLI subprocess runs in.
  workingDirectory: string;
  env?: Record<string, string>;
}

export interface HarnessExitResult {
  // SerializedException-shaped error, or undefined on a clean exit.
  error?: unknown;
}

export interface HarnessProcess {
  // The harness emits PersistentMessageTypes JSON dicts (as stored in
  // agent_message.message), in order.
  onMessage(callback: (message: Record<string, unknown>) => void): void;
  onExit(callback: (result: HarnessExitResult) => void): void;
  // Forward a user chat message into the running session.
  sendUserMessage(message: Record<string, unknown>): void;
  interrupt(): void;
  stop(): void;
  // /clear: reset the model session in-place. Harnesses that re-resolve their
  // session every turn (claude) need nothing here (the on-disk session files are
  // cleared by the caller); a persistent process (pi) must tell the CLI to start
  // a new session. Optional — defaults to a no-op.
  clearSession?(): void;
}

export interface Harness {
  launch(context: HarnessLaunchContext): HarnessProcess;
}

// Resolves an agent to the harness that should supervise it, or undefined when
// the agent is not chat-supervised here (e.g. a terminal agent — Task 3.4 — or
// an unknown harness). Provided by the registry (Task 5.6).
export type HarnessResolver = (agent: AgentRow) => Harness | undefined;
