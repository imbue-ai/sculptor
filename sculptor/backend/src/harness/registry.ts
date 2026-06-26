// The harness registry — the single point that maps an agent's stored
// `agent_config` to the harness that supervises it (ports
// `agents/harness_registry.py`). The supervisor must never hardcode a
// harness; it asks the registry's resolver. Terminal agents are not
// chat-supervised here (the runner skips them), so they resolve to `undefined`.

import type { AgentRow } from "~/db/schema";
import {
  ClaudeHarness,
  type ClaudeHarnessDeps,
} from "~/harness/claude/harness";
import { HelloHarness } from "~/harness/hello";
import { PiHarness, type PiHarnessDeps } from "~/harness/pi/harness";
import type { Harness, HarnessResolver } from "~/runner/harness";

export type HarnessKind = "claude" | "pi" | "hello" | "terminal" | "unknown";

// Map an agent config's `object_type` discriminator to a harness kind. Mirrors
// `harness_registry.get_harness_for_config`.
export function harnessKindForConfig(
  agentConfig: Record<string, unknown> | undefined,
): HarnessKind {
  switch (agentConfig?.object_type) {
    case "ClaudeCodeSDKAgentConfig":
      return "claude";
    case "PiAgentConfig":
      return "pi";
    case "HelloAgentConfig":
      return "hello";
    case "TerminalAgentConfig":
    case "RegisteredTerminalAgentConfig":
      return "terminal";
    default:
      return "unknown";
  }
}

export interface HarnessRegistryDeps {
  claude: ClaudeHarnessDeps;
  pi: PiHarnessDeps;
}

// Build the `HarnessResolver` the runner uses: the harness singletons are
// constructed once with their deps and selected per-agent by config kind.
// Terminal + unknown configs resolve to `undefined` (not chat-supervised).
export function createHarnessResolver(
  deps: HarnessRegistryDeps,
): HarnessResolver {
  const claude = new ClaudeHarness(deps.claude);
  const pi = new PiHarness(deps.pi);
  const hello = new HelloHarness();
  return (agent: AgentRow): Harness | undefined => {
    switch (harnessKindForConfig(agent.agentConfig)) {
      case "claude":
        return claude;
      case "pi":
        return pi;
      case "hello":
        return hello;
      default:
        return undefined;
    }
  };
}
