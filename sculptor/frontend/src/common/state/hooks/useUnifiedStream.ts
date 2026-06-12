import { useSetAtom, useStore } from "jotai";
import { useCallback } from "react";

import { openFileFromUiEventAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { agentWebviewStateAtomFamily } from "~/pages/workspace/panels/browser/atoms.ts";

import type { StreamingUpdate } from "../../../api";
import { handleBtwUpdateAtom } from "../atoms/btwPopup";
import { dependenciesStatusAtom } from "../atoms/dependenciesStatus";
import { notificationsAtom } from "../atoms/notifications";
import { updateProjectsAtom } from "../atoms/projects";
import { updatePrStatusAtom } from "../atoms/prStatus";
import { sculptorSettingsAtom } from "../atoms/sculptorSettings";
import { getEmptyTaskDetailState, updateTaskDetailAtom, updateTaskUpdatedArtifactsAtom } from "../atoms/taskDetails";
import { updateTasksAtom } from "../atoms/tasks";
import { updateWorkspaceBranchAtom } from "../atoms/workspaceBranch";
import { updateWorkspaceRemoteBranchesAtom } from "../atoms/workspaceRemoteBranches";
import { updateWorkspacesAtom } from "../atoms/workspaces";
import { appendSetupOutputChunkAtom } from "../atoms/workspaceSetupOutput";
import { updateWorkspaceSetupStatusAtom } from "../atoms/workspaceSetupStatus";
import { acknowledgeRequests, updateActiveWebsockets } from "../requestTracking";
import { chatMessagesReducer } from "../taskDetailReducers.ts";
import { useWebsocket } from "./useWebsocket";

const API_BASE_URL = "/api/v1";

/**
 * This hook:
 * 1. Connects to the unified WebSocket stream
 * 2. Processes task view updates (for sidebar/task list)
 * 3. Processes task detail updates for ALL tasks (even background ones)
 * 4. Processes user updates (projects, settings, repo info)
 * 5. Handles request tracking acknowledgments
 *
 * Task details are accumulated in global atoms so switching between tasks
 * doesn't lose state.
 */
export const useUnifiedStream = (): void => {
  const updateTasks = useSetAtom(updateTasksAtom);
  const updateProjects = useSetAtom(updateProjectsAtom);
  const updateWorkspaces = useSetAtom(updateWorkspacesAtom);
  const setNotifications = useSetAtom(notificationsAtom);
  const setSculptorSettings = useSetAtom(sculptorSettingsAtom);
  const updateTaskDetail = useSetAtom(updateTaskDetailAtom);
  const updateTaskUpdatedArtifacts = useSetAtom(updateTaskUpdatedArtifactsAtom);
  const updatePrStatus = useSetAtom(updatePrStatusAtom);
  const updateWorkspaceBranch = useSetAtom(updateWorkspaceBranchAtom);
  const updateWorkspaceRemoteBranches = useSetAtom(updateWorkspaceRemoteBranchesAtom);
  const updateWorkspaceSetupStatus = useSetAtom(updateWorkspaceSetupStatusAtom);
  const appendSetupOutputChunk = useSetAtom(appendSetupOutputChunkAtom);
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);
  const handleBtwUpdate = useSetAtom(handleBtwUpdateAtom);
  const openFileFromUiEvent = useSetAtom(openFileFromUiEventAtom);
  const store = useStore();

  const onOpen = useCallback(() => {
    updateActiveWebsockets(true);
  }, []);

  const onClose = useCallback(() => {
    updateActiveWebsockets(false);
  }, []);

  const onMessage = useCallback(
    (data: StreamingUpdate): void => {
      // ========================================================================
      // Handle task views (for task list/sidebar)
      // ========================================================================
      if (data.taskViewsByTaskId) {
        updateTasks(data.taskViewsByTaskId);
      }

      // ========================================================================
      // Handle task details (for chat pages)
      //    Process ALL tasks, even if not currently viewing them
      // NOTE: This is O(activeTasks) because we only get a task update if something happens
      // ========================================================================
      if (data.taskUpdateByTaskId && Object.keys(data.taskUpdateByTaskId).length > 0) {
        Object.entries(data.taskUpdateByTaskId).forEach(([taskId, taskUpdate]) => {
          updateTaskDetail({
            taskId,
            updater: (currentState) => {
              const state = currentState || getEmptyTaskDetailState();

              // Process incremental updates using pure reducers
              const newChatState = chatMessagesReducer(
                {
                  completedChatMessages: state.completedChatMessages,
                  inProgressChatMessage: state.inProgressChatMessage,
                  queuedChatMessages: state.queuedChatMessages,
                  workingUserMessageId: state.workingUserMessageId,
                  pendingUserQuestion: state.pendingUserQuestion,
                  submittedQuestionAnswers: state.submittedQuestionAnswers,
                  isInPlanMode: state.isInPlanMode,
                  pendingBackgroundTaskIds: state.pendingBackgroundTaskIds,
                },
                taskUpdate,
              );

              return {
                ...state,
                ...newChatState,
              };
            },
          });

          // Track which artifacts need fetching
          if (taskUpdate.updatedArtifacts && taskUpdate.updatedArtifacts.length > 0) {
            updateTaskUpdatedArtifacts({
              taskId,
              artifactTypes: taskUpdate.updatedArtifacts,
            });
          }
        });
      }

      // ========================================================================
      // Handle user update
      // ========================================================================
      if (data.userUpdate) {
        const userUpdate = data.userUpdate;

        if (userUpdate.notifications && userUpdate.notifications.length > 0) {
          setNotifications(userUpdate.notifications);
        }

        if (userUpdate.projects && userUpdate.projects.length > 0) {
          const activeProjects = userUpdate.projects.filter((p) => !p.isDeleted);
          updateProjects(activeProjects);
        }

        if (userUpdate.workspaces) {
          updateWorkspaces(userUpdate.workspaces);
        }

        if (userUpdate.settings) {
          setSculptorSettings(userUpdate.settings);
        }
      }

      // ========================================================================
      // Handle workspace branch updates
      // ========================================================================
      if (data.workspaceBranchByWorkspaceId && Object.keys(data.workspaceBranchByWorkspaceId).length > 0) {
        Object.entries(data.workspaceBranchByWorkspaceId).forEach(([workspaceId, branchInfo]) => {
          updateWorkspaceBranch({ workspaceId, branchInfo: branchInfo ?? null });
        });
      }

      // ========================================================================
      // Handle workspace remote-branches updates
      // ========================================================================
      if (
        data.workspaceRemoteBranchesByWorkspaceId &&
        Object.keys(data.workspaceRemoteBranchesByWorkspaceId).length > 0
      ) {
        Object.entries(data.workspaceRemoteBranchesByWorkspaceId).forEach(([workspaceId, remoteBranchesInfo]) => {
          updateWorkspaceRemoteBranches({ workspaceId, remoteBranchesInfo: remoteBranchesInfo ?? null });
        });
      }

      // ========================================================================
      // Handle workspace setup status updates
      // ========================================================================
      if (data.workspaceSetupStatusByWorkspaceId && Object.keys(data.workspaceSetupStatusByWorkspaceId).length > 0) {
        Object.entries(data.workspaceSetupStatusByWorkspaceId).forEach(([workspaceId, setupStatus]) => {
          updateWorkspaceSetupStatus({ workspaceId, status: setupStatus ?? null });
        });
      }

      // ========================================================================
      // Handle workspace setup live output chunks
      // ========================================================================
      if (data.workspaceSetupOutputByWorkspaceId && Object.keys(data.workspaceSetupOutputByWorkspaceId).length > 0) {
        Object.entries(data.workspaceSetupOutputByWorkspaceId).forEach(([workspaceId, chunks]) => {
          chunks.forEach((chunk) => {
            appendSetupOutputChunk({ workspaceId, chunk });
          });
        });
      }

      // ========================================================================
      // Handle dependencies status updates
      // ========================================================================
      if (data.dependenciesStatus) {
        setDependenciesStatus(data.dependenciesStatus);
      }

      // ========================================================================
      // Handle PR status updates
      // ========================================================================
      if (data.prStatusByWorkspaceId && Object.keys(data.prStatusByWorkspaceId).length > 0) {
        Object.entries(data.prStatusByWorkspaceId).forEach(([workspaceId, prStatus]) => {
          updatePrStatus({ workspaceId, prStatus: prStatus ?? null });
        });
      }

      // ========================================================================
      // Handle finished request IDs
      // ========================================================================
      if (data.finishedRequestIds && data.finishedRequestIds.length > 0) {
        acknowledgeRequests(data.finishedRequestIds);
      }

      // ========================================================================
      // Handle /btw side-chat streaming updates
      // ========================================================================
      if (data.btwUpdate) {
        handleBtwUpdate({
          requestId: data.btwUpdate.requestId,
          state: data.btwUpdate.state,
          answer: data.btwUpdate.answer,
          errorMessage: data.btwUpdate.errorMessage ?? null,
        });
      }

      // ========================================================================
      // Handle ui open-file events (sculpt ui open-file)
      // ========================================================================
      if (data.uiOpenFileByWorkspaceId && Object.keys(data.uiOpenFileByWorkspaceId).length > 0) {
        Object.entries(data.uiOpenFileByWorkspaceId).forEach(([workspaceId, action]) => {
          openFileFromUiEvent({
            workspaceId,
            filePath: action.filePath,
            mode: action.mode,
          });
        });
      }

      // ========================================================================
      // Handle agent webview commands (sculpt ui webview-navigate / webview-refresh)
      // ========================================================================
      if (data.uiWebviewCommandByWorkspaceId && Object.keys(data.uiWebviewCommandByWorkspaceId).length > 0) {
        Object.entries(data.uiWebviewCommandByWorkspaceId).forEach(([workspaceId, action]) => {
          store.set(agentWebviewStateAtomFamily(workspaceId), (prev) => ({ ...prev, command: action }));
        });
      }
    },
    [
      updateTasks,
      updateProjects,
      updateWorkspaces,
      setNotifications,
      setSculptorSettings,
      updateTaskDetail,
      updateTaskUpdatedArtifacts,
      updatePrStatus,
      updateWorkspaceBranch,
      updateWorkspaceRemoteBranches,
      updateWorkspaceSetupStatus,
      appendSetupOutputChunk,
      setDependenciesStatus,
      handleBtwUpdate,
      openFileFromUiEvent,
      store,
    ],
  );

  useWebsocket<StreamingUpdate>({
    url: `${API_BASE_URL}/stream/ws`,
    onOpen,
    onClose,
    onMessage,
  });
};
