import { describe, expect, it } from "vitest";

import type { AgentRow } from "~/db/schema";
import {
  ClaudeHarness,
  type ClaudeHarnessEnvironment,
} from "~/harness/claude/harness";
import { HelloHarness } from "~/harness/hello";
import { PiHarness, type PiHarnessEnvironment } from "~/harness/pi/harness";
import {
  createHarnessResolver,
  harnessKindForConfig,
} from "~/harness/registry";

describe("harnessKindForConfig", () => {
  it("maps each config object_type to a harness kind", () => {
    expect(
      harnessKindForConfig({ object_type: "ClaudeCodeSDKAgentConfig" }),
    ).toBe("claude");
    expect(harnessKindForConfig({ object_type: "PiAgentConfig" })).toBe("pi");
    expect(harnessKindForConfig({ object_type: "HelloAgentConfig" })).toBe(
      "hello",
    );
    expect(harnessKindForConfig({ object_type: "TerminalAgentConfig" })).toBe(
      "terminal",
    );
    expect(
      harnessKindForConfig({ object_type: "RegisteredTerminalAgentConfig" }),
    ).toBe("terminal");
    expect(harnessKindForConfig({ object_type: "Nonsense" })).toBe("unknown");
    expect(harnessKindForConfig(undefined)).toBe("unknown");
  });
});

describe("createHarnessResolver", () => {
  const resolver = createHarnessResolver({
    claude: {
      resolveBinaryPath: () => "/bin/claude",
      environmentFor: () => ({}) as ClaudeHarnessEnvironment,
      initializationStrategyFor: () => "WORKTREE",
    },
    pi: {
      resolveBinaryPath: () => "/bin/pi",
      environmentFor: () => ({}) as PiHarnessEnvironment,
      initializationStrategyFor: () => "WORKTREE",
    },
  });

  const agentWith = (objectType: string): AgentRow =>
    ({ agentConfig: { object_type: objectType } }) as unknown as AgentRow;

  it("selects the right harness per config and skips terminal/unknown", () => {
    expect(resolver(agentWith("ClaudeCodeSDKAgentConfig"))).toBeInstanceOf(
      ClaudeHarness,
    );
    expect(resolver(agentWith("PiAgentConfig"))).toBeInstanceOf(PiHarness);
    expect(resolver(agentWith("HelloAgentConfig"))).toBeInstanceOf(
      HelloHarness,
    );
    expect(resolver(agentWith("TerminalAgentConfig"))).toBeUndefined();
    expect(resolver(agentWith("Nonsense"))).toBeUndefined();
  });
});
