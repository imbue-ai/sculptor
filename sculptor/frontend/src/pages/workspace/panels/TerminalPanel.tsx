import { Flex } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { terminalPanelMountedAtom } from "~/components/panels/atoms.ts";

import styles from "./TerminalPanel.module.scss";
import { useTerminal } from "./useTerminal";

// ---------------------------------------------------------------------------
// TerminalInstance — one xterm.js + WebSocket per terminal index
// ---------------------------------------------------------------------------

type TerminalInstanceProps = {
  workspaceID: string;
  terminalIndex: number;
};

const TerminalInstance = ({ workspaceID, terminalIndex }: TerminalInstanceProps): ReactElement => {
  // Each terminal panel is its own always-visible instance (no shared tab
  // strip), so `isVisible` is constant and there is no `onOutput` consumer.
  const { terminalContainerRef } = useTerminal({
    terminalPath: `/api/v1/workspaces/${workspaceID}/terminal/${terminalIndex}/ws`,
    isVisible: true,
  });

  return (
    <div className={styles.terminalInstanceVisible}>
      <div ref={terminalContainerRef} className={styles.xtermWrapper} />
    </div>
  );
};

// ---------------------------------------------------------------------------
// TerminalPanel — a single terminal rendered as a panel (REQ-TERM-2)
//
// Each terminal is its own single-instance panel; there is no internal tab
// strip. New terminals are created via a section's "+" (New Terminal), and each
// gets its own `terminal:<workspaceId>:<index>` panel.
// ---------------------------------------------------------------------------

type TerminalPanelProps = {
  workspaceID: string;
  terminalIndex: number;
};

export const TerminalPanel = ({ workspaceID, terminalIndex }: TerminalPanelProps): ReactElement => {
  // Reactive signal for "is a terminal panel rendered right now?" — the command
  // palette's `hasTerminalPanel` ctx field reads this so commands like "Clear
  // terminal" hide themselves when no terminal exists.
  const setTerminalPanelMounted = useSetAtom(terminalPanelMountedAtom);
  useEffect(() => {
    setTerminalPanelMounted(true);
    return (): void => {
      setTerminalPanelMounted(false);
    };
  }, [setTerminalPanelMounted]);

  return (
    <Flex direction="column" height="100%" overflow="hidden" className={styles.terminalPanel}>
      <div className={styles.terminalContainer}>
        <TerminalInstance workspaceID={workspaceID} terminalIndex={terminalIndex} />
      </div>
    </Flex>
  );
};
