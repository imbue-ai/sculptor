import { atom } from "jotai";

import type { DependenciesStatus } from "../../../api";

export const dependenciesStatusAtom = atom<DependenciesStatus | null>(null);

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
