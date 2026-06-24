// The terminal panel: a thin, shell-agnostic wrapper around the existing xterm I/O,
// parameterized by the (workspaceId, index) the registry binds per
// terminal:<wsId>:<index> panel. It reads no layout, split, or route state
// (component_hierarchy.md → principle 2) so the same component renders identically
// wherever the section model places it, and two instances with different indices
// stream independently (TERM-01). The xterm I/O is reused verbatim via useTerminal —
// this file only owns the container element and its styling.
//
// NOTE: the OLD multi-tab terminal panel still lives in TerminalPanel.tsx; it is
// registered by old-shell code that compiles until Phase 7. Once Phase 7 deletes the
// old shell, that file can be removed and this one renamed to TerminalPanel.tsx.

import type { ReactElement } from "react";

import { registerTerminalPanelComponent } from "~/components/sections/registry/dynamicPanels.tsx";

import styles from "./TerminalPanelView.module.scss";
import { useTerminal } from "./useTerminal.ts";

export const TerminalPanelView = ({ workspaceId, index }: { workspaceId: string; index: number }): ReactElement => {
  // Reuse the existing xterm + WebSocket I/O unchanged. A panel-hosted terminal is
  // always the rendered content of its sub-section, so it is visible whenever mounted.
  const { terminalContainerRef } = useTerminal({
    terminalPath: `/api/v1/workspaces/${workspaceId}/terminal/${index}/ws`,
    isVisible: true,
  });

  return (
    <div className={styles.terminalPanel}>
      <div ref={terminalContainerRef} className={styles.xtermWrapper} />
    </div>
  );
};

// Register at module load as the base the dynamicPanels cache binds per terminal id.
registerTerminalPanelComponent(TerminalPanelView);
