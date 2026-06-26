import type { AgentRow } from "~/db/schema";

// The Harness contract the AgentSupervisor drives. The concrete Claude / Pi
// harnesses implement it; the registry resolves an agent to its harness.
// Decoupling the supervisor from the harness keeps the orchestrator independent
// of the CLI-launch specifics.

export interface HarnessLaunchContext {
  agent: AgentRow;
  // The workspace working directory the CLI subprocess runs in.
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
  // Start the process without a user turn so it can report its model catalog
  // before the first message (pi: launch + get_available_models). No-op for a
  // harness that needs nothing before the first turn (claude). Optional.
  warmUp?(): void;
}

export interface Harness {
  launch(context: HarnessLaunchContext): HarnessProcess;
}

// Resolves an agent to the harness that should supervise it, or undefined when
// the agent is not chat-supervised here (e.g. a terminal agent or an unknown
// harness). Provided by the registry.
export type HarnessResolver = (agent: AgentRow) => Harness | undefined;
