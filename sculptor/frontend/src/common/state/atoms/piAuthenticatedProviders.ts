import { atom } from "jotai";
import { loadable } from "jotai/utils";

import type { AuthenticatedProviderEntry } from "~/api";
import { getPiAuthenticatedProviders } from "~/api";

/**
 * Bump this counter to refetch the authenticated-providers list. The
 * credential-change flows (interactive login/logout, paste-key) increment it so
 * the Settings Providers area reflects the new auth.json without a restart.
 */
export const refreshPiProvidersAtom = atom(0);

const piAuthenticatedProvidersAsyncAtom = atom(async (get): Promise<ReadonlyArray<AuthenticatedProviderEntry>> => {
  get(refreshPiProvidersAtom);
  const response = await getPiAuthenticatedProviders({ meta: { skipWsAck: true } });
  return (response.data?.providers ?? []) as ReadonlyArray<AuthenticatedProviderEntry>;
});

/**
 * Loadable view of the global pi authenticated-providers read. Exposes
 * loading/error/data without a Suspense boundary; refetches when
 * {@link refreshPiProvidersAtom} changes.
 */
export const piAuthenticatedProvidersAtom = loadable(piAuthenticatedProvidersAsyncAtom);
