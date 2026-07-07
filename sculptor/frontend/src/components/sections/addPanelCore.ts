// Store-driven add-panel operations and the derived read atoms behind the
// add-panel surfaces: the section `+` dropdown / empty-state quick actions
// (AddPanelDropdown / EmptySectionState via useAddPanelActions) and the Cmd+K
// "Add panel" command flow (which runs outside React, through the command
// runtime's Jotai store). Keeping the create logic here — rather than only in
// the React hook — means the dropdown and Cmd+K can't drift, and the Cmd+K
// provider doesn't need React hooks (which would crash on non-workspace routes).
// The pure location/panel LIST queries the derived atoms wrap live in layoutQueries.
//
// New agents land in the requesting sub-section (createAgentInLocation) — the section
// "+" dropdown / empty-state / Cmd+K "Add panel" pass their own sub-section, while the
// non-scoped surfaces (the new-agent keybinding and Cmd+K "New agent" command) pass
// center. Terminals and single-instance panels also land in the requesting sub-section.
// Agents/terminals are multi-instance and are never in the single-instance re-add list
// (closing one ends it).

import type { Atom } from "jotai";
import { atom } from "jotai";
import type { useStore } from "jotai/react";
import { selectAtom } from "jotai/utils";

import { type AgentTypeName, createWorkspaceAgent, type TerminalAgentRegistration } from "~/api";
import {
  AGENT_TYPE_LABELS,
  encodeRegisteredAgentType,
  lastUsedAgentTypeAtom,
  parseStoredAgentType,
  REGISTERED_AGENT_TYPE_PREFIX,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { isPiAvailableAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { terminalNextIndexAtom, terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { createAgentErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { ToastType } from "~/components/Toast.tsx";
import { resetReviewAllScopeAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { getNextTerminalLabel } from "~/pages/workspace/panels/terminalLabelUtils.ts";

import type { AddPanelLocation, AvailableStaticPanel } from "./layoutQueries.ts";
import { listAvailableLocations, listAvailableStaticPanels } from "./layoutQueries.ts";
import { makeAgentPanelId, makeTerminalPanelId } from "./registry/dynamicPanels.tsx";
import { panelRegistryAtom } from "./registry/panelRegistry.ts";
import { jumpToSectionAtom, openPanelAtom, setActivePanelAtom } from "./sectionActions.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import type { PanelId, SubSectionId } from "./sectionTypes.ts";

type AppStore = ReturnType<typeof useStore>;

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

// Append a fresh tab to the workspace's persisted terminal state. The index comes from
// terminalNextIndexAtom (monotonic) and the label reuses the lowest free number via
// getNextTerminalLabel, so the numbering matches what useWorkspaceDynamicPanels renders.
// Returns the new tab's index (which keys the terminal's panel id); placement is the
// caller's concern.
function appendTerminalTab(store: AppStore, workspaceId: string): number {
  const index = store.get(terminalNextIndexAtom)[workspaceId] ?? 1;
  const existingTabs = store.get(terminalTabStateAtom)[workspaceId] ?? [];
  const newTab = { id: `terminal-${index}`, index, label: getNextTerminalLabel(existingTabs) };
  store.set(terminalTabStateAtom, (prev) => ({ ...prev, [workspaceId]: [...(prev[workspaceId] ?? []), newTab] }));
  store.set(terminalNextIndexAtom, (prev) => ({ ...prev, [workspaceId]: index + 1 }));
  return index;
}

// Append a fresh terminal tab, then place the terminal panel in the sub-section.
export function createTerminalInLocation(store: AppStore, subSection: SubSectionId): void {
  const workspaceId = store.get(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return;
  }
  const index = appendTerminalTab(store, workspaceId);

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
  const firstExisting = (store.get(terminalTabStateAtom)[workspaceId] ?? [])[0];
  if (firstExisting !== undefined) {
    return firstExisting.index;
  }
  return appendTerminalTab(store, workspaceId);
}

// Resolve a stored/requested agent type into the effective one. Claude, pi, and
// registered terminal-agent types all pass through unchanged, as does a bare
// "terminal": the new-workspace form legitimately stores it, and surfaces that
// cannot use it layer their own fallback on top (see normalizeRecentAgentType).
// Kept as the single choke point every surface resolves through so their handling
// of stored types cannot drift.
export function resolveStoredAgentType<T extends StoredAgentType>(stored: T): T {
  return stored;
}

// The stored last-used agent type, normalized for the pinned "New {recent} agent"
// row shared by the section "+" dropdown, the empty-section quick actions, the
// new-agent keybinding/command, and the Cmd+K "Add panel" flow. A stored bare
// "terminal" cannot back an agent row and falls back to Claude — the add-panel
// model has no bare terminal AGENT; the dedicated "New terminal" row owns terminal
// creation.
export function normalizeRecentAgentType(stored: StoredAgentType): StoredAgentType {
  if (stored === "terminal") {
    return "claude";
  }
  return resolveStoredAgentType(stored);
}

// Display label for the pinned "New {recent} agent" row, shared by the section "+"
// dropdown and the Cmd+K "Add panel" flow so the two surfaces label the row
// identically: built-in labels for Claude/pi/terminal, the registration's display
// name for a registered terminal agent, and the generic "agent" when the
// registration is unknown (removed since it was stored, or the caller has no
// registrations list — the Cmd+K provider runs outside React and passes none).
export function recentAgentLabel(
  stored: StoredAgentType,
  registrations: ReadonlyArray<TerminalAgentRegistration>,
): string {
  if (stored.startsWith(REGISTERED_AGENT_TYPE_PREFIX)) {
    const { registrationId } = parseStoredAgentType(stored);
    return registrations.find((registration) => registration.registrationId === registrationId)?.displayName ?? "agent";
  }
  return AGENT_TYPE_LABELS[stored as Exclude<AgentTypeName, "registered">];
}

// ── Derived read atoms for the add-panel surfaces ─────────────────────────────
//
// The menu surfaces subscribe to these atoms only while their content is MOUNTED
// (Radix mounts dropdown content on open), and the Cmd+K provider reads them
// imperatively per produce — so the always-mounted shell (section headers,
// shortcuts, bootstrap) carries no layout/registry subscription for the add-panel
// feature. Each atom carries an equality guard so an OPEN menu does not re-render
// when an unrelated layout write (split-ratio drag) or a registry rebuild (task
// tick) recomputes an identical list.

// The stored recent agent type, normalized (a bare "terminal" falls back to
// Claude — see normalizeRecentAgentType). A string, so Jotai's Object.is guard
// already dedupes recomputes that land on the same value.
//
// pi can be the recorded MRU while no usable pi binary is resolved; the pinned
// "New {recent} agent" row (and its Cmd+K / empty-state / keybinding twins, which
// all read this atom) then falls back to Claude rather than backing it with a pi
// agent that cannot launch. The agent-type sub-menu still lists pi, as "Install
// Pi" — see AddPanelDropdown.
export const recentAgentTypeAtom: Atom<StoredAgentType> = atom((get) => {
  const recent = normalizeRecentAgentType(get(lastUsedAgentTypeAtom));
  return recent === "pi" && !get(isPiAvailableAtom) ? "claude" : recent;
});

function availableStaticPanelListsEqual(
  a: ReadonlyArray<AvailableStaticPanel>,
  b: ReadonlyArray<AvailableStaticPanel>,
): boolean {
  return (
    a.length === b.length &&
    a.every(
      (panel, index) =>
        panel.id === b[index].id &&
        panel.displayName === b[index].displayName &&
        panel.icon === b[index].icon &&
        panel.description === b[index].description,
    )
  );
}

// listAvailableStaticPanels over two sources; the selectAtom wrapper is what holds
// the equality guard (a plain derived atom would emit a fresh array per recompute).
const unguardedAvailableStaticPanelsAtom = atom((get) =>
  listAvailableStaticPanels(get(panelRegistryAtom), get(workspaceLayoutAtom).placement),
);

// Single-instance static panels not currently open anywhere — the re-add list
// offered by the section "+" dropdown, the empty-state quick actions, and the
// Cmd+K "Add panel" page.
export const availableStaticPanelsAtom: Atom<ReadonlyArray<AvailableStaticPanel>> = selectAtom(
  unguardedAvailableStaticPanelsAtom,
  (panels) => panels,
  availableStaticPanelListsEqual,
);

function locationListsEqual(a: ReadonlyArray<AddPanelLocation>, b: ReadonlyArray<AddPanelLocation>): boolean {
  return (
    a.length === b.length &&
    a.every((location, index) => location.subSection === b[index].subSection && location.label === b[index].label)
  );
}

// The labeled locations a panel can be added to (the Cmd+K "Add panel" location
// page; the section "+" dropdown is already scoped to its own sub-section).
export const availableLocationsAtom: Atom<ReadonlyArray<AddPanelLocation>> = selectAtom(
  workspaceLayoutAtom,
  listAvailableLocations,
  locationListsEqual,
);

export type AgentTypeOption = {
  key: string;
  stored: StoredAgentType;
  agentType: AgentTypeName;
  registrationId: string | undefined;
  label: string;
};

// The agent-type sub-menu options: Claude, pi, and each registered terminal-agent
// program. No bare "Terminal" agent type — terminal creation belongs to the
// dedicated "New terminal" row.
export function buildAgentTypeOptions(inputs: {
  registrations: ReadonlyArray<TerminalAgentRegistration>;
}): ReadonlyArray<AgentTypeOption> {
  const options: Array<AgentTypeOption> = [
    {
      key: "claude",
      stored: "claude",
      agentType: "claude",
      registrationId: undefined,
      label: AGENT_TYPE_LABELS.claude,
    },
    {
      key: "pi",
      stored: "pi",
      agentType: "pi",
      registrationId: undefined,
      label: AGENT_TYPE_LABELS.pi,
    },
  ];

  for (const registration of inputs.registrations) {
    options.push({
      key: `registered:${registration.registrationId}`,
      stored: encodeRegisteredAgentType(registration.registrationId),
      agentType: "registered",
      registrationId: registration.registrationId,
      label: registration.displayName,
    });
  }
  return options;
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
  const agentType: AgentTypeName = resolveStoredAgentType(inputs.agentType);

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
