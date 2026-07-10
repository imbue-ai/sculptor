import { describe, expect, it } from "vitest";

import type { TerminalAgentRegistration } from "~/api";

import { encodeRegisteredAgentType, resolveEffectiveAgentType } from "./agentTabs.ts";

const registration = (registrationId: string): TerminalAgentRegistration => ({
  registrationId,
  displayName: registrationId,
  launchCommand: "run",
});

describe("resolveEffectiveAgentType", () => {
  it("passes built-in agent types through unchanged", () => {
    expect(resolveEffectiveAgentType("claude", [])).toEqual({ agentType: "claude", registrationId: undefined });
    expect(resolveEffectiveAgentType("pi", [])).toEqual({ agentType: "pi", registrationId: undefined });
    expect(resolveEffectiveAgentType("terminal", [])).toEqual({ agentType: "terminal", registrationId: undefined });
  });

  it("keeps a registered agent whose registration still exists", () => {
    const stored = encodeRegisteredAgentType("reg-1");
    expect(resolveEffectiveAgentType(stored, [registration("reg-1")])).toEqual({
      agentType: "registered",
      registrationId: "reg-1",
    });
  });

  it("falls back to Claude when the registration was deleted", () => {
    // The create path can't launch a deleted registration, so it creates Claude;
    // the form's capability gate reads the same result and shows Claude's controls.
    const stored = encodeRegisteredAgentType("reg-gone");
    expect(resolveEffectiveAgentType(stored, [registration("reg-1")])).toEqual({
      agentType: "claude",
      registrationId: undefined,
    });
  });
});
