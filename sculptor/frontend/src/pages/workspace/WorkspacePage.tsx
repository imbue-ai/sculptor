import { Flex } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useMemo, useRef } from "react";

import { useImbueNavigate, useWorkspacePageParams } from "../../common/NavigateUtils.ts";
import { markSwitchMilestone } from "../../common/perf/workspaceSwitchProfiler.ts";
import { tasksArrayAtom } from "../../common/state/atoms/tasks.ts";
import {
  agentIdForWorkspaceAtomFamily,
  removeTabFromOrderAtom,
  setAgentForWorkspaceAtom,
  workspaceIdsAtom,
} from "../../common/state/atoms/workspaces.ts";
import { useMarkRead } from "../../common/state/hooks/useMarkRead";
import { usePerWorkspacePanelLayout } from "../../common/state/hooks/usePerWorkspacePanelLayout.ts";
import { useWorkspaceFiles } from "../../common/state/hooks/useWorkspaceFiles.ts";
import { CompactLayout } from "../../components/panels/CompactLayout.tsx";
import { useWorkspaceLayoutBootstrap } from "../workspace/panels/useWorkspaceLayoutBootstrap.ts";
import { workspaceDefaultLayout } from "../workspace/panels/workspacePanels.ts";
import { AgentWorkspaceCommands } from "./components/AgentWorkspaceCommands.tsx";
import { WorkspaceBanner } from "./components/WorkspaceBanner.tsx";
import { useArtifactSync } from "./hooks/useArtifactSync";
import styles from "./WorkspacePage.module.scss";

const WorkspacePageContent = ({ taskID }: { taskID: string }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();

  // Profiling: record the first render with a new workspace id (the switch's
  // first commit). Marked during render rather than in an effect so it lands
  // before — not after — the paint it describes.
  const profiledWorkspaceIdRef = useRef<string | null>(null);
  if (profiledWorkspaceIdRef.current !== workspaceID) {
    profiledWorkspaceIdRef.current = workspaceID;
    markSwitchMilestone("page-content-render");
  }

  // Sync artifacts for the currently viewed task only
  useArtifactSync(workspaceID, taskID);
  usePerWorkspacePanelLayout(workspaceID, workspaceDefaultLayout);

  // Pre-warm the file list cache so @-mention fuzzy search has data ready
  // before the user types, even if the file browser panel is not open.
  useWorkspaceFiles(workspaceID);

  // Mark agent as read when user views the chat
  useMarkRead(workspaceID, taskID);

  // Place the active agent into the Center section and seed the Bottom terminal
  // on first visit (REQ-DEFAULT-1 / REQ-AGENT-1).
  useWorkspaceLayoutBootstrap({ workspaceId: workspaceID, agentId: taskID });

  return (
    <Flex direction="column" className={styles.container} overflowY="hidden">
      <WorkspaceBanner />
      <CompactLayout />
      <AgentWorkspaceCommands />
    </Flex>
  );
};

export const WorkspacePage = (): ReactElement | null => {
  const { workspaceID, agentID: agentIDFromUrl } = useWorkspacePageParams();
  const { navigateToAgent, navigateToAddWorkspace } = useImbueNavigate();
  const tasks = useAtomValue(tasksArrayAtom);
  const workspaceIds = useAtomValue(workspaceIdsAtom);
  const savedAgentIdAtom = useMemo(() => agentIdForWorkspaceAtomFamily(workspaceID), [workspaceID]);
  const savedAgentId = useAtomValue(savedAgentIdAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);
  const removeTab = useSetAtom(removeTabFromOrderAtom);

  // Optimistic-render-then-validate: rootLoader has already redirected us to
  // the saved agent URL on cold start, so the common path is `agentIDFromUrl`
  // is set and we render WorkspacePageContent immediately. This effect only
  // covers the cleanup paths: stale workspace, stale or missing agent.
  useEffect(() => {
    if (workspaceIds === undefined) return; // first WS snapshot hasn't arrived
    if (!workspaceIds.includes(workspaceID)) {
      // Workspace was deleted between sessions — drop the tab and bail out.
      removeTab(workspaceID);
      navigateToAddWorkspace();
      return;
    }
    if (agentIDFromUrl) return; // URL is authoritative, nothing to fix up
    if (tasks === undefined) return; // tasks haven't loaded; can't validate yet

    const workspaceTasks = tasks.filter((task) => task.workspaceId === workspaceID);
    const hasSavedTask = savedAgentId !== null && workspaceTasks.some((task) => task.id === savedAgentId);
    if (hasSavedTask && savedAgentId !== null) {
      navigateToAgent(workspaceID, savedAgentId);
      return;
    }
    const fallback = workspaceTasks[0];
    if (fallback) {
      setAgentForWorkspace({ wsId: workspaceID, agentId: fallback.id });
      navigateToAgent(workspaceID, fallback.id);
    }
  }, [
    workspaceID,
    agentIDFromUrl,
    workspaceIds,
    tasks,
    savedAgentId,
    navigateToAgent,
    navigateToAddWorkspace,
    setAgentForWorkspace,
    removeTab,
  ]);

  if (!agentIDFromUrl) return null;
  return <WorkspacePageContent taskID={agentIDFromUrl} />;
};
