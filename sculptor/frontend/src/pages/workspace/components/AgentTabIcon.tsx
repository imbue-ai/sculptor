import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { taskAtomFamily } from "~/common/state/atoms/tasks.ts";
import { AgentStatusDot, getAgentDotStatus } from "~/components/statusDot";

/**
 * Reactive status dot for an agent's panel tab. Subscribes to the single task
 * atom so the dot updates live (running / waiting / unread …) without rebuilding
 * the panel registry. Used as a `PanelDefinition.tabIcon`.
 */
export const AgentTabIcon = ({ agentId }: { agentId: string }): ReactElement | null => {
  const task = useAtomValue(taskAtomFamily(agentId));
  if (!task) return null;
  const dotStatus = getAgentDotStatus(task.status, task.lastReadAt, task.updatedAt);
  return <AgentStatusDot status={dotStatus} />;
};
