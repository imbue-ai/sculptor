// The section `+` add-panel DROPDOWN (Radix DropdownMenu, not the cmdk overlay).
// Opened by the section header `+` and the empty-state add button, scoped to the
// sub-section it was opened from. Items, in order:
//   1. "New {recent} agent" — the recently-used agent type (Claude by default),
//      with its new-agent keybinding shown. Lands the agent in THIS sub-section.
//   2. Agent-type sub-menu — create an agent of a different type: Claude, pi,
//      and each registered terminal-agent program. No bare "Terminal"
//      agent type. Also lands in THIS sub-section.
//   3. "New terminal" — creates a terminal in THIS sub-section.
//   4. Every single-instance panel not currently open anywhere — opens in THIS
//      sub-section. Agents/terminals are never offered (closing one ends it).
//
// Reuses the add-panel row styling, rendered as dropdown items.

import { DropdownMenu, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useRef } from "react";

import { type AgentTypeName, ElementIds } from "~/api";
import { useKeybindingDisplayText } from "~/common/keybindings/hooks.ts";
import { INSTALL_PI_LABEL, usePiAgentOption } from "~/common/state/hooks/usePiAgentOption.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import { mergeClasses } from "~/common/Utils.ts";

import {
  availableStaticPanelsAtom,
  buildAgentTypeOptions,
  recentAgentLabel,
  recentAgentTypeAtom,
} from "./addPanelCore.ts";
import styles from "./AddPanelDropdown.module.scss";
import type { SubSectionId } from "./sectionTypes.ts";
import { useAddPanelActions } from "./useAddPanelActions.ts";

// The shared row body rendered inside every dropdown item and sub-trigger: a label
// with an optional trailing keybinding hint (no leading icons — text-only rows).
// When a description is supplied it renders inline after the label on the same row,
// muted and ellipsized when space runs short; the label then holds its width so the
// description is what gives way. A row without a description is a single title line
// that ellipsizes if it outgrows the menu. Hover/active backgrounds come from the
// wrapping Radix item, so this only lays out the contents.
const MenuRow = ({
  label,
  shortcut,
  description,
}: {
  label: string;
  shortcut?: string;
  description?: string;
}): ReactElement => {
  const hasDescription = description !== undefined && description !== "";
  return (
    <span className={styles.item}>
      <span className={styles.itemText}>
        <span className={mergeClasses(styles.itemTitle, hasDescription ? styles.itemTitleWithDescription : undefined)}>
          {label}
        </span>
        {hasDescription && <span className={styles.description}>{description}</span>}
      </span>
      {shortcut !== undefined && shortcut !== "" && <span className={styles.shortcut}>{shortcut}</span>}
    </span>
  );
};

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

