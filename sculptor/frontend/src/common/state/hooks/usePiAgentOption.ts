import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useEffect } from "react";

import { getDependenciesStatus } from "~/api";
import { dependenciesStatusAtom, isPiAvailableAtom } from "~/common/state/atoms/dependenciesStatus";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings";

/** Label every agent-type picker shows in place of its pi entry while no usable
 * pi binary is resolved. */
export const INSTALL_PI_LABEL = "Install Pi";

/**
 * Shared behavior of the pi entry in the agent-type pickers (the tab bar's +
 * menu, the new-workspace select, the CI babysitter select). pi is an optional
 * harness: while no usable binary is resolved, a picker cannot select it —
 * its pi entry reads "Install Pi" and choosing it routes to Settings → Pi,
 * where the binary can be installed or configured.
 *
 * Availability can go stale in the picker's favor: pi becomes available
 * mid-session (installed outside Sculptor onto PATH), and the stream only
 * re-pushes dependencies status when something else happens to recompute it.
 * So the hook re-checks with a one-shot GET (the AddRepoDialog pattern) on
 * mount, and exposes `refreshPiAvailability` for pickers whose host outlives
 * the install (the new-workspace select re-checks on every dropdown open; the
 * tab bar's + menu mounts its items per open, so mount alone covers it).
 * skipWsAck: the dependencies endpoint opens no data-model transaction, so no
 * WS acknowledgment ever follows.
 */
export const usePiAgentOption = (): {
  isPiAvailable: boolean;
  openPiSettings: () => void;
  refreshPiAvailability: () => void;
} => {
  const isPiAvailable = useAtomValue(isPiAvailableAtom);
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);
  const openSettings = useOpenSettings();
  const openPiSettings = useCallback((): void => openSettings("PI"), [openSettings]);

  const refreshPiAvailability = useCallback((): void => {
    const refresh = async (): Promise<void> => {
      try {
        const { data } = await getDependenciesStatus({ meta: { skipWsAck: true } });
        if (data) setDependenciesStatus(data);
      } catch {
        // Best-effort; the atom keeps its last (fail-open) value.
      }
    };
    void refresh();
  }, [setDependenciesStatus]);

  useEffect(() => {
    refreshPiAvailability();
  }, [refreshPiAvailability]);

  return { isPiAvailable, openPiSettings, refreshPiAvailability };
};
