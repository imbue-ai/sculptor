import { Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { X } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { AgentOverrideContext, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { AgentStatusDot, getAgentDotStatus } from "~/components/statusDot";

import { secondChatAgentIdAtomFamily } from "./centerAtoms.ts";
import { ChatPanelContent } from "./ChatPanelContent.tsx";
import styles from "./SecondaryChatPane.module.scss";

/**
 * The Center's second chat pane (pane B) when the chat is split. Renders an
 * independent chat for `agentId` — its own scroll and input — with a thin header
 * styled to match the terminal tab strip, and a close button that collapses the
 * split (REQ-CHAT-1/2/3).
 */
export const SecondaryChatPane = ({ agentId }: { agentId: string }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const setSecondChat = useSetAtom(secondChatAgentIdAtomFamily(workspaceID));
  const tasks = useAtomValue(tasksArrayAtom);

  const agent = useMemo(() => (tasks ?? []).find((t) => t.id === agentId), [tasks, agentId]);
  const dotStatus = agent ? getAgentDotStatus(agent.status, agent.lastReadAt, agent.updatedAt) : null;

  return (
    <Flex direction="column" height="100%" overflow="hidden">
      <Flex align="center" gap="2" px="2" className={styles.header}>
        {dotStatus && <AgentStatusDot status={dotStatus} />}
        <Text size="1" className={styles.title} truncate>
          {agent?.title ?? "Untitled"}
        </Text>
        <span style={{ flex: 1 }} />
        <Tooltip content="Close split" side="bottom">
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            onClick={() => setSecondChat(null)}
            aria-label="Close split"
            data-testid="chat-split-close"
          >
            <X size={14} />
          </IconButton>
        </Tooltip>
      </Flex>
      <div className={styles.chat}>
        <AgentOverrideContext.Provider value={agentId}>
          <ChatPanelContent taskIDOverride={agentId} />
        </AgentOverrideContext.Provider>
      </div>
    </Flex>
  );
};
