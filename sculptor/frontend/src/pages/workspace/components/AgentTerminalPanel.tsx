import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import { useTerminal } from "../panels/useTerminal";
import styles from "./AgentTerminalPanel.module.scss";
import { useTerminalChatActions } from "./useTerminalChatActions.ts";

type AgentTerminalPanelProps = {
  taskId: string;
};

/**
 * Full-pane terminal for a terminal agent — occupies the space the chat
 * interface occupies for chat agents.
 *
 * Only mounted for the active agent tab: hidden-tab persistence comes from
 * the backend-owned PTY (the WebSocket reconnects with the replay buffer),
 * not from keeping xterm mounted. useTerminal's 4404 retry covers the
 * agent-still-BUILDING window before the backend handler registers the PTY.
 */
export const AgentTerminalPanel = ({ taskId }: AgentTerminalPanelProps): ReactElement => {
  useTerminalChatActions(taskId);
  const { terminalContainerRef } = useTerminal({
    terminalPath: `/api/v1/agents/${taskId}/terminal/ws`,
    isVisible: true,
    fontSize: 13,
    lineHeight: 1.1,
    // The terminal is this agent's only input surface and the pane remounts
    // on every tab switch, so it must take keyboard focus immediately (SCU-1578).
    focusOnVisible: true,
  });

  return (
    <div className={styles.agentTerminalPanel} data-testid={ElementIds.AGENT_TERMINAL_PANEL}>
      <div ref={terminalContainerRef} className={styles.xtermWrapper} />
    </div>
  );
};
