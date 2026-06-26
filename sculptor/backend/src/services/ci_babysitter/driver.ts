import { getCurrentUserConfig } from "~/config/user_config";
import { getOrm } from "~/db/orm";
import { listAgentMessages } from "~/db/repositories/agent_messages";
import { listAgentsByWorkspace } from "~/db/repositories/agents";
import type { AgentRow } from "~/db/schema";
import { getLogger } from "~/logging/logger";
import { scanTerminalSignalState } from "~/projection/status";
import { getAgentService } from "~/services/agent";
import { getRegistration } from "~/services/terminal_agent_registry/registry";
import { getTerminalManager } from "~/terminal/instance";

// The babysitter's agent-resolution + delivery seam. The coordinator owns the
// policy (transitions, dedup, cap, pause); the driver owns "which agent, and how
// the prompt physically reaches it" — a chat agent gets a queued message, a
// registered opt-in terminal agent gets a guarded PTY write once it's at its
// prompt. Ports services/ci_babysitter_service/coordinator.py's
// _resolve_babysitter_agent / _ensure_babysitter_task / deliver_prompt_to_agent.

const BABYSITTER_TITLE = "CI Babysitter";

// Persistent disabled reasons surfaced when the MRU is a terminal that can't
// receive automated prompts, or when a pinned harness is no longer available.
// The copy is shared with the tests, which assert on a fragment of it.
export const DISABLED_REASON_MRU_NON_DRIVEABLE =
  "Your most-recent agent is a terminal that can't receive automated prompts, so the CI Babysitter can't act here. Pick a specific agent in CI Babysitter settings, or use a chat or prompt-enabled terminal agent.";
export const DISABLED_REASON_PINNED_UNAVAILABLE =
  "The CI Babysitter's selected agent is no longer available. Choose another in CI Babysitter settings.";
export const TRANSIENT_REASON_UNREACHABLE =
  "Couldn't reach the terminal agent's prompt; will retry on the next failure.";

const FALLBACK_MODEL = "CLAUDE-4-OPUS-200K";
const TERMINAL_READINESS_BACKSTOP_MS = 30_000;
const TERMINAL_READINESS_POLL_MS = 500;

export type ResolvedBabysitterAgent =
  | { kind: "chat"; agentType: "claude" | "pi" }
  | { kind: "terminal"; registrationId: string }
  | { kind: "disabled"; reason: string; transient: boolean };

export interface BabysitterDriver {
  // Which agent the babysitter drives for this workspace (config pin or MRU).
  resolve(workspaceId: string, projectId: string): ResolvedBabysitterAgent;
  // Ensure the CI Babysitter agent exists and deliver `prompt` to it.
  deliver(
    workspaceId: string,
    projectId: string,
    resolved: ResolvedBabysitterAgent,
    prompt: string,
  ): void;
}

function configType(agent: AgentRow): string {
  return String(agent.agentConfig.object_type ?? "");
}

function isTerminalConfig(agent: AgentRow): boolean {
  const type = configType(agent);
  return (
    type === "TerminalAgentConfig" || type === "RegisteredTerminalAgentConfig"
  );
}

// The workspace's non-deleted agents, most-recent first, excluding the
// babysitter's own task. Never iterate past the most-recent agent to reach an
// older one — that is exactly the tool-switch this feature removes.
function workspaceAgentsMostRecentFirst(workspaceId: string): AgentRow[] {
  return listAgentsByWorkspace(getOrm(), workspaceId)
    .filter(
      (agent) =>
        !agent.isDeleted &&
        !agent.isDeleting &&
        agent.title !== BABYSITTER_TITLE,
    )
    .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

function selectModelForWorkspace(workspaceId: string): string {
  for (const agent of workspaceAgentsMostRecentFirst(workspaceId)) {
    if (isTerminalConfig(agent)) {
      continue;
    }
    if (agent.defaultModel !== null && agent.defaultModel !== "") {
      return agent.defaultModel;
    }
  }
  const config = getCurrentUserConfig();
  return config.default_llm && config.default_llm !== ""
    ? config.default_llm
    : FALLBACK_MODEL;
}

function findBabysitterAgent(workspaceId: string): AgentRow | undefined {
  const candidates = listAgentsByWorkspace(getOrm(), workspaceId).filter(
    (agent) =>
      !agent.isDeleted && !agent.isDeleting && agent.title === BABYSITTER_TITLE,
  );
  if (candidates.length === 0) {
    return undefined;
  }
  return candidates.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))[0];
}

// A registered, opt-in terminal agent stamped from the *live* registration, or
// null when the registration is gone or has revoked its automated-prompt opt-in.
function driveableTerminalRegistration(
  registrationId: string,
): { kind: "terminal"; registrationId: string } | null {
  const registration = getRegistration(registrationId);
  if (registration === null || !registration.acceptsAutomatedPrompts) {
    return null;
  }
  return { kind: "terminal", registrationId: registration.registrationId };
}

