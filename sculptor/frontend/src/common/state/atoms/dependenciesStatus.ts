import { atom } from "jotai";

import type { DependenciesStatus } from "../../../api";
import { getDependenciesStatus } from "../../../api";

/** The dependencies status. Only the unified stream writes it: every snapshot
 * replaces the whole status, so a second writer could put an older one back. */
export const dependenciesStatusAtom = atom<DependenciesStatus | null>(null);

/**
 * Ask the backend to recompute the dependencies status, for changes that send
 * no event of their own (a binary or identity changed outside Sculptor). The
 * backend publishes the result on the unified stream, which updates
 * `dependenciesStatusAtom`. The returned snapshot is for the caller's own
 * decisions, such as when to stop polling; never write it into the atom.
 * Resolves to null when the request fails.
 *
 * skipWsAck: the endpoint opens no data-model transaction, so no stream
 * acknowledgement ever follows.
 */
export const refreshDependenciesStatus = async (): Promise<DependenciesStatus | null> => {
  try {
    const { data } = await getDependenciesStatus({ meta: { skipWsAck: true } });
    return data ?? null;
  } catch {
    return null;
  }
};

/** Whether a usable pi binary is currently resolved: installed and within the
 * pinned range (an agent launch hard-fails outside it). Gates the pi entry in
 * every agent-type picker — when false they offer "Install Pi" instead.
 *
 * Fails open while the status is still unknown (the stream hasn't delivered a
 * snapshot yet): the gate exists to steer users away from a pi we *know* is
 * unusable, not to flash "Install Pi" during startup. */
export const isPiAvailableAtom = atom<boolean>((get) => {
  const status = get(dependenciesStatusAtom);
  if (status === null) return true;
  return Boolean(status.pi.installed && status.pi.isVersionInRange);
});

/** JJ_AVAILABLE: whether Sculptor can use jj, as derived by the backend's readiness
 * check (`jjReadiness`).
 *
 * Fails closed while the status is still unknown: what it gates writes to the
 * user's repository, so it must never assume jj works. */
export const isJjAvailableAtom = atom<boolean>((get) => {
  const status = get(dependenciesStatusAtom);
  if (status === null) return false;
  return status.jjReadiness.blocker === null;
});
