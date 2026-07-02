// Store-driven add-panel operations and lists, shared by the React add-panel
// surfaces (AddPanelDropdown / EmptySectionState via useAddPanelActions) and the
// Cmd+K "Add panel" command flow (which runs outside React, through the command
// runtime's Jotai store). Keeping the create/list logic here — rather than only in
// the React hook — means the dropdown and Cmd+K can't drift, and the Cmd+K
// provider doesn't need React hooks (which would crash on non-workspace routes).
//
// New agents land in the requesting sub-section (createAgentInLocation) — the section
// "+" dropdown / empty-state / Cmd+K "Add panel" pass their own sub-section, while the
// non-scoped surfaces (the new-agent keybinding and Cmd+K "New agent" command) pass
// center. Terminals and single-instance panels also land in the requesting sub-section.
// Agents/terminals are multi-instance and are never in the single-instance re-add list
// (closing one ends it).

import type { useStore } from "jotai/react";

import { type AgentTypeName, createWorkspaceAgent } from "~/api";
import { encodeRegisteredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { terminalNextIndexAtom, terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { createAgentErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { isPiAgentEnabledAtom, userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { ToastType } from "~/components/Toast.tsx";
import { resetReviewAllScopeAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { getNextTerminalLabel } from "~/pages/workspace/panels/terminalLabelUtils.ts";

import { makeAgentPanelId, makeTerminalPanelId } from "./registry/dynamicPanels.tsx";
import { type PanelDefinition, panelRegistryAtom } from "./registry/panelRegistry.ts";
import { jumpToSectionAtom, openPanelAtom, setActivePanelAtom } from "./sectionActions.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";
import { SECTION_IDS, toSecondary } from "./sectionTypes.ts";

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

// The locations a panel can be added to: EVERY section (including collapsed ones —
// adding a panel there expands the section), plus the secondary half of any section
// that is both expanded and split. A collapsed section only offers its primary; its
// split half isn't shown until the section is expanded.
export function listAvailableLocations(store: AppStore): ReadonlyArray<AddPanelLocation> {
  const layout = store.get(workspaceLayoutAtom);
  const locations: Array<AddPanelLocation> = [];
  for (const section of SECTION_IDS) {
    const isExpanded = section === "center" || (layout.expanded[section] ?? false);
    const isSplit = layout.splits[section] !== undefined;
    const shouldShowSecondary = isExpanded && isSplit;
    locations.push({
      subSection: section,
      label: shouldShowSecondary ? `${SECTION_LABELS[section]} (primary)` : SECTION_LABELS[section],
    });
    if (shouldShowSecondary) {
      locations.push({ subSection: toSecondary(section), label: `${SECTION_LABELS[section]} (secondary)` });
    }
  }
  return locations;
}

// Single-instance static panels not currently open anywhere — the re-add list.
// Sourced from the live registry (not STATIC_PANEL_METADATA) so plugin-contributed
// panels — also kind "static" — are offered too; the multi-instance agent/terminal
// panels are excluded by the kind filter.
export function listAvailableStaticPanels(store: AppStore): ReadonlyArray<AvailableStaticPanel> {
  const layout = store.get(workspaceLayoutAtom);
  const openPanelIds = new Set<PanelId>(Object.keys(layout.placement));
  return store
    .get(panelRegistryAtom)
    .filter((def) => def.kind === "static" && !openPanelIds.has(def.id))
    .map((def) => ({ id: def.id, displayName: def.displayName, icon: def.icon }));
}

export function openStaticPanelInLocation(store: AppStore, panelId: PanelId, subSection: SubSectionId): void {
  // Review All always OPENS on the full branch review ("All" scope). Guarded on
  // the panel not being placed yet, so re-adding/revealing an already-open panel
  // keeps whatever scope the user picked meanwhile.
  if (panelId === "review-all" && store.get(workspaceLayoutAtom).placement[panelId] === undefined) {
    store.set(resetReviewAllScopeAtom);
  }
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

// Create an agent of the given type and place its panel in the requesting sub-section.
// Returns the new task id (or undefined on failure) so callers can navigate to it. The
// placement is just an id reference; the registry sync derives the panel def once the
// task loads. Placing the panel here (before the caller navigates) means the shell's
// active-agent effect sees an existing placement and leaves the agent in this section
// rather than pulling it into center.
export async function createAgentInLocation(
  store: AppStore,
  subSection: SubSectionId,
  inputs: CreateAgentInputs,
): Promise<string | undefined> {
  // A "pi" agent is unusable while the pi harness is disabled (e.g. a remembered
  // last-used type from before the flag was turned off) — fall back to Claude so
  // every create surface degrades the same way.
  const agentType: AgentTypeName =
    inputs.agentType === "pi" && !store.get(isPiAgentEnabledAtom) ? "claude" : inputs.agentType;

  // Optimistically reflect the chosen harness as the most-recently-used type so the
  // surfaces' "New {recent} agent" label updates immediately; the backend persists
  // it on actual create.
  const stored =
    agentType === "registered" && inputs.registrationId !== undefined
      ? encodeRegisteredAgentType(inputs.registrationId)
      : agentType;
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
      body: { model, agentType, registrationId: inputs.registrationId },
    });
    if (!response.data) {
      return undefined;
    }
    const panelId = makeAgentPanelId(response.data.id);
    store.set(openPanelAtom, { panelId, in: subSection });
    store.set(setActivePanelAtom, { panelId, in: subSection });
    store.set(jumpToSectionAtom, { subSection });
    return response.data.id;
  } catch (error) {
    console.error("Failed to create agent:", error);
    return undefined;
  }
}

// Create an agent in the sub-section, then navigate to it; on failure surface the
// shared error toast. The add-panel dropdown / empty-state (via useAddPanelActions)
// and the Cmd+K "New agent" row all funnel through here so their post-create
// behavior (navigation + failure feedback) cannot drift.
export async function createAgentAndNavigate(
  store: AppStore,
  subSection: SubSectionId,
  inputs: CreateAgentInputs,
  navigateToAgent: (workspaceId: string, taskId: string) => void,
): Promise<void> {
  const workspaceId = store.get(activeWorkspaceIdAtom);
  const taskId = await createAgentInLocation(store, subSection, inputs);
  if (taskId !== undefined && workspaceId !== null) {
    navigateToAgent(workspaceId, taskId);
    return;
  }
  store.set(createAgentErrorToastAtom, {
    title: "Failed to create agent",
    description: "The agent could not be created. Try again or check your connection.",
    type: ToastType.ERROR,
    action: null,
  });
}
