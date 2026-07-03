import { useAtomValue } from "jotai";
import { useCallback } from "react";

import { isPiAvailableAtom } from "~/common/state/atoms/dependenciesStatus";
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
 */
export const usePiAgentOption = (): {
  isPiAvailable: boolean;
  openPiSettings: () => void;
} => {
  const isPiAvailable = useAtomValue(isPiAvailableAtom);
  const openSettings = useOpenSettings();
  const openPiSettings = useCallback((): void => openSettings("PI"), [openSettings]);
  return { isPiAvailable, openPiSettings };
};