// The dropdown's item list. A separate component (rather than inline JSX in
// AddPanelDropdown) so its subscriptions — the layout/registry-derived panel list,
// the recent agent type, the registrations query — mount only while the menu is
// OPEN: Radix mounts DropdownMenu.Content's children on open and unmounts them on
// close, so a closed dropdown costs its host section header nothing. Do not lift
// these reads into AddPanelDropdown/useAddPanelActions, which stay mounted in every
// section header and would re-render the shell on every layout write.
const AddPanelMenuItems = ({
  subSection,
  onOpenPanel,
}: {
  subSection: SubSectionId;
  // Called synchronously when an item is selected, before the menu closes, so the
  // dropdown can suppress Radix's focus-restore-to-trigger (see AddPanelDropdown).
  onOpenPanel: () => void;
}): ReactElement => {
  // state and hooks
  const actions = useAddPanelActions();
  const newAgentShortcut = useKeybindingDisplayText("new_agent");
  const recentAgentType = useAtomValue(recentAgentTypeAtom);
  const availableStaticPanels = useAtomValue(availableStaticPanelsAtom);
  // Mounting on menu open re-fetches the registrations (staleTime 0 +
  // refetchOnMount), so the agent-type sub-menu tracks the registrations
  // directory without a restart or an explicit refetch call.
  const { registrations } = useTerminalAgentRegistrations();
  const { isPiAvailable, openPiSettings } = usePiAgentOption();

  // rendering / derived data
  const agentTypeOptions = buildAgentTypeOptions({ registrations });

  return (
    <>
      <DropdownMenu.Item
        data-testid={ElementIds.ADD_PANEL_NEW_AGENT}
        onSelect={() => {
          onOpenPanel();
          actions.createRecentAgent(subSection);
        }}
      >
        <MenuRow label={`New ${recentAgentLabel(recentAgentType, registrations)} agent`} shortcut={newAgentShortcut} />
      </DropdownMenu.Item>

      <DropdownMenu.Sub>
        <DropdownMenu.SubTrigger data-testid={ElementIds.ADD_PANEL_AGENT_TYPE_SUBMENU}>
          <MenuRow label="New agent of type…" />
        </DropdownMenu.SubTrigger>
        <DropdownMenu.SubContent data-testid={ElementIds.AGENT_TYPE_MENU}>
          {agentTypeOptions.map((option) => {
            // pi is optional: while no usable binary is resolved its entry reads
            // "Install Pi" and routes to Settings → Pi instead of creating a pi
            // agent that cannot launch.
            const isUnavailablePi = option.agentType === "pi" && !isPiAvailable;
            return (
              <DropdownMenu.Item
                key={option.key}
                data-testid={agentTypeTestId(option.agentType)}
                data-registration-id={option.registrationId}
                onSelect={() => {
                  if (isUnavailablePi) {
                    openPiSettings();
                    return;
                  }
                  onOpenPanel();
                  actions.createAgent(option.agentType, option.registrationId, subSection);
                }}
              >
                <MenuRow label={isUnavailablePi ? INSTALL_PI_LABEL : option.label} />
              </DropdownMenu.Item>
            );
          })}
        </DropdownMenu.SubContent>
      </DropdownMenu.Sub>

      <DropdownMenu.Item
        data-testid={ElementIds.ADD_PANEL_NEW_TERMINAL}
        onSelect={() => {
          onOpenPanel();
          actions.createTerminal(subSection);
        }}
      >
        <MenuRow label="New terminal" />
      </DropdownMenu.Item>

      {availableStaticPanels.length > 0 && (
        <>
          <DropdownMenu.Separator />
          {availableStaticPanels.map((panel) => (
            <DropdownMenu.Item
              key={panel.id}
              data-testid={`${ElementIds.ADD_PANEL_PANEL_OPTION}-${panel.id}`}
              onSelect={() => {
                onOpenPanel();
                actions.openStaticPanel(panel.id, subSection);
              }}
            >
              <MenuRow label={panel.displayName} description={panel.description} />
            </DropdownMenu.Item>
          ))}
        </>
      )}
    </>
  );
};

export const AddPanelDropdown = ({ subSection, trigger, tooltip }: AddPanelDropdownProps): ReactElement => {
  // Selecting an item opens a panel/agent/terminal that manages its own focus
  // (e.g. the Browser panel focuses its URL bar, an agent focuses its composer).
  // Radix's default close behaviour restores focus to the trigger `+`, which lands
  // AFTER the opened panel's mount-focus and steals it back. Suppress that restore
  // only when the close was caused by an item selection; Escape / click-outside
  // (no selection) still return focus to the trigger for keyboard users.
  const openedPanelRef = useRef(false);
  return (
    <DropdownMenu.Root>
      {tooltip !== undefined ? (
        <Tooltip content={tooltip}>
          <DropdownMenu.Trigger>{trigger}</DropdownMenu.Trigger>
        </Tooltip>
      ) : (
        <DropdownMenu.Trigger>{trigger}</DropdownMenu.Trigger>
      )}
      <DropdownMenu.Content
        size="1"
        className={styles.content}
        data-testid={`${ElementIds.ADD_PANEL_DROPDOWN}-${subSection}`}
        onCloseAutoFocus={(event) => {
          if (openedPanelRef.current) {
            openedPanelRef.current = false;
            event.preventDefault();
          }
        }}
      >
        <AddPanelMenuItems
          subSection={subSection}
          onOpenPanel={() => {
            openedPanelRef.current = true;
          }}
        />
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};
