import { useMemo } from "react";

import type { CodingAgentTaskView } from "~/api";
import { useActiveProjectID, useWorkspacePageParams } from "~/common/hooks/navigation.ts";
import { useTaskChatMessages, useTaskDetailWithDefaults } from "~/common/state/hooks/useTaskDetail";
import { useTask } from "~/common/state/hooks/useTaskHelpers";

import type { ArtifactsMap } from "../../../common/state/atoms/taskDetails.ts";
import { extractUserMessageIds } from "./suggestionUtils";

export type WorkspacePanelData = {
  task: CodingAgentTaskView | null;
  artifacts: ArtifactsMap;
  userMessageIds: Array<string>;
  taskID: string;
  projectID: string | null;
};

export const useWorkspacePanelData = (): WorkspacePanelData => {
  const { agentID } = useWorkspacePageParams();
  const projectID = useActiveProjectID();
  const taskID = agentID ?? "";
  const task = useTask(taskID);
  const { artifacts } = useTaskDetailWithDefaults(taskID);
  const { chatMessages } = useTaskChatMessages(taskID);
  const userMessageIds = useMemo(() => extractUserMessageIds(chatMessages), [chatMessages]);

  return { task, artifacts, userMessageIds, taskID, projectID };
};
