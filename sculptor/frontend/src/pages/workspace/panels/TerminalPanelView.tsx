// The terminal panel: a thin, shell-agnostic wrapper around the existing xterm I/O,
// parameterized by the (workspaceId, index) the registry binds per
// terminal:<wsId>:<index> panel. It reads no layout, split, or route state, so the same
// component renders identically wherever the section model places it, and two instances
// with different indices stream independently. The xterm I/O is reused verbatim via
// useTerminal — this file only owns the container element and its styling.

import { useSetAtom } from "jotai";
import { type ReactElement, useCallback, useEffect } from "react";

import { reportTerminalConnectionStatusAtom } from "~/common/state/atoms/terminalTabs.ts";
import { terminalPanelMountedAtom } from "~/pages/workspace/atoms.ts";
import { makeTerminalPanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";

import styles from "./TerminalPanelView.module.scss";
import type { TerminalConnectionStatus } from "./useTerminal.ts";
import { useTerminal } from "./useTerminal.ts";

export const TerminalPanelView = ({ workspaceId, index }: { workspaceId: string; index: number }): ReactElement => {
  // Publish this terminal's WebSocket connection state keyed by its panel id, so the
  // panel tab (SectionHeader) can show a reconnecting/disconnected dot for it.
  const panelId = makeTerminalPanelId(workspaceId, index);
  const reportConnectionStatus = useSetAtom(reportTerminalConnectionStatusAtom);
  const handleConnectionStatusChange = useCallback(
    (status: TerminalConnectionStatus): void => reportConnectionStatus({ panelId, status }),
    [panelId, reportConnectionStatus],
  );

  // Reuse the existing xterm + WebSocket I/O unchanged. A panel-hosted terminal is
  // always the rendered content of its sub-section, so it is visible whenever mounted.
  const { terminalContainerRef } = useTerminal({
    terminalPath: `/api/v1/workspaces/${workspaceId}/terminal/${index}/ws`,
    isVisible: true,
    onConnectionStatusChange: handleConnectionStatusChange,
  });

  // Forget this terminal's connection status on unmount. useTerminal deliberately
  // suppresses its final callback during teardown, and SectionBody unmounts every
  // non-active panel — without this cleanup, backgrounding a terminal mid-reconnect
  // would leave a stale "reconnecting" dot stuck on its tab.
  useEffect(() => {
    return (): void => {
      reportConnectionStatus({ panelId, status: null });
    };
  }, [panelId, reportConnectionStatus]);

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
