import { Flex } from "@radix-ui/themes";
import type { Editor as TipTapEditor } from "@tiptap/react";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useMemo, useRef } from "react";

import { useImbueNavigate, useWorkspacePageParams } from "../../common/NavigateUtils.ts";
import type { InsertSkillArg } from "../../common/state/atoms/chatActions.ts";
import { tasksArrayAtom } from "../../common/state/atoms/tasks.ts";
import {
  agentIdForWorkspaceAtomFamily,
  removeTabFromOrderAtom,
  setAgentForWorkspaceAtom,
  workspaceIdsAtom,
} from "../../common/state/atoms/workspaces.ts";
import { useMarkRead } from "../../common/state/hooks/useMarkRead";
import { usePanelLayoutSync } from "../../common/state/hooks/usePanelLayoutSync.ts";
import { usePerWorkspacePanelLayout } from "../../common/state/hooks/usePerWorkspacePanelLayout.ts";
import { useWorkspaceFiles } from "../../common/state/hooks/useWorkspaceFiles.ts";
import { DockingLayout } from "../../components/panels/DockingLayout";
import { useWorkspaceTabActions } from "../../components/useWorkspaceTabActions.ts";
import { AgentTabs } from "./components/AgentTabs.tsx";
import { BottomBar } from "./components/BottomBar";
import { ChatPanelContent } from "./components/ChatPanelContent.tsx";
import { DiffSplitContainer } from "./components/DiffSplitContainer.tsx";
import { WorkspaceBanner } from "./components/WorkspaceBanner.tsx";
import { useArtifactSync } from "./hooks/useArtifactSync";
import styles from "./WorkspacePage.module.scss";

const WorkspacePageContent = ({ taskID }: { taskID: string }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const appendTextRef = useRef<((text: string) => void) | null>(null);
  const insertSkillRef = useRef<((skill: InsertSkillArg) => void) | null>(null);
  const editorRef = useRef<TipTapEditor | null>(null);

  // Sync artifacts for the currently viewed task only
  useArtifactSync(workspaceID, taskID);
  usePanelLayoutSync();
  usePerWorkspacePanelLayout(workspaceID);

  // Pre-warm the file list cache so @-mention fuzzy search has data ready
  // before the user types, even if the file browser panel is not open.
  useWorkspaceFiles(workspaceID);

  // Mark agent as read when user views the chat
  useMarkRead(workspaceID, taskID);

  // Memoize center content — AlphaChatInterface owns its own data subscriptions,
  // so this subtree is stable across most re-renders of WorkspacePageContent.
  const centerContent = useMemo(
    () => (
      <Flex direction="column" className={styles.centerPanel}>
        <WorkspaceBanner />
        <DiffSplitContainer
          workspaceId={workspaceID}
          chatContent={
            <Flex direction="column" className={styles.centerPanel}>
              <ChatPanelContent appendTextRef={appendTextRef} insertSkillRef={insertSkillRef} editorRef={editorRef} />
              <AgentTabs />
            </Flex>
          }
        />
      </Flex>
    ),
    [workspaceID],
  );

  return (
    <Flex direction="column" className={styles.container} overflowY="hidden">
      <DockingLayout centerContent={centerContent} />
      <BottomBar />
    </Flex>
  );
};

export const WorkspacePage = (): ReactElement | null => {
  const { workspaceID, agentID: agentIDFromUrl } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const { navigateToNextTab } = useWorkspaceTabActions();
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
      // The workspace backing this route is gone. This fires when the workspace
      // was deleted out from under us — either the active tab we just deleted
      // (whose confirmation drops it from workspaceIds while this route still
      // holds the stale param) or a deletion from another session. Drop the now-
      // stale tab and land on the next surviving tab; navigateToNextTab only
      // falls back to the add-workspace page when no tabs remain. Routing
      // through it (instead of always going to /ws/new) keeps us on a sibling
      // workspace and avoids spawning a phantom new-workspace tab.
      removeTab(workspaceID);
      navigateToNextTab(workspaceID);
      return;
    }
    if (agentIDFromUrl) return; // URL is authoritative, nothing to fix up
    if (tasks === undefined) return; // tasks haven't loaded; can't validate yet

    const workspaceTasks = tasks.filter((task) => task.workspaceId === workspaceID);
    if (savedAgentId !== null && workspaceTasks.some((task) => task.id === savedAgentId)) {
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
    navigateToNextTab,
    setAgentForWorkspace,
    removeTab,
  ]);

  if (!agentIDFromUrl) return null;
  return <WorkspacePageContent taskID={agentIDFromUrl} />;
};
