import { describe, expect, it } from "vitest";

import type { AuthenticatedProviderEntry } from "~/api";
import { ProviderGroup } from "~/api";

import { groupProviders } from "./piProvidersGrouping.ts";

const makeProvider = (overrides: Partial<AuthenticatedProviderEntry>): AuthenticatedProviderEntry => ({
  providerId: "anthropic",
  displayName: "Anthropic",
  group: ProviderGroup.SINGLE_KEY,
  inAuthJson: false,
  envDetected: false,
  envVarNames: ["ANTHROPIC_API_KEY"],
  ...overrides,
});

describe("groupProviders", () => {
  it("puts an auth.json provider under Connected", () => {
    const grouping = groupProviders([makeProvider({ providerId: "anthropic", inAuthJson: true })]);
    expect(grouping.connected.map((p) => p.providerId)).toEqual(["anthropic"]);
    expect(grouping.available).toHaveLength(0);
  });

  it("puts an env-detected single-key provider under Connected", () => {
    const grouping = groupProviders([makeProvider({ providerId: "openai", envDetected: true })]);
    expect(grouping.connected.map((p) => p.providerId)).toEqual(["openai"]);
  });

  it("puts an unauthenticated single-key provider under Available", () => {
    const grouping = groupProviders([makeProvider({ providerId: "openrouter" })]);
    expect(grouping.available.map((p) => p.providerId)).toEqual(["openrouter"]);
    expect(grouping.connected).toHaveLength(0);
  });

  it("always puts session-only providers in their own group regardless of auth state", () => {
    const grouping = groupProviders([
      makeProvider({ providerId: "amazon-bedrock", group: ProviderGroup.SESSION_ONLY, envDetected: true }),
    ]);
    expect(grouping.sessionOnly.map((p) => p.providerId)).toEqual(["amazon-bedrock"]);
    expect(grouping.connected).toHaveLength(0);
  });
});
