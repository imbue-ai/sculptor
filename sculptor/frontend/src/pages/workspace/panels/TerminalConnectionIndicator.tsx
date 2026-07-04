import type { ReactNode } from "react";

import { ElementIds } from "~/api";
import { BlandCircle, PulsingCircle } from "~/components/PulsingCircle.tsx";

import styles from "./TerminalConnectionIndicator.module.scss";
import type { TerminalConnectionStatus } from "./useTerminal";

// A connection-issue indicator for a terminal's panel tab, or null when the
// connection is healthy (or still opening). Reconnecting is transient (amber,
// pulsing); disconnected won't recover on its own (red, static). Rendered in the
// tab's dot slot by SectionHeader's PanelTab (and mirrored by TabPill's drag
// copies) from the definition's connectionStatus; kept in its own module so it
// can be rendered in isolation without pulling in the panel's heavier
// dependencies.
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
