import type { ReactNode } from "react";

import { ElementIds } from "~/api";
import { BlandCircle, PulsingCircle } from "~/components/PulsingCircle.tsx";

import styles from "./TerminalConnectionIndicator.module.scss";
import type { TerminalConnectionStatus } from "./useTerminal";

// A connection-issue indicator for a terminal tab, or null when the connection
// is healthy (or still opening). Reconnecting is transient (amber, pulsing);
// disconnected won't recover on its own (red, static). Kept in its own module
// (not in TerminalPanel) so it can be rendered in isolation — e.g. Storybook —
// without pulling in the panel's heavier dependencies.
export const getTabStatusIcon = (status: TerminalConnectionStatus | undefined): ReactNode => {
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
