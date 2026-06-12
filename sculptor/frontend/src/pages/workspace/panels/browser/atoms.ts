import { atom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { WebviewCommandUiAction } from "~/api";

export type BrowserPanelState = {
  currentUrl: string;
};

export const DEFAULT_BROWSER_PANEL_STATE: BrowserPanelState = {
  currentUrl: "",
};

export const browserPanelStateAtomFamily = atomFamily((workspaceId: string) =>
  atomWithStorage<BrowserPanelState>(`browser-panel-state-${workspaceId}`, DEFAULT_BROWSER_PANEL_STATE),
);

// Per-workspace agent-driven webview state. `command` is the latest
// WebviewCommandUiAction surfaced from the streaming update; `lastAppliedSeq`
// is the highest seq the slot has already dispatched into the <webview>.
// In-memory only (no atomWithStorage) — persisting would replay agent
// commands on next app launch. Combined into one atom (rather than two
// parallel families plus a write-only setter) so the dedupe state lives
// next to the command it dedupes against.
export type AgentWebviewState = {
  command: WebviewCommandUiAction | null;
  lastAppliedSeq: number;
};

const DEFAULT_AGENT_WEBVIEW_STATE: AgentWebviewState = {
  command: null,
  lastAppliedSeq: 0,
};

export const agentWebviewStateAtomFamily = atomFamily((_workspaceId: string) =>
  atom<AgentWebviewState>(DEFAULT_AGENT_WEBVIEW_STATE),
);
