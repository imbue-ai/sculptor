import { atom } from "jotai";

import { closeWorkspaceTerminal } from "~/api";
import {
  activeTerminalTabIdAtom,
  terminalNextIndexAtom,
  terminalTabStateAtom,
} from "~/common/state/atoms/terminalTabs.ts";

import { getNextTerminalLabel } from "./terminalLabelUtils.ts";

// ---------------------------------------------------------------------------
// Terminal panels (REQ-TERM-2)
//
// Each terminal instance is its own single-instance panel. The set of terminals
// that exist in a workspace is the source of truth for which terminal panels the
// registry exposes; it lives in `terminalTabStateAtom` (a per-workspace list),
// reused from the old multi-tab terminal so existing sessions/labels survive.
// ---------------------------------------------------------------------------

export type TerminalInstanceInfo = {
  id: string;
  index: number;
  label: string;
};

export const TERMINAL_PANEL_PREFIX = "terminal:";

export const terminalPanelId = (workspaceId: string, index: number): string =>
  `${TERMINAL_PANEL_PREFIX}${workspaceId}:${index}`;

export const isTerminalPanelId = (id: string): boolean => id.startsWith(TERMINAL_PANEL_PREFIX);

/** Parse a terminal panel id back into its workspace id and index. */
export const parseTerminalPanelId = (id: string): { workspaceId: string; index: number } | null => {
  if (!isTerminalPanelId(id)) return null;
  const rest = id.slice(TERMINAL_PANEL_PREFIX.length);
  const sep = rest.lastIndexOf(":");
  if (sep < 0) return null;
  const workspaceId = rest.slice(0, sep);
  const index = Number(rest.slice(sep + 1));
  if (!workspaceId || Number.isNaN(index)) return null;
  return { workspaceId, index };
};

// A fresh workspace conceptually starts with one terminal (index 0) so the
// Bottom section has something to show by default (REQ-DEFAULT-1).
const DEFAULT_TERMINAL: TerminalInstanceInfo = { id: "terminal-0", index: 0, label: "Terminal 1" };

/** The terminals that exist in a workspace (defaults to a single terminal). */
export const getWorkspaceTerminals = (
  allTabs: Record<string, ReadonlyArray<TerminalInstanceInfo>>,
  workspaceId: string,
): ReadonlyArray<TerminalInstanceInfo> => {
  const tabs = allTabs[workspaceId];
  return tabs && tabs.length > 0 ? tabs : [DEFAULT_TERMINAL];
};

/**
 * Create a new terminal in a workspace and return its panel id. The caller is
 * responsible for placing the panel into a section.
 */
export const addTerminalAtom = atom(null, (get, set, workspaceId: string): string => {
  const terminals = getWorkspaceTerminals(get(terminalTabStateAtom), workspaceId);
  const nextIndex = get(terminalNextIndexAtom)[workspaceId] ?? terminals.length;
  const newTerminal: TerminalInstanceInfo = {
    id: `terminal-${nextIndex}`,
    index: nextIndex,
    label: getNextTerminalLabel(terminals),
  };
  set(terminalTabStateAtom, (prev) => ({ ...prev, [workspaceId]: [...terminals, newTerminal] }));
  set(terminalNextIndexAtom, (prev) => ({ ...prev, [workspaceId]: nextIndex + 1 }));
  set(activeTerminalTabIdAtom, (prev) => ({ ...prev, [workspaceId]: newTerminal.id }));
  return terminalPanelId(workspaceId, nextIndex);
});

/**
 * Remove a terminal instance and stop its backend pty. Used when a terminal
 * panel's tab is closed.
 */
export const removeTerminalAtom = atom(null, (get, set, panelId: string): void => {
  const parsed = parseTerminalPanelId(panelId);
  if (!parsed) return;
  const { workspaceId, index } = parsed;
  const terminals = getWorkspaceTerminals(get(terminalTabStateAtom), workspaceId);
  set(terminalTabStateAtom, (prev) => ({
    ...prev,
    [workspaceId]: terminals.filter((t) => t.index !== index),
  }));
  // Fire-and-forget: a 404 (terminal never started / already closed) is harmless.
  void closeWorkspaceTerminal({ path: { workspace_id: workspaceId, index }, throwOnError: false });
});
