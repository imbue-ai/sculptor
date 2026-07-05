import { useMemo } from "react";

import type { CodingAgentTaskView } from "~/api";
import { useActiveProjectID, useWorkspacePageParams } from "~/common/hooks/navigation.ts";
import { useAgentChatMessages, useAgentDetailWithDefaults } from "~/common/state/hooks/useAgentDetail";
import { useAgent } from "~/common/state/hooks/useAgentHelpers";

import type { ArtifactsMap } from "../../../common/state/atoms/agentDetails.ts";
import { extractUserMessageIds } from "./suggestionUtils";

export type WorkspacePanelData = {
  agent: CodingAgentTaskView | null;
  artifacts: ArtifactsMap;
  userMessageIds: Array<string>;
  agentId: string;
  projectID: string | null;
};

export const useWorkspacePanelData = (): WorkspacePanelData => {
  const { agentID } = useWorkspacePageParams();
  const projectID = useActiveProjectID();
  const agentId = agentID ?? "";
  const agent = useAgent(agentId);
  const { artifacts } = useAgentDetailWithDefaults(agentId);
  const { chatMessages } = useAgentChatMessages(agentId);
  const userMessageIds = useMemo(() => extractUserMessageIds(chatMessages), [chatMessages]);

  return { agent, artifacts, userMessageIds, agentId, projectID };
};
