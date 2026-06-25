// Store-driven add-panel operations and lists, shared by the React add-panel
// surfaces (AddPanelDropdown / EmptySectionState via useAddPanelActions) and the
// Cmd+K "Add panel" command flow (which runs outside React, through the command
// runtime's Jotai store). Keeping the create/list logic here — rather than only in
// the React hook — means the dropdown and Cmd+K can't drift, and the Cmd+K
// provider doesn't need React hooks (which would crash on non-workspace routes).
//
// New agents ALWAYS land in the center section, regardless of the
// requesting sub-section. Terminals and single-instance panels land in the
// requesting sub-section. Agents/terminals are multi-instance and are never in the
// single-instance re-add list (closing one ends it).

import type { useStore } from "jotai/react";

import { type AgentTypeName, createWorkspaceAgent } from "~/api";
import { encodeRegisteredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { terminalNextIndexAtom, terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { getNextTerminalLabel } from "~/pages/workspace/panels/terminalLabelUtils.ts";

import { makeAgentPanelId, makeTerminalPanelId } from "./registry/dynamicPanels.tsx";
import { type PanelDefinition, STATIC_PANEL_METADATA } from "./registry/panelRegistry.ts";
import { jumpToSectionAtom, openPanelAtom, setActivePanelAtom } from "./sectionActions.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";
import { SECTION_IDS, toSecondary } from "./sectionTypes.ts";

// New agents always land in the center section's primary sub-section.
const AGENT_TARGET_SUB_SECTION: SubSectionId = "center";

type AppStore = ReturnType<typeof useStore>;

export type AddPanelLocation = { subSection: SubSectionId; label: string };

export type AvailableStaticPanel = {
  id: PanelId;
  displayName: string;
  icon: PanelDefinition["icon"];
};

const SECTION_LABELS: Readonly<Record<SectionId, string>> = {
  left: "Left",
  center: "Center",
  right: "Right",
  bottom: "Bottom",
};

// The locations a panel can be added to: every currently-expanded section, plus the
// secondary half of any split section (the center section is always expanded).
export function listAvailableLocations(store: AppStore): ReadonlyArray<AddPanelLocation> {
  const layout = store.get(workspaceLayoutAtom);
  const locations: Array<AddPanelLocation> = [];
  for (const section of SECTION_IDS) {
    const isExpanded = section === "center" || (layout.expanded[section] ?? false);
    if (!isExpanded) {
      continue;
    }
    const isSplit = layout.splits[section] !== undefined;
    locations.push({
      subSection: section,
      label: isSplit ? `${SECTION_LABELS[section]} (primary)` : SECTION_LABELS[section],
    });
    if (isSplit) {
      locations.push({ subSection: toSecondary(section), label: `${SECTION_LABELS[section]} (secondary)` });
    }
  }
  return locations;
}

// Single-instance static panels not currently open anywhere — the re-add list.
// Dynamic agent/terminal ids never appear in STATIC_PANEL_METADATA, so they are
// inherently excluded.
export function listAvailableStaticPanels(store: AppStore): ReadonlyArray<AvailableStaticPanel> {
  const layout = store.get(workspaceLayoutAtom);
  const openPanelIds = new Set<PanelId>(Object.keys(layout.placement));
  return STATIC_PANEL_METADATA.filter((meta) => !openPanelIds.has(meta.id)).map((meta) => ({
    id: meta.id,
    displayName: meta.displayName,
    icon: meta.icon,
  }));
}

export function openStaticPanelInLocation(store: AppStore, panelId: PanelId, subSection: SubSectionId): void {
  store.set(openPanelAtom, { panelId, in: subSection });
  // Adding a panel is a deliberate interaction: make its section active and pulse the
  // ring. openPanel has already expanded the section, so the jump applies.
  store.set(jumpToSectionAtom, { subSection });
}

// Append a fresh tab to the workspace's persisted terminal state (the same state
// TerminalPanel reads), mirroring TerminalPanel's handleAddTerminal so index/label
// numbering stays consistent, then place the terminal panel in the sub-section.
export function createTerminalInLocation(store: AppStore, subSection: SubSectionId): void {
  const workspaceId = store.get(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return;
  }
  const nextIndexByWorkspace = store.get(terminalNextIndexAtom);
  const index = nextIndexByWorkspace[workspaceId] ?? 1;
  const existingTabs = store.get(terminalTabStateAtom)[workspaceId] ?? [];
  const newTab = { id: `terminal-${index}`, index, label: getNextTerminalLabel(existingTabs) };
  store.set(terminalTabStateAtom, (prev) => ({ ...prev, [workspaceId]: [...(prev[workspaceId] ?? []), newTab] }));
  store.set(terminalNextIndexAtom, (prev) => ({ ...prev, [workspaceId]: index + 1 }));

  const panelId = makeTerminalPanelId(workspaceId, index);
  store.set(openPanelAtom, { panelId, in: subSection });
  store.set(setActivePanelAtom, { panelId, in: subSection });
  store.set(jumpToSectionAtom, { subSection });
}

// Seed the workspace's first-visit terminal for the default bottom section.
// Reuses the first existing terminal tab if one is already persisted (so a no-migration
// revisit of a workspace that already had terminals does not spawn a duplicate),
// otherwise appends one fresh tab with the same index/label scheme as
// createTerminalInLocation. Returns the terminal's index so the default layout can
// reference its panel id. Unlike createTerminalInLocation it does NOT place/activate the
// panel — buildDefaultWorkspaceLayout owns the bottom placement.
export function seedFirstVisitTerminal(store: AppStore, workspaceId: string): number {
  const existingTabs = store.get(terminalTabStateAtom)[workspaceId] ?? [];
  const firstExisting = existingTabs[0];
  if (firstExisting !== undefined) {
    return firstExisting.index;
  }
  const index = store.get(terminalNextIndexAtom)[workspaceId] ?? 1;
  const newTab = { id: `terminal-${index}`, index, label: getNextTerminalLabel(existingTabs) };
  store.set(terminalTabStateAtom, (prev) => ({ ...prev, [workspaceId]: [...(prev[workspaceId] ?? []), newTab] }));
  store.set(terminalNextIndexAtom, (prev) => ({ ...prev, [workspaceId]: index + 1 }));
  return index;
}

type CreateAgentInputs = { agentType: AgentTypeName; registrationId?: string; activeAgentId?: string };

// Create an agent of the given type and place its panel in the CENTER section
// regardless of the requesting sub-section. Returns the new task id (or
// undefined on failure) so callers can navigate to it. The placement is just an id
// reference; the registry sync derives the panel def once the task loads.
export async function createAgentInCenter(store: AppStore, inputs: CreateAgentInputs): Promise<string | undefined> {
  // Optimistically reflect the chosen harness as the most-recently-used type so the
  // surfaces' "New {recent} agent" label updates immediately; the backend persists
  // it on actual create.
  const stored =
    inputs.agentType === "registered" && inputs.registrationId !== undefined
      ? encodeRegisteredAgentType(inputs.registrationId)
      : inputs.agentType;
  store.set(userConfigAtom, (prev) => (prev ? { ...prev, lastUsedAgentType: stored } : prev));

  // Inherit the model from the currently viewed agent so the new agent starts with
  // the same model selection. Terminal agents never read it.
  const tasks = store.get(tasksArrayAtom);
  const currentAgent = inputs.activeAgentId ? tasks?.find((task) => task.id === inputs.activeAgentId) : undefined;
  const model = currentAgent?.model;

  const workspaceId = store.get(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return undefined;
  }

  try {
    const response = await createWorkspaceAgent({
      path: { workspace_id: workspaceId },
      body: { model, agentType: inputs.agentType, registrationId: inputs.registrationId },
    });
    if (!response.data) {
      return undefined;
    }
    const panelId = makeAgentPanelId(response.data.id);
    store.set(openPanelAtom, { panelId, in: AGENT_TARGET_SUB_SECTION });
    store.set(setActivePanelAtom, { panelId, in: AGENT_TARGET_SUB_SECTION });
    store.set(jumpToSectionAtom, { subSection: AGENT_TARGET_SUB_SECTION });
    return response.data.id;
  } catch (error) {
    console.error("Failed to create agent:", error);
    return undefined;
  }
}
