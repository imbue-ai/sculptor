// The terminal panel: a thin, shell-agnostic wrapper around the existing xterm I/O,
// parameterized by the (workspaceId, index) the registry binds per
// terminal:<wsId>:<index> panel. It reads no layout, split, or route state, so the same
// component renders identically wherever the section model places it, and two instances
// with different indices stream independently. The xterm I/O is reused verbatim via
// useTerminal — this file only owns the container element and its styling.

import { useSetAtom } from "jotai";
import { type ReactElement, useEffect } from "react";

import { registerTerminalPanelComponent } from "~/components/sections/registry/dynamicPanels.tsx";
import { terminalPanelMountedAtom } from "~/pages/workspace/atoms.ts";

import styles from "./TerminalPanelView.module.scss";
import { useTerminal } from "./useTerminal.ts";

export const TerminalPanelView = ({ workspaceId, index }: { workspaceId: string; index: number }): ReactElement => {
  // Reuse the existing xterm + WebSocket I/O unchanged. A panel-hosted terminal is
  // always the rendered content of its sub-section, so it is visible whenever mounted.
  const { terminalContainerRef } = useTerminal({
    terminalPath: `/api/v1/workspaces/${workspaceId}/terminal/${index}/ws`,
    isVisible: true,
  });

  // Reactive signal for the command palette: maintain a shared mount counter so
  // terminal-scoped commands (e.g. "Clear terminal") gate on whether a terminal is open.
  const setTerminalPanelMounted = useSetAtom(terminalPanelMountedAtom);
  useEffect(() => {
    setTerminalPanelMounted((count) => count + 1);
    return (): void => {
      setTerminalPanelMounted((count) => count - 1);
    };
  }, [setTerminalPanelMounted]);

  return (
    <div className={styles.terminalPanel}>
      <div ref={terminalContainerRef} className={styles.xtermWrapper} />
    </div>
  );
};

// Register at module load as the base the dynamicPanels cache binds per terminal id.
registerTerminalPanelComponent(TerminalPanelView);
