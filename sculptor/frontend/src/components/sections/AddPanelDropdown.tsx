// The section `+` add-panel DROPDOWN (Radix DropdownMenu, not the cmdk overlay).
// Opened by the section header `+` and the empty-state add button, scoped to the
// sub-section it was opened from. Items, in order:
//   1. "New {recent} agent" — the recently-used agent type (Claude by default),
//      with its new-agent keybinding shown. ALWAYS lands the agent in center,
//      regardless of `subSection`.
//   2. Agent-type sub-menu — create an agent of a different type: Claude, pi
//      (gated), and each registered terminal-agent program. No bare "Terminal"
//      agent type. Also lands in center.
//   3. "New terminal" — creates a terminal in THIS sub-section.
//   4. Every single-instance panel not currently open anywhere — opens in THIS
//      sub-section. Agents/terminals are never offered (closing one ends it).
//
// Reuses the add-panel row styling, rendered as dropdown items.

import { DropdownMenu, Tooltip } from "@radix-ui/themes";
import { MessageSquarePlus, SquareTerminal } from "lucide-react";
import type { ReactElement } from "react";

import { type AgentTypeName, ElementIds } from "~/api";
import { useKeybindingDisplayText } from "~/common/keybindings/hooks.ts";

import styles from "./AddPanelDropdown.module.scss";
import type { SubSectionId } from "./sectionTypes.ts";
import { useAddPanelActions } from "./useAddPanelActions.ts";

type AddPanelDropdownProps = {
  subSection: SubSectionId;
  // The control that opens the dropdown (the section header `+` or the empty-state
  // add button). Wrapped in DropdownMenu.Trigger.
  trigger: ReactElement;
  // Optional hover tooltip for the trigger (e.g. the section header `+`). The
  // empty-state add button is self-explanatory and omits it.
  tooltip?: string;
};

// The agent-type sub-menu never offers a bare "terminal" type, so
// only claude / pi / registered appear; "terminal" maps to the registered testid
// for completeness.
const agentTypeTestId = (agentType: AgentTypeName): string => {
  switch (agentType) {
    case "claude":
      return ElementIds.AGENT_TYPE_MENU_ITEM_CLAUDE;
    case "pi":
      return ElementIds.AGENT_TYPE_MENU_ITEM_PI;
    case "registered":
    case "terminal":
      return ElementIds.AGENT_TYPE_MENU_ITEM_REGISTERED;
  }
};

export const AddPanelDropdown = ({ subSection, trigger, tooltip }: AddPanelDropdownProps): ReactElement => {
  // state and hooks
  const actions = useAddPanelActions();
  const newAgentShortcut = useKeybindingDisplayText("new_agent");

  // functions and callbacks
  const handleOpenChange = (isOpen: boolean): void => {
    // Re-read the registrations directory on open so the agent-type sub-menu
    // tracks the filesystem without a restart.
    if (isOpen) {
      actions.refreshRegistrations();
    }
  };

  // rendering / derived data
  return (
    <DropdownMenu.Root onOpenChange={handleOpenChange}>
      {tooltip !== undefined ? (
        <Tooltip content={tooltip}>
          <DropdownMenu.Trigger>{trigger}</DropdownMenu.Trigger>
        </Tooltip>
      ) : (
        <DropdownMenu.Trigger>{trigger}</DropdownMenu.Trigger>
      )}
      <DropdownMenu.Content size="1" data-testid={`${ElementIds.ADD_PANEL_DROPDOWN}-${subSection}`}>
        <DropdownMenu.Item data-testid={ElementIds.ADD_PANEL_NEW_AGENT} onSelect={() => actions.createRecentAgent()}>
          <span className={styles.item}>
            <span className={styles.itemIcon}>
              <MessageSquarePlus size={16} />
            </span>
            <span className={styles.itemTitle}>New {actions.recentAgentLabel} agent</span>
            {newAgentShortcut !== "" && <span className={styles.shortcut}>{newAgentShortcut}</span>}
          </span>
        </DropdownMenu.Item>

        <DropdownMenu.Sub>
          <DropdownMenu.SubTrigger data-testid={ElementIds.ADD_PANEL_AGENT_TYPE_SUBMENU}>
            <span className={styles.item}>
              <span className={styles.itemIcon}>
                <MessageSquarePlus size={16} />
              </span>
              <span className={styles.itemTitle}>New agent of type…</span>
            </span>
          </DropdownMenu.SubTrigger>
          <DropdownMenu.SubContent data-testid={ElementIds.AGENT_TYPE_MENU}>
            {actions.agentTypeOptions.map((option) => (
              <DropdownMenu.Item
                key={option.key}
                data-testid={agentTypeTestId(option.agentType)}
                data-registration-id={option.registrationId}
                onSelect={() => actions.createAgent(option.agentType, option.registrationId)}
              >
                <span className={styles.item}>
                  <span className={styles.itemIcon}>
                    {option.agentType === "registered" ? <SquareTerminal size={16} /> : <MessageSquarePlus size={16} />}
                  </span>
                  <span className={styles.itemTitle}>{option.label}</span>
                </span>
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.SubContent>
        </DropdownMenu.Sub>

        <DropdownMenu.Item
          data-testid={ElementIds.ADD_PANEL_NEW_TERMINAL}
          onSelect={() => actions.createTerminal(subSection)}
        >
          <span className={styles.item}>
            <span className={styles.itemIcon}>
              <SquareTerminal size={16} />
            </span>
            <span className={styles.itemTitle}>New terminal</span>
          </span>
        </DropdownMenu.Item>

        {actions.availableStaticPanels.length > 0 && (
          <>
            <DropdownMenu.Separator />
            {actions.availableStaticPanels.map((panel) => {
              const Icon = panel.icon;
              return (
                <DropdownMenu.Item
                  key={panel.id}
                  data-testid={`${ElementIds.ADD_PANEL_PANEL_OPTION}-${panel.id}`}
                  onSelect={() => actions.openStaticPanel(panel.id, subSection)}
                >
                  <span className={styles.item}>
                    <span className={styles.itemIcon}>
                      <Icon size={16} />
                    </span>
                    <span className={styles.itemTitle}>{panel.displayName}</span>
                  </span>
                </DropdownMenu.Item>
              );
            })}
          </>
        )}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};
