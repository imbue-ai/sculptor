import { Flex, Select, Text } from "@radix-ui/themes";
import { BotIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import {
  AGENT_TYPE_LABELS,
  encodeRegisteredAgentType,
  parseStoredAgentType,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";

type AgentTypeSelectProps = {
  /** The stored agent type (e.g. "claude", "registered:<id>"). */
  value: StoredAgentType;
  onChange: (value: StoredAgentType) => void;
  className?: string;
};

/**
 * The first-agent type picker — the same per-agent choice as the tab bar's `+`
 * menu. Claude, Pi, Terminal, and any registered terminal agents are all
 * available to everyone.
 */
export const AgentTypeSelect = ({ value, onChange, className }: AgentTypeSelectProps): ReactElement => {
  // State and hooks
  const { registrations, refetch: refreshRegistrations } = useTerminalAgentRegistrations();

  // JSX and rendering logic
  const { agentType, registrationId } = parseStoredAgentType(value);
  const triggerLabel =
    agentType === "registered"
      ? (registrations.find((r) => r.registrationId === registrationId)?.displayName ?? "Registered")
      : AGENT_TYPE_LABELS[agentType];

  return (
    <Select.Root
      size="1"
      value={value}
      onValueChange={(next) => onChange(next as StoredAgentType)}
      onOpenChange={(open) => {
        // Re-read the registrations directory on every open so the options track
        // the filesystem without a restart.
        if (open) refreshRegistrations();
      }}
    >
      <Select.Trigger variant="ghost" className={className} data-testid={ElementIds.ADD_WORKSPACE_AGENT_TYPE_SELECT}>
        <Flex align="center" gap="1">
          <BotIcon size={12} />
          <Text size="1" color="gray">
            agent
          </Text>
          <Text size="1" weight="medium" color="gray" highContrast>
            {triggerLabel}
          </Text>
        </Flex>
      </Select.Trigger>
      <Select.Content position="popper" side="bottom" sideOffset={5}>
        <Select.Item value="claude" data-testid={ElementIds.AGENT_TYPE_OPTION_CLAUDE}>
          {AGENT_TYPE_LABELS.claude}
        </Select.Item>
        <Select.Item value="pi" data-testid={ElementIds.AGENT_TYPE_OPTION_PI}>
          {AGENT_TYPE_LABELS.pi}
        </Select.Item>
        <Select.Item value="terminal" data-testid={ElementIds.AGENT_TYPE_OPTION_TERMINAL}>
          {AGENT_TYPE_LABELS.terminal}
        </Select.Item>
        {registrations.map((registration) => (
          <Select.Item
            key={registration.registrationId}
            value={encodeRegisteredAgentType(registration.registrationId)}
            data-testid={ElementIds.AGENT_TYPE_OPTION_REGISTERED}
            data-registration-id={registration.registrationId}
          >
            {registration.displayName}
          </Select.Item>
        ))}
      </Select.Content>
    </Select.Root>
  );
};
