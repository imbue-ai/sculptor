// Dynamic (multi-instance) panel derivation for the active workspace: one
// agent:<taskId> panel per task and one terminal:<wsId>:<index> panel per terminal.
// Source data comes from tasksArrayAtom (src/common/state/atoms/tasks.ts) and
// terminalTabStateAtom (src/common/state/atoms/terminalTabs.ts), fed in by the sync
// hook.
//
// The bound component per dynamic panel id is cached, so rebuilding the registry on
// every task tick returns the SAME component reference per id and a live
// agent/terminal panel never remounts (it stays mounted under SectionBody).
// The base components are registered by AgentPanel/TerminalPanel at import time and
// looked up at render time, so a cached bound component picks up its
// base once it registers.

import { Bot, Terminal } from "lucide-react";
import type { ComponentType } from "react";
import { createElement } from "react";

import type { TaskStatus } from "~/api";
import { ElementIds } from "~/api";
import { clearUnreadOverride, getAgentDotStatusWithUnreadOverride } from "~/common/state/atoms/unreadOverrides.ts";
import type { TerminalConnectionStatus } from "~/pages/workspace/panels/useTerminal.ts";

import type { PanelId } from "../sectionTypes.ts";
import type { PanelContextMenuItem, PanelDefinition } from "./panelRegistry.ts";
import { panelDefinitionByIdAtom } from "./panelRegistry.ts";

export type AgentPanelBaseComponent = ComponentType<{ taskId: string }>;
export type TerminalPanelBaseComponent = ComponentType<{ workspaceId: string; index: number }>;

let agentBaseComponent: AgentPanelBaseComponent | null = null;
let terminalBaseComponent: TerminalPanelBaseComponent | null = null;

export function registerAgentPanelComponent(component: AgentPanelBaseComponent): void {
  agentBaseComponent = component;
}

export function registerTerminalPanelComponent(component: TerminalPanelBaseComponent): void {
  terminalBaseComponent = component;
}

// Single source of truth for the dynamic (multi-instance) panel id format. The id
// embeds the agent/terminal identity behind these prefixes; isMultiInstancePanelId
// keys off them so callers never re-derive the prefixes as bare literals.
export const AGENT_PANEL_ID_PREFIX = "agent:";
export const TERMINAL_PANEL_ID_PREFIX = "terminal:";

export function makeAgentPanelId(taskId: string): PanelId {
  return `${AGENT_PANEL_ID_PREFIX}${taskId}`;
}

export function makeTerminalPanelId(workspaceId: string, index: number): PanelId {
  return `${TERMINAL_PANEL_ID_PREFIX}${workspaceId}:${index}`;
}

// True when a panel id is a dynamic agent/terminal panel (multi-instance). Distinct
// from isMultiInstanceKind, which keys off the registry kind rather than the id.
export function isMultiInstancePanelId(panelId: PanelId): boolean {
  return panelId.startsWith(AGENT_PANEL_ID_PREFIX) || panelId.startsWith(TERMINAL_PANEL_ID_PREFIX);
}

const componentCache = new Map<PanelId, ComponentType>();

function getAgentComponent(taskId: string): ComponentType {
  const id = makeAgentPanelId(taskId);
  let cached = componentCache.get(id);
  if (cached === undefined) {
    const BoundAgentPanel: ComponentType = () =>
      agentBaseComponent === null ? null : createElement(agentBaseComponent, { taskId });
    cached = BoundAgentPanel;
    componentCache.set(id, cached);
  }
  return cached;
}

function getTerminalComponent(workspaceId: string, index: number): ComponentType {
  const id = makeTerminalPanelId(workspaceId, index);
  let cached = componentCache.get(id);
  if (cached === undefined) {
    const BoundTerminalPanel: ComponentType = () =>
      terminalBaseComponent === null ? null : createElement(terminalBaseComponent, { workspaceId, index });
    cached = BoundTerminalPanel;
    componentCache.set(id, cached);
  }
  return cached;
}

// Diagnostics for an agent's context menu. Fetched lazily by the
// sync hook when the tab's menu opens; absent/null fields disable the matching copy
// action (e.g. "Copy session id" is disabled until the agent has a session).
export type DynamicAgentDiagnostics = {
  sessionId?: string | null;
  claudeTranscriptPath?: string | null;
  sculptorTranscriptPath?: string | null;
};

