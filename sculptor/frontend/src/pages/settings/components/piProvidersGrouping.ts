import type { AuthenticatedProviderEntry } from "~/api";
import { ProviderGroup } from "~/api";

export type ProviderGrouping = {
  connected: ReadonlyArray<AuthenticatedProviderEntry>;
  available: ReadonlyArray<AuthenticatedProviderEntry>;
  sessionOnly: ReadonlyArray<AuthenticatedProviderEntry>;
};

const isAuthenticated = (provider: AuthenticatedProviderEntry): boolean => provider.inAuthJson || provider.envDetected;

/**
 * Partition providers into the three Providers sections (Connected / Available /
 * Session-only), ordered alphabetically by display name within each section.
 * Session-only providers always land in their own group regardless of auth state
 * (their persistence is deferred); otherwise an authenticated provider is Connected
 * and an unauthenticated one is Available.
 */
export const groupProviders = (providers: ReadonlyArray<AuthenticatedProviderEntry>): ProviderGrouping => {
  const connected: Array<AuthenticatedProviderEntry> = [];
  const available: Array<AuthenticatedProviderEntry> = [];
  const sessionOnly: Array<AuthenticatedProviderEntry> = [];
  // Sort before partitioning so every section ends up alphabetical.
  const sortedProviders = [...providers].sort((a, b) =>
    a.displayName.localeCompare(b.displayName, undefined, { sensitivity: "base" }),
  );
  for (const provider of sortedProviders) {
    if (provider.group === ProviderGroup.SESSION_ONLY) {
      sessionOnly.push(provider);
    } else if (isAuthenticated(provider)) {
      connected.push(provider);
    } else {
      available.push(provider);
    }
  }
  return { connected, available, sessionOnly };
};