function resolveAgentConfigChoice(): ResolvedBabysitterAgent | null {
  const config = getCurrentUserConfig();
  const choice = config.ci_babysitter.agent as
    | { object_type?: string; registration_id?: string }
    | undefined
    | null;
  const objectType = choice?.object_type;
  if (objectType === "BabysitterAgentClaude") {
    return { kind: "chat", agentType: "claude" };
  }
  if (objectType === "BabysitterAgentPi") {
    // A pinned Pi while Pi is disabled goes Disabled — no silent fallback.
    return config.enable_pi_agent
      ? { kind: "chat", agentType: "pi" }
      : {
          kind: "disabled",
          reason: DISABLED_REASON_PINNED_UNAVAILABLE,
          transient: false,
        };
  }
  if (objectType === "BabysitterAgentRegistered" && choice?.registration_id) {
    const driveable = driveableTerminalRegistration(choice.registration_id);
    return (
      driveable ?? {
        kind: "disabled",
        reason: DISABLED_REASON_PINNED_UNAVAILABLE,
        transient: false,
      }
    );
  }
  return null; // MRU (the default)
}

export function createDefaultBabysitterDriver(): BabysitterDriver {
  return {
    resolve(workspaceId: string): ResolvedBabysitterAgent {
      const pinned = resolveAgentConfigChoice();
      if (pinned !== null) {
        return pinned;
      }
      const config = getCurrentUserConfig();
      const agents = workspaceAgentsMostRecentFirst(workspaceId);
      if (agents.length === 0) {
        return { kind: "chat", agentType: "claude" };
      }
      const mru = agents[0]!;
      const type = configType(mru);
      if (type === "ClaudeCodeSDKAgentConfig") {
        return { kind: "chat", agentType: "claude" };
      }
      if (type === "PiAgentConfig") {
        // MRU is a best-effort inherit: an MRU Pi while Pi is disabled falls
        // back to Claude rather than bricking the babysitter.
        return config.enable_pi_agent
          ? { kind: "chat", agentType: "pi" }
          : { kind: "chat", agentType: "claude" };
      }
      if (type === "RegisteredTerminalAgentConfig") {
        const registrationId = String(mru.agentConfig.registration_id ?? "");
        const driveable = driveableTerminalRegistration(registrationId);
        return (
          driveable ?? {
            kind: "disabled",
            reason: DISABLED_REASON_MRU_NON_DRIVEABLE,
            transient: false,
          }
        );
      }
      // A plain TerminalAgentConfig (bare shell) is never driveable.
      return {
        kind: "disabled",
        reason: DISABLED_REASON_MRU_NON_DRIVEABLE,
        transient: false,
      };
    },

    deliver(
      workspaceId: string,
      _projectId: string,
      resolved: ResolvedBabysitterAgent,
      prompt: string,
    ): void {
      if (resolved.kind === "disabled") {
        return;
      }
      const existing = findBabysitterAgent(workspaceId);
      if (resolved.kind === "chat") {
        if (existing !== undefined) {
          getAgentService().sendMessage(existing.objectId, {
            message: prompt,
            model:
              existing.defaultModel ?? selectModelForWorkspace(workspaceId),
          });
          return;
        }
        const model = selectModelForWorkspace(workspaceId);
        void getAgentService()
          .create(workspaceId, {
            name: BABYSITTER_TITLE,
            prompt,
            model,
            agentType: resolved.agentType,
          })
          .catch((error: unknown) => {
            getLogger().error(
              { error, workspaceId },
              "CI babysitter: failed to create chat babysitter agent",
            );
          });
        return;
      }
      // resolved.kind === "terminal"
      if (existing !== undefined) {
        void driveTerminal(existing.objectId, prompt);
        return;
      }
      void getAgentService()
        .create(workspaceId, {
          name: BABYSITTER_TITLE,
          agentType: "registered",
          registrationId: resolved.registrationId,
        })
        .then((view) => driveTerminal(view.id, prompt))
        .catch((error: unknown) => {
          getLogger().error(
            { error, workspaceId },
            "CI babysitter: failed to create terminal babysitter agent",
          );
        });
    },
  };
}

// Wait for the babysitter's terminal program to reach its prompt, then write the
// fix-CI prompt to its PTY. The PTY only exists once the terminal is opened, so
// poll for both the PTY and an IDLE/WAITING signal up to a never-ready backstop.
async function driveTerminal(agentId: string, prompt: string): Promise<void> {
  const deadline = Date.now() + TERMINAL_READINESS_BACKSTOP_MS;
  while (Date.now() < deadline) {
    const pty = getTerminalManager().getAgentTerminal(agentId);
    if (pty !== undefined) {
      const messages = listAgentMessages(getOrm(), agentId).map(
        (row) => row.message,
      );
      const { runStarted, latestSignal } = scanTerminalSignalState(messages);
      if (
        runStarted &&
        (latestSignal === "IDLE" || latestSignal === "WAITING")
      ) {
        pty.write(`${prompt}\n`);
        return;
      }
    }
    await new Promise((resolve) =>
      setTimeout(resolve, TERMINAL_READINESS_POLL_MS),
    );
  }
  getLogger().info(
    { agentId },
    "CI babysitter: terminal agent never reached its prompt within the backstop",
  );
}
