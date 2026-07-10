import { useAtomValue } from "jotai";
import type { ReactElement, ReactNode } from "react";

import { ElementIds } from "~/api";
import type { TerminalConnectionStatus } from "~/common/state/atoms/terminalTabs.ts";
import { terminalConnectionStatusByPanelIdAtom } from "~/common/state/atoms/terminalTabs.ts";
import { BlandCircle, PulsingCircle } from "~/components/PulsingCircle.tsx";

import styles from "./TerminalConnectionIndicator.module.scss";

// A connection-issue indicator for a terminal's panel tab, or null when the
// connection is healthy (or still opening). Reconnecting is transient (amber,
// pulsing); disconnected won't recover on its own (red, static). Kept in its own
// module so it can be rendered in isolation without pulling in the panel's heavier
// dependencies.
const getTabStatusIcon = (status: TerminalConnectionStatus | undefined): ReactNode => {
  if (status === "reconnecting") {
    return (
      <span
        className={styles.statusReconnecting}
        title="Reconnecting…"
        data-testid={ElementIds.TERMINAL_TAB_STATUS_INDICATOR}
        data-status={status}
      >
        <PulsingCircle size={7} />
      </span>
    );
  }

  if (status === "disconnected") {
    return (
      <span
        className={styles.statusDisconnected}
        title="Disconnected"
        data-testid={ElementIds.TERMINAL_TAB_STATUS_INDICATOR}
        data-status={status}
      >
        <BlandCircle size={7} />
      </span>
    );
  }

  return null;
};

// A terminal tab's connection-issue dot, driven by its OWN slice of the terminal
// connection-status map (keyed by panel id). Reading the status here — rather than
// threading it through the panel registry — means a connection transition re-renders
// only this dot, not the tab or the registry. Healthy, unmounted, and never-opened
// terminals read undefined and render nothing. The caller supplies the wrapper class
// (the dot slot lives in each tab's own stylesheet) and controls aria-hidden.
export const TerminalTabConnectionDot = ({
  panelId,
  className,
  ariaHidden,
}: {
  panelId: string;
  className: string;
  ariaHidden?: boolean;
}): ReactElement | null => {
  const status = useAtomValue(terminalConnectionStatusByPanelIdAtom(panelId));
  const indicator = getTabStatusIcon(status);
  if (indicator === null) {
    return null;
  }
  return (
    <div className={className} aria-hidden={ariaHidden}>
      {indicator}
    </div>
  );
};
