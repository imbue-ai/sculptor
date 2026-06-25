// React hook for the add-panel surfaces: the section `+` dropdown
// (AddPanelDropdown) and the empty-state quick actions (EmptySectionState). Wraps
// the store-driven operations in addPanelCore with React niceties (navigation
// after create, the live registrations list, pi gating, the recent-agent label).
//
// The actual create/list logic lives in addPanelCore so the Cmd+K "Add panel" flow
// (which runs outside React) shares one implementation and can't drift. New agents
// always land in center; terminals and single-instance panels land in
// the requesting sub-section; agents/terminals are never in the re-add list.

import { useAtomValue } from "jotai";
import { useStore } from "jotai/react";
import { useCallback, useMemo } from "react";

import type { AgentTypeName, TerminalAgentRegistration } from "~/api";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import {
  AGENT_TYPE_LABELS,
  encodeRegisteredAgentType,
  lastUsedAgentTypeAtom,
  parseStoredAgentType,
  REGISTERED_AGENT_TYPE_PREFIX,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { createAgentErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { isPiAgentEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import { ToastType } from "~/components/Toast.tsx";

import {
  type AvailableStaticPanel,
  createAgentInCenter,
  createTerminalInLocation,
  openStaticPanelInLocation,
} from "./addPanelCore.ts";
import { STATIC_PANEL_METADATA } from "./registry/panelRegistry.ts";
import { workspaceLayoutAtom } from "./sectionAtoms.ts";
import type { PanelId, SubSectionId } from "./sectionTypes.ts";

export type StaticPanelOption = AvailableStaticPanel;

export type AgentTypeOption = {
  key: string;
  stored: StoredAgentType;
  agentType: AgentTypeName;
  registrationId: string | undefined;
  label: string;
};

export type AddPanelActions = {
  // The recently-used agent type's display label (e.g. "Claude"), used for the
  // pinned "New {recent} agent" row.
  recentAgentLabel: string;
  // The agent types offered in the "different agent type" sub-menu: Claude, pi
  // (only when enabled), and each registered terminal-agent program. There is no
  // bare "Terminal" agent type.
  agentTypeOptions: ReadonlyArray<AgentTypeOption>;
  // Re-read the registrations directory (call when the menu opens).
  refreshRegistrations: () => void;
  // Single-instance static panels not currently open anywhere — the re-add list.
  availableStaticPanels: ReadonlyArray<StaticPanelOption>;
  // Create an agent of the recently-used type (Claude by default) in center.
  createRecentAgent: () => void;
  // Create an agent of a specific type in center.
  createAgent: (agentType: AgentTypeName, registrationId?: string) => void;
  // Create a terminal and place it in the requesting sub-section.
  createTerminal: (subSection: SubSectionId) => void;
  // Open a single-instance static panel in the requesting sub-section.
  openStaticPanel: (panelId: string, subSection: SubSectionId) => void;
};

export const useAddPanelActions = (): AddPanelActions => {
  // state and hooks
  const store = useStore();
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const lastUsedAgentType = useAtomValue(lastUsedAgentTypeAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const { registrations, refetch } = useTerminalAgentRegistrations();
  // Subscribe to the layout so the re-add list recomputes when panels open/close.
  // (The Cmd+K path stays on the imperative listAvailableStaticPanels(store), which
  // runs outside React.)
  const layout = useAtomValue(workspaceLayoutAtom);

  // A stored "pi" is unusable once pi-agent is turned off — fall back to Claude.
  const defaultAgentType: StoredAgentType =
    lastUsedAgentType === "pi" && !isPiAgentEnabled ? "claude" : lastUsedAgentType;

  // functions and callbacks
  const refreshRegistrations = useCallback((): void => {
    void refetch();
  }, [refetch]);

  const createAgent = useCallback(
    (agentType: AgentTypeName, registrationId?: string): void => {
      void (async (): Promise<void> => {
        const taskId = await createAgentInCenter(store, { agentType, registrationId, activeAgentId: agentID });
        if (taskId !== undefined) {
          navigateToAgent(workspaceID, taskId);
        } else {
          store.set(createAgentErrorToastAtom, {
            title: "Failed to create agent",
            description: "The agent could not be created. Try again or check your connection.",
            type: ToastType.ERROR,
            action: null,
          });
        }
      })();
    },
    [store, agentID, workspaceID, navigateToAgent],
  );

  const createRecentAgent = useCallback((): void => {
    const { agentType, registrationId } = parseStoredAgentType(defaultAgentType);
    createAgent(agentType, registrationId);
  }, [defaultAgentType, createAgent]);

  const createTerminal = useCallback(
    (subSection: SubSectionId): void => {
      createTerminalInLocation(store, subSection);
    },
    [store],
  );

  const openStaticPanel = useCallback(
    (panelId: string, subSection: SubSectionId): void => {
      openStaticPanelInLocation(store, panelId, subSection);
    },
    [store],
  );

  // rendering / derived data
  const recentAgentLabel = agentTypeDisplayLabel(defaultAgentType, registrations);
  const agentTypeOptions = buildAgentTypeOptions({ isPiAgentEnabled, registrations });
  const availableStaticPanels = useMemo(
    () => listAvailableStaticPanelsFromPlacement(layout.placement),
    [layout.placement],
  );

  return {
    recentAgentLabel,
    agentTypeOptions,
    refreshRegistrations,
    availableStaticPanels,
    createRecentAgent,
    createAgent,
    createTerminal,
    openStaticPanel,
  };
};

// Display label for a stored agent type: built-in labels for Claude/pi/terminal,
// the registration's display name for a registered terminal agent, falling back to
// "agent" if a remembered registration has since been removed.
function agentTypeDisplayLabel(
  stored: StoredAgentType,
  registrations: ReadonlyArray<TerminalAgentRegistration>,
): string {
  if (stored.startsWith(REGISTERED_AGENT_TYPE_PREFIX)) {
    const { registrationId } = parseStoredAgentType(stored);
    return registrations.find((reg) => reg.registrationId === registrationId)?.displayName ?? "agent";
  }
  return AGENT_TYPE_LABELS[stored as Exclude<AgentTypeName, "registered">];
}

// The agent-type sub-menu options: Claude, pi (gated), and each registered
// terminal-agent program. No bare "Terminal" agent type.
function buildAgentTypeOptions(inputs: {
  isPiAgentEnabled: boolean;
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
  ];
  if (inputs.isPiAgentEnabled) {
    options.push({
      key: "pi",
      stored: "pi",
      agentType: "pi",
      registrationId: undefined,
      label: AGENT_TYPE_LABELS.pi,
    });
  }

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

// React-side mirror of addPanelCore's listAvailableStaticPanels: single-instance
// static panels not currently open anywhere — the re-add list. Takes the subscribed
// layout's placement (rather than reading the store imperatively) so the add-panel
// surfaces recompute whenever panels open/close. Dynamic agent/terminal ids never
// appear in STATIC_PANEL_METADATA, so they are inherently excluded.
function listAvailableStaticPanelsFromPlacement(
  placement: Partial<Record<PanelId, SubSectionId>>,
): ReadonlyArray<AvailableStaticPanel> {
  const openPanelIds = new Set<PanelId>(Object.keys(placement) as ReadonlyArray<PanelId>);
  return STATIC_PANEL_METADATA.filter((meta) => !openPanelIds.has(meta.id)).map((meta) => ({
    id: meta.id,
    displayName: meta.displayName,
    icon: meta.icon,
  }));
}