export type DynamicAgentInput = {
  taskId: string;
  // The agent's display name. Carries the backend's "Claude N" / "Agent N" title with
  // lowest-available-number reuse after deletions; the sync hook passes
  // agent.title through, so numbering stays in one place (the backend).
  displayName: string;
  // Raw fields for the tab status dot; the dot is derived here via the shared
  // getAgentDotStatusWithUnreadOverride so the panel tab and the workspace
  // sidebar row can't drift.
  status: TaskStatus;
  lastReadAt: string | null;
  updatedAt: string;
  // True for the viewed agent (see viewedAgentIdAtom): its tab dot derives as
  // "read" instead of flashing unread while the debounced mark-read lags. An
  // explicit "Mark as unread" still wins inside the shared helper.
  isViewed?: boolean;
  // Diagnostics powering the context-menu copy actions. Omitted until the
  // sync hook has fetched them.
  diagnostics?: DynamicAgentDiagnostics;
  // Closing an agent tab deletes the agent with confirmation + optimistic rollback.
  // Supplied by the sync hook; when unset, the tab close falls back to
  // closePanelAtom (removes the panel from the layout without deleting the agent).
  onRequestClose?: () => void;
  // Committing an inline tab rename persists the new title on the agent;
  // supplied by the sync hook (renameWorkspaceAgent + optimistic title update).
  onRename?: (newName: string) => void;
  // "Mark as unread" from the tab context menu: records the unread override and
  // persists it (see unreadOverrides.ts). Supplied by the sync hook
  // (markAgentUnreadAtom); allowed on every agent tab, including the one the
  // user is currently viewing — the override suppresses the auto mark-read.
  onMarkUnread?: () => void;
};

async function copyToClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

// Build an agent's tab context-menu actions: "Mark as unread" first, then the flat
// diagnostics copy actions. Copy agent id / name are always available; session id
// and transcript paths are disabled until a session exists.
function buildAgentContextMenuActions(agent: DynamicAgentInput): ReadonlyArray<PanelContextMenuItem> {
  const { sessionId, claudeTranscriptPath, sculptorTranscriptPath } = agent.diagnostics ?? {};
  return [
    { label: "Mark as unread", action: () => agent.onMarkUnread?.(), testId: ElementIds.TAB_CONTEXT_MENU_MARK_UNREAD },
    { label: "Copy agent id", action: () => void copyToClipboard(agent.taskId) },
    { label: "Copy agent name", action: () => void copyToClipboard(agent.displayName) },
    {
      label: "Copy claude session id",
      disabled: !sessionId,
      action: () => void (sessionId && copyToClipboard(sessionId)),
    },
    {
      label: "Copy claude transcript file path",
      disabled: !claudeTranscriptPath,
      action: () => void (claudeTranscriptPath && copyToClipboard(claudeTranscriptPath)),
    },
    {
      label: "Copy Sculptor transcript file path",
      disabled: !sculptorTranscriptPath,
      action: () => void (sculptorTranscriptPath && copyToClipboard(sculptorTranscriptPath)),
    },
  ];
}

export type DynamicTerminalInput = {
  workspaceId: string;
  index: number;
  displayName: string;
  // The terminal's live WebSocket connection state, shown as a dot on its panel tab.
  // Supplied by the sync hook from terminalConnectionStatusesAtom, which holds only
  // unhealthy states (reconnecting/disconnected) for MOUNTED terminals — healthy,
  // backgrounded (unmounted), and never-opened terminals leave it undefined.
  connectionStatus?: TerminalConnectionStatus;
  // Closing a terminal tab kills the backend shell with a confirmation.
  // Supplied by the sync hook; absent for callers that don't wire the close flow.
  onRequestClose?: () => void;
  // Committing an inline tab rename updates this terminal tab's persisted label;
  // supplied by the sync hook.
  onRename?: (newName: string) => void;
};

export function deriveDynamicPanels(
  agents: ReadonlyArray<DynamicAgentInput>,
  terminals: ReadonlyArray<DynamicTerminalInput>,
): ReadonlyArray<PanelDefinition> {
  const liveIds = new Set<PanelId>();
  const definitions: Array<PanelDefinition> = [];

  for (const agent of agents) {
    const id = makeAgentPanelId(agent.taskId);
    liveIds.add(id);
    const dotStatus = getAgentDotStatusWithUnreadOverride(agent.taskId, agent, agent.isViewed ?? false);
    definitions.push({
      id,
      displayName: agent.displayName,
      icon: Bot,
      kind: "agent",
      defaultSection: "center",
      component: getAgentComponent(agent.taskId),
      dotStatus,
      contextMenuActions: buildAgentContextMenuActions(agent),
      onRequestClose: agent.onRequestClose,
      onRename: agent.onRename,
    });
  }

  for (const terminal of terminals) {
    const id = makeTerminalPanelId(terminal.workspaceId, terminal.index);
    liveIds.add(id);
    definitions.push({
      id,
      displayName: terminal.displayName,
      icon: Terminal,
      kind: "terminal",
      defaultSection: "bottom",
      component: getTerminalComponent(terminal.workspaceId, terminal.index),
      connectionStatus: terminal.connectionStatus,
      onRequestClose: terminal.onRequestClose,
      onRename: terminal.onRename,
    });
  }

  // Evict cached components whose task/terminal no longer exists, dropping any
  // unread override for a deleted agent along with its component. The per-id
  // definition slice is evicted too — its family is keyed by panel id, so without
  // this it would grow one entry per agent/terminal forever.
  for (const id of [...componentCache.keys()]) {
    if (!liveIds.has(id)) {
      componentCache.delete(id);
      panelDefinitionByIdAtom.remove(id);
      if (id.startsWith(AGENT_PANEL_ID_PREFIX)) {
        clearUnreadOverride(id.slice(AGENT_PANEL_ID_PREFIX.length));
      }
    }
  }

  return definitions;
}
