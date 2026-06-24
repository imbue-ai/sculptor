// Dynamic (multi-instance) panel derivation for the active workspace: one
// agent:<taskId> panel per task and one terminal:<wsId>:<index> panel per terminal.
// Source data comes from tasksArrayAtom (src/common/state/atoms/tasks.ts) and
// terminalTabStateAtom (src/common/state/atoms/terminalTabs.ts), fed in by the sync
// hook in Task 6.2.
//
// The bound component per dynamic panel id is cached, so rebuilding the registry on
// every task tick returns the SAME component reference per id and a live
// agent/terminal panel never remounts (component_hierarchy.md → SectionBody;
// SWITCH-02). The base components are registered by AgentPanel/TerminalPanel
// (Phase 2/3) and looked up at render time, so a cached bound component picks up its
// base once it registers.

import { Bot, Terminal } from "lucide-react";
import type { ComponentType } from "react";
import { createElement } from "react";

import type { PanelId } from "../sectionTypes.ts";
import type { PanelContextMenuItem, PanelDefinition } from "./panelRegistry.ts";

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

export function makeAgentPanelId(taskId: string): PanelId {
  return `agent:${taskId}`;
}

export function makeTerminalPanelId(workspaceId: string, index: number): PanelId {
  return `terminal:${workspaceId}:${index}`;
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

export type DynamicAgentInput = {
  taskId: string;
  displayName: string;
  contextMenuActions?: ReadonlyArray<PanelContextMenuItem>;
};

export type DynamicTerminalInput = {
  workspaceId: string;
  index: number;
  displayName: string;
  contextMenuActions?: ReadonlyArray<PanelContextMenuItem>;
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
    definitions.push({
      id,
      displayName: agent.displayName,
      icon: Bot,
      kind: "agent",
      defaultSection: "center",
      component: getAgentComponent(agent.taskId),
      contextMenuActions: agent.contextMenuActions,
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
      contextMenuActions: terminal.contextMenuActions,
    });
  }

  // Evict cached components whose task/terminal no longer exists.
  for (const id of [...componentCache.keys()]) {
    if (!liveIds.has(id)) {
      componentCache.delete(id);
    }
  }

  return definitions;
}
