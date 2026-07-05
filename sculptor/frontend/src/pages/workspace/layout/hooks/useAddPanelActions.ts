// React ACTIONS hook for the add-panel surfaces: the section `+` dropdown
// (AddPanelDropdown), the empty-state quick actions (EmptySectionState), the
// new-agent keybinding (useWorkspaceShortcuts), and the bootstrap's Cmd+K
// "agent.create" registration.
//
// Deliberately subscription-free: the hook mounts in every section header and in
// the always-mounted shell spine, so it must not re-render its hosts on layout or
// registry churn. Every callback reads the state it needs (the normalized recent
// agent type) imperatively via the Jotai store at INVOCATION time. The lists the
// menus display (available static panels, agent-type options, the recent-agent
// label) are not the hook's concern — the menu content subscribes to the derived
// atoms in addPanel itself, and only while it is mounted (i.e. open).
//
// The actual create logic — including post-create navigation and the failure
// toast — lives in addPanel so the Cmd+K flows (which run outside React) share
// one implementation and can't drift. Agents, terminals, and single-instance panels
// all land in the requesting sub-section; the non-scoped surfaces (the new-agent
// keybinding and Cmd+K "New agent" command) pass no target and default to center.
// Agents/terminals are never in the re-add list.

import { useStore } from "jotai/react";
import { useCallback } from "react";

import type { AgentTypeName } from "~/api";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/hooks/navigation.ts";
import { parseStoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import {
  createAgentAndNavigate,
  createTerminalInLocation,
  openStaticPanelInLocation,
  recentAgentTypeAtom,
} from "~/pages/workspace/layout/atoms/addPanel.ts";
import type { SubSectionId } from "~/pages/workspace/layout/types/section.ts";

export type AddPanelActions = {
  // Create an agent of the recently-used type (Claude by default). Lands in the given
  // sub-section, defaulting to center for the non-scoped surfaces (keybinding / command).
  createRecentAgent: (target?: SubSectionId) => void;
  // Create an agent of a specific type. Lands in the given sub-section, defaulting to
  // center for the non-scoped surfaces.
  createAgent: (agentType: AgentTypeName, registrationId?: string, target?: SubSectionId) => void;
  // Create a terminal and place it in the requesting sub-section.
  createTerminal: (subSection: SubSectionId) => void;
  // Open a single-instance static panel in the requesting sub-section.
  openStaticPanel: (panelId: string, subSection: SubSectionId) => void;
};

export const useAddPanelActions = (): AddPanelActions => {
  // state and hooks
  const store = useStore();
  const { agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();

  // functions and callbacks
  const createAgent = useCallback(
    (agentType: AgentTypeName, registrationId?: string, target: SubSectionId = "center"): void => {
      // Navigation and the failure toast live in the shared core so the Cmd+K
      // "New agent" row behaves identically.
      void createAgentAndNavigate(
        store,
        target,
        { agentType, registrationId, activeAgentId: agentID },
        navigateToAgent,
      );
    },
    [store, agentID, navigateToAgent],
  );

  const createRecentAgent = useCallback(
    (target: SubSectionId = "center"): void => {
      // Read at press time (not render time) so the callback never goes stale and
      // the hosts never subscribe to the recent-type's inputs.
      const { agentType, registrationId } = parseStoredAgentType(store.get(recentAgentTypeAtom));
      createAgent(agentType, registrationId, target);
    },
    [store, createAgent],
  );

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

  return {
    createRecentAgent,
    createAgent,
    createTerminal,
    openStaticPanel,
  };
};
