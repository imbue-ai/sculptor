import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuthenticatedProviderEntry } from "~/api";
import { ProviderGroup } from "~/api";

import { PiProvidersArea } from "./PiProvidersArea.tsx";
import { groupProviders } from "./piProvidersGrouping.ts";

const { mockUsePiAuthenticatedProviders } = vi.hoisted(() => ({
  mockUsePiAuthenticatedProviders: vi.fn(),
}));

vi.mock("~/common/state/hooks/usePiAuthenticatedProviders", () => ({
  usePiAuthenticatedProviders: mockUsePiAuthenticatedProviders,
}));

// The login dialog embeds an xterm terminal; these tests never open it.
vi.mock("./PiLoginDialog.tsx", () => ({
  PiLoginDialog: (): ReactElement | null => null,
}));

const makeProvider = (overrides: Partial<AuthenticatedProviderEntry>): AuthenticatedProviderEntry => ({
  providerId: "anthropic",
  displayName: "Anthropic",
  group: ProviderGroup.SINGLE_KEY,
  inAuthJson: false,
  envDetected: false,
  envVarNames: ["ANTHROPIC_API_KEY"],
  supportsSubscription: false,
  ...overrides,
});

const renderProvidersArea = (providers: ReadonlyArray<AuthenticatedProviderEntry>): void => {
  mockUsePiAuthenticatedProviders.mockReturnValue({
    providers,
    isPending: false,
    refetch: vi.fn(),
  });
  render(
    <Theme>
      <PiProvidersArea />
    </Theme>,
  );
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PiProvidersArea copy", () => {
  it("describes the connected providers as synced with auth.json", () => {
    renderProvidersArea([makeProvider({ inAuthJson: true })]);
    expect(screen.getByText(/The list of connected providers is synced with/)).toBeTruthy();
    expect(screen.getByText("~/.pi/agent/auth.json")).toBeTruthy();
  });

  it("renders connected rows without a per-row credential-source line", () => {
    renderProvidersArea([
      makeProvider({ providerId: "anthropic", displayName: "Anthropic", inAuthJson: true }),
      makeProvider({
        providerId: "groq",
        displayName: "Groq",
        envDetected: true,
        envVarNames: ["GROQ_API_KEY"],
      }),
    ]);
    expect(screen.queryByText(/Imported from/)).toBeNull();
    expect(screen.queryByText(/Detected via environment variable/)).toBeNull();
    // The env-only row keeps its explainer note — the only place that names the env var.
    expect(screen.getByText(/clear that variable to disconnect/)).toBeTruthy();
  });
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

  it("puts an unauthenticated subscription-only provider under Available", () => {
    const grouping = groupProviders([
      makeProvider({
        providerId: "openai-codex",
        group: ProviderGroup.SUBSCRIPTION_ONLY,
        supportsSubscription: true,
        envVarNames: [],
      }),
    ]);
    expect(grouping.available.map((p) => p.providerId)).toEqual(["openai-codex"]);
    expect(grouping.sessionOnly).toHaveLength(0);
  });

  it("puts an authenticated subscription-only provider under Connected", () => {
    const grouping = groupProviders([
      makeProvider({
        providerId: "github-copilot",
        group: ProviderGroup.SUBSCRIPTION_ONLY,
        supportsSubscription: true,
        envVarNames: [],
        inAuthJson: true,
      }),
    ]);
    expect(grouping.connected.map((p) => p.providerId)).toEqual(["github-copilot"]);
    expect(grouping.sessionOnly).toHaveLength(0);
  });

  it("sorts the Available group alphabetically by display name", () => {
    const grouping = groupProviders([
      makeProvider({ providerId: "openrouter", displayName: "OpenRouter" }),
      makeProvider({ providerId: "anthropic", displayName: "Anthropic" }),
      makeProvider({ providerId: "mistral", displayName: "Mistral" }),
      makeProvider({ providerId: "cerebras", displayName: "Cerebras" }),
    ]);
    expect(grouping.available.map((p) => p.displayName)).toEqual(["Anthropic", "Cerebras", "Mistral", "OpenRouter"]);
  });

  it("sorts the Connected group alphabetically by display name", () => {
    const grouping = groupProviders([
      makeProvider({ providerId: "openai", displayName: "OpenAI", inAuthJson: true }),
      makeProvider({ providerId: "anthropic", displayName: "Anthropic", inAuthJson: true }),
    ]);
    expect(grouping.connected.map((p) => p.displayName)).toEqual(["Anthropic", "OpenAI"]);
  });

  it("sorts case-insensitively so xAI precedes Z.AI", () => {
    const grouping = groupProviders([
      makeProvider({ providerId: "zai", displayName: "Z.AI" }),
      makeProvider({ providerId: "xai", displayName: "xAI" }),
    ]);
    expect(grouping.available.map((p) => p.displayName)).toEqual(["xAI", "Z.AI"]);
  });

  it("sorts the Session-only group alphabetically by display name", () => {
    const grouping = groupProviders([
      makeProvider({
        providerId: "cloudflare-workers-ai",
        displayName: "Cloudflare Workers AI",
        group: ProviderGroup.SESSION_ONLY,
      }),
      makeProvider({ providerId: "amazon-bedrock", displayName: "Amazon Bedrock", group: ProviderGroup.SESSION_ONLY }),
      makeProvider({
        providerId: "azure-openai-responses",
        displayName: "Azure OpenAI",
        group: ProviderGroup.SESSION_ONLY,
      }),
    ]);
    expect(grouping.sessionOnly.map((p) => p.displayName)).toEqual([
      "Amazon Bedrock",
      "Azure OpenAI",
      "Cloudflare Workers AI",
    ]);
  });
});
